from aws_cdk import (
    Stack,
    Duration,
    BundlingOptions,
    aws_lambda as _lambda,
    aws_lambda_destinations as destinations,
    aws_iam as iam,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subs,
    aws_events as events,
    aws_events_targets as targets,
    aws_stepfunctions as sfn,
    aws_ec2 as ec2,
)
from constructs import Construct

DISCORD_WEBHOOK_PARAM_NAME = "/cloud-project/discord-webhook-url"

class NotificationsStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            monitored_lambdas: list[_lambda.IFunction],
            state_machine: sfn.IStateMachine,
            vpc: ec2.IVpc,
            lambda_sg: ec2.ISecurityGroup,
            **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.alerts_topic = sns.Topic(
            self, "AlertsTopic",
            topic_name="cloud-project-alerts",
            display_name="Cloud Project Alerts",
        )
        
        self.alerts_topic.add_to_resource_policy(iam.PolicyStatement(
            actions=["sns:Publish"],
            principals=[
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("events.amazonaws.com")
            ],
            resources=[self.alerts_topic.topic_arn],
        ))

        notification_lambda = _lambda.Function(
            self, "DiscordNotificationLambda",
            function_name="discord-notification",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset(
                "lambdas/notifications",
                bundling=BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_11.bundling_image,
                    command=["bash", "-c", "cp -r . /asset-output"],
                ),
            ),
            timeout=Duration.seconds(30),
            memory_size=128,
            environment={
                "DISCORD_WEBHOOK_PARAM": DISCORD_WEBHOOK_PARAM_NAME,
                "AWS_REGION_NAME": self.region,
            },
        )

        notification_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter{DISCORD_WEBHOOK_PARAM_NAME}",
            ],
        ))

        notification_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["kms:Decrypt"],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "kms:ViaService": f"ssm.{self.region}.amazonaws.com"
                },
                "ForAnyValue:StringEquals": {
                    "kms:ResourceAliases": "alias/aws/ssm"
                }
            },
        ))

        self.alerts_topic.add_subscription(
            sns_subs.LambdaSubscription(notification_lambda)
        )

        for fn in monitored_lambdas:
            fn.configure_async_invoke(
                retry_attempts=0,
                on_failure=destinations.SnsDestination(self.alerts_topic)
            )

        step_function_failure_rule = events.Rule(
            self, "StepFunctionFailureRule",
            rule_name="step-function-failure-rule",
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail_type=["Step Functions Execution Status Change"],
                detail={
                    "status": ["FAILED", "TIMED_OUT", "ABORTED"],
                },
            ),
        )
        step_function_failure_rule.add_target(targets.SnsTopic(self.alerts_topic))