from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct


class NetworkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC sa 2 public subnet-a u 2 različite AZ-a
        self.vpc = ec2.Vpc(
            self, "DataLakehouseVpc",
            vpc_name="data-lakehouse-vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
        )

        # VPC Gateway Endpoint za S3 (besplatan, privatan put do S3)
        self.vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # Security grupa za Lambda funkcije
        self.lambda_sg = ec2.SecurityGroup(
            self, "LambdaSecurityGroup",
            vpc=self.vpc,
            security_group_name="lambda-sg",
            description="Security group za Lambda funkcije",
            allow_all_outbound=True,
        )

        # Security grupa za EC2 (Superset + PostgreSQL)
        self.ec2_sg = ec2.SecurityGroup(
            self, "Ec2SecurityGroup",
            vpc=self.vpc,
            security_group_name="ec2-sg",
            description="Security group za EC2 (Superset + PostgreSQL)",
            allow_all_outbound=True,
        )

        # EC2 prihvata SSH samo sa konkretne IP adrese (zameni kasnije)
        # self.ec2_sg.add_ingress_rule(
        #     peer=ec2.Peer.ipv4("TVOJA_IP/32"),
        #     connection=ec2.Port.tcp(22),
        #     description="SSH pristup samo sa moje IP",
        # )

        # EC2 prihvata Superset (8088) sa interneta - za sada otvoreno za tim
        # self.ec2_sg.add_ingress_rule(
        #     peer=ec2.Peer.any_ipv4(),
        #     connection=ec2.Port.tcp(8088),
        #     description="Superset web UI",
        # )

        # EC2 prihvata PostgreSQL (5432) samo od Lambda funkcija
        self.ec2_sg.add_ingress_rule(
            peer=self.lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="PostgreSQL pristup samo od Lambda funkcija",
        )