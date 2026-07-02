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
        hn_lambda_sg: ec2.ISecurityGroup,
        twitter_lambda_sg: ec2.ISecurityGroup,
        bronze_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # hackernews lambda
        hn_role = iam.Role(
            self, "HackerNewsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

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
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[hn_lambda_sg],
        )

        # twitter lambda
        twitter_role = iam.Role(
            self, "TwitterLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                ),
            ],
        )

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
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_groups=[twitter_lambda_sg],
        )

        # Event bridge cron at 02:00 utc used by both lambdas
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

        self.hn_lambda = hn_lambda
        self.twitter_lambda = twitter_lambda