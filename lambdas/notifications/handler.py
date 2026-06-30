import os
import json
import urllib.request
import boto3

ssm = boto3.client("ssm")

WEBHOOK_PARAM_NAME = os.environ["DISCORD_WEBHOOK_PARAM"]

# Cache webhook URL preko Lambda warm invokacija
_webhook_url = None


def get_webhook_url():
    """Učitava webhook URL iz SSM Parameter Store-a (sa cache-om)."""
    global _webhook_url
    if _webhook_url is None:
        response = ssm.get_parameter(
            Name=WEBHOOK_PARAM_NAME,
            WithDecryption=True,
        )
        _webhook_url = response["Parameter"]["Value"]
    return _webhook_url


def format_message(event):
    """
    Formatira poruku za Discord na osnovu tipa event-a.
    Event može biti SNS poruka (CloudWatch alarm) ili EventBridge event
    (Step Function failure).
    """

    # CloudWatch alarm preko SNS-a
    if "Records" in event:
        sns_message = json.loads(event["Records"][0]["Sns"]["Message"])
        alarm_name = sns_message.get("AlarmName", "Unknown alarm")
        reason = sns_message.get("NewStateReason", "No reason provided")

        return {
            "title": f"AWS Lambda Failure: {alarm_name}",
            "description": reason,
            "color": 15158332,  # crvena
        }

    # Step Function failure event direktno
    if event.get("source") == "aws.states":
        detail = event.get("detail", {})
        execution_arn = detail.get("executionArn", "Unknown")
        status = detail.get("status", "Unknown")
        state_machine_name = execution_arn.split(":")[-2] if ":" in execution_arn else "Unknown"

        return {
            "title": f"Step Function {status}: {state_machine_name}",
            "description": f"Execution ARN: {execution_arn}",
            "color": 15158332,
        }

    # Fallback
    return {
        "title": "AWS Notification",
        "description": json.dumps(event)[:1500],
        "color": 15158332,
    }


def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)[:500]}")

    webhook_url = get_webhook_url()
    message = format_message(event)

    payload = {
        "embeds": [{
            "title": message["title"],
            "description": message["description"][:2000],
            "color": message["color"],
        }]
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            print(f"Discord webhook response: {status}")
    except Exception as e:
        print(f"Failed to send Discord webhook: {e}")
        raise

    return {"statusCode": 200}
