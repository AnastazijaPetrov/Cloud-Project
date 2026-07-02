from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct


class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        nat_provider = ec2.NatProvider.instance_v2(
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3,
                ec2.InstanceSize.MICRO,
            ),
        )

        # vpc with public and private subnets in 2 different az
        self.vpc = ec2.Vpc(
            self, "DataLakehouseVpc",
            vpc_name="data-lakehouse-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateway_provider=nat_provider,
            nat_gateways=1,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        self.hn_bronze_sg = ec2.SecurityGroup(
            self, "HnBronzeSg",
            vpc=self.vpc,
            security_group_name="hn-bronze-sg",
            description="HN bronze Lambda (HN API and S3 access)",
            allow_all_outbound=False,
        )

        self.lambda_s3_sg = ec2.SecurityGroup(
            self, "LambdaS3Sg",
            vpc=self.vpc,
            security_group_name="lambda-s3-sg",
            description="Lambdas that need S3 access only",
            allow_all_outbound=False,
        )

        self.notifications_sg = ec2.SecurityGroup(
            self, "NotificationsSg",
            vpc=self.vpc,
            security_group_name="notifications-sg",
            description="Notifications Lambda with Discord and SSM access",
            allow_all_outbound=False,
        )

        self.loader_sg = ec2.SecurityGroup(
            self, "LoaderSg",
            vpc=self.vpc,
            security_group_name="loader-sg",
            description="Loader Lambda - PostgreSQL access",
            allow_all_outbound=False,
        )

        self.ec2_sg = ec2.SecurityGroup(
            self, "Ec2SecurityGroup",
            vpc=self.vpc,
            security_group_name="ec2-sg",
            description="EC2 (Superset + PostgreSQL)",
            allow_all_outbound=True,
        )

        self.hn_bronze_sg.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HN API and S3",
        )

        self.notifications_sg.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(443),
            description="HTTPS Discord and SSM",
        )

        self.loader_sg.add_egress_rule(
            peer=self.ec2_sg,
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL na EC2",
        )

        self.ec2_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(22),
            description="SSH access",
        )
        self.ec2_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port.tcp(8088),
            description="Superset web UI",
        )
        self.ec2_sg.add_ingress_rule(
            peer=self.loader_sg,
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL accessible only by loader lambda",
        )
