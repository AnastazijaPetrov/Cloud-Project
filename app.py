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
from infra.ec2_stack import Ec2Stack
from infra.loader_stack import LoaderStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region="eu-central-1"
)

GITHUB_OWNER = "AnastazijaPetrov"
GITHUB_REPO = "Cloud-Project"
SSH_KEY_PAIR_NAME = "cloud-project-key"

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

ec2 = Ec2Stack(
    app, "Ec2Stack",
    vpc=network.vpc,
    ec2_sg=network.ec2_sg,
    key_pair_name=SSH_KEY_PAIR_NAME,
    env=env,
)

loader = LoaderStack(
    app, "LoaderStack",
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    gold_bucket=storage.gold_bucket,
    postgres_host=ec2.instance.instance_private_ip,
    env=env,
)

step_functions = StepFunctionsStack(
    app, "StepFunctionsStack",
    bronze_bucket=storage.bronze_bucket,
    hn_silver_lambda=silver.hn_lambda,
    twitter_silver_lambda=silver.twitter_lambda,
    gold_lambda=gold.gold_lambda,
    loader_lambda=loader.loader_lambda,
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
        loader.loader_lambda,
    ],
    state_machine=step_functions.state_machine,
    vpc=network.vpc,
    lambda_sg=network.lambda_sg,
    env=env,
)

app.synth()