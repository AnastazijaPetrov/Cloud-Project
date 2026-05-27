#!/usr/bin/env python3
import os
import aws_cdk as cdk

from infra.storage_stack import StorageStack
from infra.network_stack import NetworkStack
from infra.bronze_stack import BronzeStack

app = cdk.App()

env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION')
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

app.synth()