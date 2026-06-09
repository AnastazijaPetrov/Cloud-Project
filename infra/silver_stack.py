from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_ec2 as ec2,
)
from constructs import Construct


class SilverStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        bronze_bucket: s3.IBucket,
        silver_bucket: s3.IBucket,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        role = iam.Role(
            self,
            "SilverLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ]
        )

        bronze_bucket.grant_read(role)
        silver_bucket.grant_read_write(role)

        # HN Lambda
        hn_lambda = _lambda.Function(
            self,
            "SilverHackerNewsLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/silver/normalize_hackernews",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=role,
            environment={
                "SILVER_BUCKET": silver_bucket.bucket_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[lambda_sg],
            allow_public_subnet=True,
        )

        # Twitter Lambda
        twitter_lambda = _lambda.Function(
            self,
            "SilverTwitterLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/silver/normalize_twitter",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.minutes(15),
            memory_size=1024,
            role=role,
            environment={
                "SILVER_BUCKET": silver_bucket.bucket_name,
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[lambda_sg],
            allow_public_subnet=True,
        )

        bronze_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(hn_lambda),
            s3.NotificationKeyFilter(prefix="hackernews/")
        )

        bronze_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(twitter_lambda),
            s3.NotificationKeyFilter(prefix="twitter/")
        )