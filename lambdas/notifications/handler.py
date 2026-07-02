import os
import json
import urllib.request
import boto3

ssm = boto3.client("ssm")

WEBHOOK_PARAM_NAME = os.environ["DISCORD_WEBHOOK_PARAM"]
REGION = os.environ.get("AWS_REGION_NAME", "eu-central-1")

_webhook_url = None


def get_webhook_url():
    global _webhook_url
    if _webhook_url is None:
        response = ssm.get_parameter(
            Name=WEBHOOK_PARAM_NAME,
            WithDecryption=True,
        )
        _webhook_url = response["Parameter"]["Value"]
    return _webhook_url


def build_cloudwatch_url(log_group: str) -> str:
    encoded = log_group.replace("/", "$252F")
    return (
        f"https://{REGION}.console.aws.amazon.com/cloudwatch/home"
        f"?region={REGION}#logsV2:log-groups/log-group/{encoded}"
    )


def parse_cloudwatch_alarm(sns_message: dict) -> dict:
    """
    CloudWatch alarm SNS poruka ima oblik:
    {
        "AlarmName": "hackernews-ingest-errors",
        "NewStateReason": "Threshold Crossed: 1 datapoint...",
        "Trigger": {
            "Dimensions": [{"name": "FunctionName", "value": "hackernews-ingest"}]
        }
    }
    """
    alarm_name = sns_message.get("AlarmName", "Unknown")
    reason = sns_message.get("NewStateReason", "No reason provided")

    function_name = alarm_name.replace("-errors", "")

    log_group = f"/aws/lambda/{function_name}"
    cw_url = build_cloudwatch_url(log_group)

    return {
        "title": f"Lambda Failure: {function_name}",
        "description": f"{reason}\n\n[View CloudWatch logs]({cw_url})",
        "color": 15158332,  # crvena
    }


def parse_step_function_failure(sns_message: dict) -> dict:
    """
    EventBridge → SNS poruka za Step Function failure ima oblik:
    {
        "source": "aws.states",
        "detail": {
            "executionArn": "arn:aws:states:eu-central-1:...:execution:Pipeline:abc",
            "stateMachineArn": "...",
            "status": "FAILED",
            "name": "abc-123"
        }
    }
    """
    detail = sns_message.get("detail", {})
    execution_arn = detail.get("executionArn", "Unknown")
    status = detail.get("status", "Unknown")
    name = detail.get("name", "Unknown")

    state_machine_name = "Unknown"
    if ":execution:" in execution_arn:
        parts = execution_arn.split(":execution:")
        if len(parts) > 1:
            state_machine_name = parts[1].split(":")[0]

    return {
        "title": f"Step Function {status}: {state_machine_name}",
        "description": f"Execution: {name}\nARN: `{execution_arn}`",
        "color": 15158332,
    }


def format_message(event):
    """
    Formatira poruku za Discord na osnovu tipa event-a.
    Svi event-i dolaze kroz SNS topic.
    """
    if "Records" not in event:
        return {
            "title": "AWS Notification (Unknown format)",
            "description": json.dumps(event)[:1500],
            "color": 15158332,
        }

    sns_message_raw = event["Records"][0]["Sns"]["Message"]
    try:
        sns_message = json.loads(sns_message_raw)
    except json.JSONDecodeError:
        return {
            "title": "AWS Notification (Raw)",
            "description": sns_message_raw[:1500],
            "color": 15158332,
        }

    if "AlarmName" in sns_message:
        return parse_cloudwatch_alarm(sns_message)
    if sns_message.get("source") == "aws.states":
        return parse_step_function_failure(sns_message)

    return {
        "title": "AWS Notification",
        "description": json.dumps(sns_message)[:1500],
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
        headers={"Content-Type": "application/json",
                 "User-Agent": "Mozilla/5.0"},
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
