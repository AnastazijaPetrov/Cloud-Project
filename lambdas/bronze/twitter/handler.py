import os
import json
import boto3
from datetime import datetime

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['BRONZE_BUCKET']

def lambda_handler(event, context):
    print("Lambda started")

    with open("data/twitter_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    now = datetime.utcnow()

    key = f"twitter/bronze/year={now.year}/month={now.month:02d}/day={now.day:02d}/twitter.json"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data),
        ContentType="application/json"
    )

    print(f"Uploaded {len(data)} records to {BUCKET_NAME}/{key}")
    print("Lambda finished")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Twitter bronze ingest successful",
            "records": len(data),
            "s3_key": key
        })
    }

if __name__ == "__main__":
    print("STARTING LOCAL TEST")
    lambda_handler(None, None)
    print("DONE")