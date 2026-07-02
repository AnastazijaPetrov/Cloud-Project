from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
)
from constructs import Construct


class StepFunctionsStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        bronze_bucket: s3.IBucket,
        hn_silver_lambda: _lambda.IFunction,
        twitter_silver_lambda: _lambda.IFunction,
        gold_lambda: _lambda.IFunction,
        loader_lambda: _lambda.IFunction,
        **kwargs,
    ):
        super().__init__(scope, construct_id, **kwargs)

        normalize_hn = tasks.LambdaInvoke(
            self,
            "NormalizeHackerNews",
            lambda_function=hn_silver_lambda,
            payload=sfn.TaskInput.from_json_path_at("$"),
            result_path="$.hn_result",
        )

        normalize_twitter = tasks.LambdaInvoke(
            self,
            "NormalizeTwitter",
            lambda_function=twitter_silver_lambda,
            payload=sfn.TaskInput.from_json_path_at("$"),
            result_path="$.twitter_result",
        )

        build_gold = tasks.LambdaInvoke(
            self,
            "BuildGoldLayer",
            lambda_function=gold_lambda,
            payload=sfn.TaskInput.from_object({}),
            result_path="$.gold_result",
        )

        load_to_postgres = tasks.LambdaInvoke(
            self,
            "LoadToPostgres",
            lambda_function=loader_lambda,
            payload=sfn.TaskInput.from_object({}),
            result_path="$.loader_result",
        )

        parallel_silver = sfn.Parallel(
            self,
            "ParallelSilverNormalization",
            result_path="$.silver_results",
        )
        parallel_silver.branch(normalize_hn)
        parallel_silver.branch(normalize_twitter)

        definition = parallel_silver.next(build_gold).next(load_to_postgres)

        self.state_machine = sfn.StateMachine(
            self,
            "SilverGoldPipeline",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(45),
        )

        bronze_rule = events.Rule(
            self,
            "BronzeObjectCreatedRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [bronze_bucket.bucket_name]},
                },
            ),
        )
        
        rule_role = iam.Role(
            self,
            "BronzeRuleRole",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
        )
        self.state_machine.grant_start_execution(rule_role)

        bronze_rule.add_target(
            targets.SfnStateMachine(
                self.state_machine,
                role=rule_role,
            )
        )
