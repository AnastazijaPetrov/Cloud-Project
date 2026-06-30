#!/usr/bin/env python3
import os
import aws_cdk as cdk

from infra.gold_stack import GoldStack
from infra.notifications_stack import NotificationsStack
from infra.step_functions_stack import StepFunctionsStack
from infra.storage_stack import StorageStack
from infra.network_stack import NetworkStack
from infra.bronze_stack import BronzeStack
from infra.oidc_stack import OidcStack
from infra.silver_stack import SilverStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    # region=os.getenv('CDK_DEFAULT_REGION')
    region="eu-central-1"
)

GITHUB_OWNER = "AnastazijaPetrov"
GITHUB_REPO = "Cloud-Project"

oidc = OidcStack(
    app, "OidcStack",
    github_owner=GITHUB_OWNER,
    github_repo=GITHUB_REPO,
    env=env,
)
network = NetworkStack(app, "NetworkStack", env=env)
storage = StorageStack(app, "StorageStack", env=env)
bronze = BronzeStack(
    app, "BronzeStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bronze_bucket=storage.bronze_bucket,
    env=env,
)
 
silver = SilverStack(
    app, "SilverStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    bronze_bucket=storage.bronze_bucket,
    silver_bucket=storage.silver_bucket,
    env=env,
)
 
gold = GoldStack(
    app, "GoldStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    silver_bucket=storage.silver_bucket,
    gold_bucket=storage.gold_bucket,
    env=env,
)

step_functions = StepFunctionsStack(
    app, "StepFunctionsStack",
    bronze_bucket=storage.bronze_bucket,
    hn_silver_lambda=silver.hn_lambda,
    twitter_silver_lambda=silver.twitter_lambda,
    gold_lambda=gold.gold_lambda,
    env=env,
)

NotificationsStack(
    app, "NotificationsStack",
    monitored_lambdas=[
        bronze.hn_lambda,
        bronze.twitter_lambda,
        silver.hn_lambda,
        silver.twitter_lambda,
        gold.gold_lambda,
    ],
    state_machine=step_functions.state_machine,
    env=env,
)
 
app.synth()