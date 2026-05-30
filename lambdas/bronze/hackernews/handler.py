import os
import json
import boto3
from datetime import datetime, timedelta

s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BRONZE_BUCKET"]

def lambda_handler(event, context):

    print("HackerNews bronze ingestion started")

    yesterday = datetime.utcnow() - timedelta(days=1)
    filename = f"hn_{yesterday.strftime('%Y%m%d')}.json"

    with open(f"data/{filename}", "r") as f:
        data = json.load(f)

    now = datetime.utcnow()

    key = (
        f"hackernews/"
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}/hn.json"
    )

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data),
        ContentType="application/json"
    )

    print(f"Uploaded {len(data)} HackerNews items")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "HackerNews bronze ingest successful",
            "records": len(data),
            "s3_key": key
        })
    }