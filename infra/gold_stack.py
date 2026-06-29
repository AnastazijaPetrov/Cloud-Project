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


class GoldStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        silver_bucket: s3.IBucket,
        gold_bucket: s3.IBucket,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        awswrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "AwsWranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python311:24",
        )

        role = iam.Role(
            self,
            "GoldLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )

        silver_bucket.grant_read(role)
        gold_bucket.grant_read_write(role)

        self.gold_lambda = _lambda.Function(
            self,
            "GoldLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            layers=[awswrangler_layer],
            code=_lambda.Code.from_asset(
                "lambdas/gold",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=["bash", "-c", "cp -r . /asset-output"],
                ),
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=role,
            environment={
                "SILVER_BUCKET": silver_bucket.bucket_name,
                "GOLD_BUCKET": gold_bucket.bucket_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[lambda_sg],
            allow_public_subnet=True,
        )