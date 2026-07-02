from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ec2 as ec2,
)
from constructs import Construct


POSTGRES_PASSWORD_PARAM = "/cloud-project/postgres-password"


class LoaderStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        gold_bucket: s3.IBucket,
        postgres_host: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        awswrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "AwsWranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python311:24",
        )

        role = iam.Role(
            self,
            "LoaderLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        gold_bucket.grant_read(role)

        role.add_to_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter{POSTGRES_PASSWORD_PARAM}",
            ],
        ))

        role.add_to_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "kms:ViaService": f"ssm.{self.region}.amazonaws.com"
                },
            },
        ))

        self.loader_lambda = _lambda.Function(
            self,
            "LoaderLambda",
            function_name="postgres-loader",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            layers=[awswrangler_layer],
            code=_lambda.Code.from_asset(
                "lambdas/loader",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.minutes(10),
            memory_size=1024,
            role=role,
            environment={
                "GOLD_BUCKET": gold_bucket.bucket_name,
                "POSTGRES_HOST": postgres_host,
                "POSTGRES_PASSWORD_PARAM": POSTGRES_PASSWORD_PARAM,
                "POSTGRES_DB": "gold_metrics",
                "POSTGRES_USER": "cloud_project",
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[lambda_sg],
        )