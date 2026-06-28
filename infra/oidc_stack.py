from aws_cdk import (
    Stack,
    aws_iam as iam,
)
from constructs import Construct


class OidcStack(Stack):
    """
    OIDC trust između GitHub Actions i AWS-a.
    Omogucava GitHub workflow-ima da preuzmu IAM role bez Access Key-eva.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        github_owner: str,
        github_repo: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        github_provider = iam.OpenIdConnectProvider(
            self,
            "GitHubOidcProvider",
            url="https://token.actions.githubusercontent.com",
            client_ids=["sts.amazonaws.com"],
            thumbprints=["6938fd4d98bab03faadb97b34396831e3780aea1"]
        )

        github_principal = iam.OpenIdConnectPrincipal(
            github_provider,
            conditions={
                "StringEquals": {
                "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                },
                "StringLike": {
                "token.actions.githubusercontent.com:sub": f"repo:{github_owner}/{github_repo}:*",
                },
            },
        )

        self.github_actions_role = iam.Role(
            self, "GitHubActionsRole",
            role_name="github-actions-deploy-role",
            assumed_by=github_principal,
            description="Role za GitHub Actions CDK deploy",
            max_session_duration=Stack.of(self).node.try_get_context("session_duration") or None,
        )

        self.github_actions_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )