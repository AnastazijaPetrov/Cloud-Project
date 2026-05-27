from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class BronzeStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.IVpc,
        lambda_sg: ec2.ISecurityGroup,
        bronze_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ===== HackerNews Lambda =====
        hn_role = iam.Role(
            self, "HackerNewsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Least privilege: dozvoli upis SAMO u hackernews/ prefiks bronze bucket-a
        bronze_bucket.grant_put(hn_role, objects_key_pattern="hackernews/*")

        hn_lambda = _lambda.Function(
            self, "HackerNewsIngestLambda",
            function_name="hackernews-ingest",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/bronze/hackernews",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                "BRONZE_BUCKET": bronze_bucket.bucket_name,
            },
            role=hn_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[lambda_sg],
            allow_public_subnet=True,
        )

        # ===== Twitter Lambda =====
        twitter_role = iam.Role(
            self, "TwitterLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

        # Least privilege: dozvoli upis SAMO u twitter/ prefiks bronze bucket-a
        bronze_bucket.grant_put(twitter_role, objects_key_pattern="twitter/*")

        twitter_lambda = _lambda.Function(
            self, "TwitterIngestLambda",
            function_name="twitter-ingest",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/bronze/twitter",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash", "-c",
                        "pip install --no-cache -r requirements.txt -t /asset-output && cp -r . /asset-output"
                    ],
                ),
            ),
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                "BRONZE_BUCKET": bronze_bucket.bucket_name,
            },
            role=twitter_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[lambda_sg],
            allow_public_subnet=True,
        )

        # ===== EventBridge Cron - svaki dan u 2:00 UTC =====
        daily_schedule = events.Rule(
            self, "DailyIngestSchedule",
            rule_name="daily-bronze-ingest",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",
                day="*",
                month="*",
                year="*",
            ),
        )

        daily_schedule.add_target(targets.LambdaFunction(hn_lambda))
        daily_schedule.add_target(targets.LambdaFunction(twitter_lambda))