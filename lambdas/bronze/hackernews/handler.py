import os
import json
import boto3
from datetime import datetime

s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BRONZE_BUCKET"]

def lambda_handler(event, context):

    print("HackerNews bronze ingestion started")

    with open("data/hn_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    now = datetime.utcnow()

    key = (
        f"bronze/hackernews/"
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