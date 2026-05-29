import os
import json
import boto3
import requests
from datetime import datetime

s3 = boto3.client("s3")
BUCKET = os.environ["BRONZE_BUCKET"]

def lambda_handler(event, context):

    print("HackerNews ingestion started")

    top_ids = requests.get(
        "https://hacker-news.firebaseio.com/v0/topstories.json"
    ).json()

    data = []

    for story_id in top_ids[:100]:

        item = requests.get(
            f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        ).json()

        if item:
            data.append(item)

    now = datetime.utcnow()

    key = (
        f"bronze/hackernews/"
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}/hn.json"
    )

    s3.put_object(
        Bucket=BUCKET,
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