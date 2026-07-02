from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    CfnOutput,
)
from constructs import Construct


POSTGRES_PASSWORD_PARAM = "/cloud-project/postgres-password"
SUPERSET_PASSWORD_PARAM = "/cloud-project/superset-admin-password"


class Ec2Stack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        ec2_sg: ec2.ISecurityGroup,
        key_pair_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        instance_role = iam.Role(
            self, "SupersetEc2Role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        instance_role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter{POSTGRES_PASSWORD_PARAM}",
                f"arn:aws:ssm:{self.region}:{self.account}:parameter{SUPERSET_PASSWORD_PARAM}",
            ],
        ))

        instance_role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "kms:ViaService": f"ssm.{self.region}.amazonaws.com"
                },
            },
        ))

        user_data = ec2.UserData.for_linux()
        user_data.add_commands(
            "set -e",
            "exec > /var/log/user-data.log 2>&1",
            "echo 'Starting user data script...'",

            "yum update -y",
            "yum install -y docker jq",
            "systemctl start docker",
            "systemctl enable docker",
            "usermod -aG docker ec2-user",

            "curl -L https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose",
            "chmod +x /usr/local/bin/docker-compose",

            "dd if=/dev/zero of=/swapfile bs=128M count=16",
            "chmod 600 /swapfile",
            "mkswap /swapfile",
            "swapon /swapfile",
            "echo '/swapfile swap swap defaults 0 0' >> /etc/fstab",

            f"POSTGRES_PASS=$(aws ssm get-parameter --name {POSTGRES_PASSWORD_PARAM} --with-decryption --region {self.region} --query Parameter.Value --output text)",
            f"SUPERSET_PASS=$(aws ssm get-parameter --name {SUPERSET_PASSWORD_PARAM} --with-decryption --region {self.region} --query Parameter.Value --output text)",

            "mkdir -p /opt/superset",
            "cd /opt/superset",

            "cat > docker-compose.yml << 'EOF'\n"
            "services:\n"
            "  postgres:\n"
            "    image: postgres:15\n"
            "    restart: always\n"
            "    environment:\n"
            "      POSTGRES_USER: cloud_project\n"
            "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}\n"
            "      POSTGRES_DB: gold_metrics\n"
            "    ports:\n"
            "      - '5432:5432'\n"
            "    volumes:\n"
            "      - postgres_data:/var/lib/postgresql/data\n"
            "\n"
            "  superset:\n"
            "    image: apache/superset:latest\n"
            "    restart: always\n"
            "    depends_on:\n"
            "      - postgres\n"
            "    environment:\n"
            "      SUPERSET_SECRET_KEY: change_me_to_random_string_12345\n"
            "    ports:\n"
            "      - '8088:8088'\n"
            "    volumes:\n"
            "      - superset_home:/app/superset_home\n"
            "\n"
            "volumes:\n"
            "  postgres_data:\n"
            "  superset_home:\n"
            "EOF",

            "cat > .env << EOF\n"
            "POSTGRES_PASSWORD=$POSTGRES_PASS\n"
            "EOF",

            "docker-compose up -d",

            "echo 'Waiting for services to start...'",
            "sleep 60",

            f"docker exec superset-superset-1 superset fab create-admin --username admin --firstname Admin --lastname User --email admin@example.com --password $SUPERSET_PASS || true",
            "docker exec superset-superset-1 superset db upgrade",
            "docker exec superset-superset-1 superset init",

            "echo 'Setup complete!'",
        )

        self.instance = ec2.Instance(
            self, "SupersetInstance",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO,
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=ec2_sg,
            key_name=key_pair_name,
            role=instance_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=20,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                    ),
                ),
            ],
        )

        CfnOutput(
            self, "InstancePublicIp",
            value=self.instance.instance_public_ip,
            description="Public IP EC2 instance (SSH i Superset)",
        )

        CfnOutput(
            self, "SupersetUrl",
            value=f"http://{self.instance.instance_public_ip}:8088",
            description="Superset web UI",
        )