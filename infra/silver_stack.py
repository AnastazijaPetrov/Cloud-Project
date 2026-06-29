from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3 as s3,
    aws_ec2 as ec2,
    aws_events as events,
    aws_events_targets as targets,
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

        awswrangler_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "AwsWranglerLayer",
            "arn:aws:lambda:eu-central-1:336392948345:layer:AWSSDKPandas-Python311:24"
        )

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

        # FIX: PRIVATE_WITH_EGRESS umesto PUBLIC subneta.
        #
        # Lambda u public subnetu ne dobija automatski internet pristup i
        # krši principle least privilege iz spec tačke 7.
        # PRIVATE_WITH_EGRESS subnet koristi NAT Gateway za outbound pristup
        # internetu (potrebno za HN API pozive u normalize_hackernews).
        # S3 saobraćaj ide kroz VPC Gateway Endpoint (bez NAT-a, bez troška).
        #
        # Pretpostavka: VPC ima konfigurisane private subnete sa NAT Gateway-em
        # i S3 Gateway Endpoint. Ovo je standardni CDK VPC setup:
        #   ec2.Vpc(self, "Vpc", nat_gateways=1)
        # automatski kreira public + private_with_egress subnete.

        hn_lambda = _lambda.Function(
            self,
            "SilverHackerNewsLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            layers=[awswrangler_layer],
            code=_lambda.Code.from_asset(
                "lambdas/silver/normalize_hackernews",
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
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # FIX
            ),
            security_groups=[lambda_sg],
            # FIX: allow_public_subnet=True uklonjeno — ne treba u private subnetu
        )

        twitter_lambda = _lambda.Function(
            self,
            "SilverTwitterLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            layers=[awswrangler_layer],
            code=_lambda.Code.from_asset(
                "lambdas/silver/normalize_twitter",
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
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS  # FIX
            ),
            security_groups=[lambda_sg],
            # FIX: allow_public_subnet=True uklonjeno
        )

        hn_rule = events.Rule(
            self,
            "HackerNewsBronzeObjectCreatedRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [bronze_bucket.bucket_name]},
                    "object": {"key": [{"prefix": "hackernews/"}]},
                },
            ),
        )
        hn_rule.add_target(targets.LambdaFunction(hn_lambda))

        twitter_rule = events.Rule(
            self,
            "TwitterBronzeObjectCreatedRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [bronze_bucket.bucket_name]},
                    "object": {"key": [{"prefix": "twitter/"}]},
                },
            ),
        )
        twitter_rule.add_target(targets.LambdaFunction(twitter_lambda))

        # Eksportujemo lambde da bi ih StepFunctionsStack mogao koristiti
        self.hn_lambda = hn_lambda
        self.twitter_lambda = twitter_lambda