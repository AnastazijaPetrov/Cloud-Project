#!/usr/bin/env python3
import os
import aws_cdk as cdk

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

storage = StorageStack(app, "StorageStack", env=env)
network = NetworkStack(app, "NetworkStack", env=env)

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

app.synth()