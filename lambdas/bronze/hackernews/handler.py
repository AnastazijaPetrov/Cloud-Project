import os
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone

s3_client = boto3.client("s3")

BUCKET_NAME = os.environ["BRONZE_BUCKET"]

HN_API = "https://hn.algolia.com/api/v1/search_by_date"

POST_TYPES = ["story", "ask_hn", "show_hn", "job", "poll", "comment"]


def fetch_by_type(tag: str, date_from: str, date_to: str) -> list:
    """
    Preuzima sve objave zadatog tipa za zadati vremenski opseg
    koristeći Algolia paginaciju.

    Algolia search_by_date parametri:
      - tags: tip objave (story, comment, job itd.)
      - numericFilters: Unix timestamp opseg
      - hitsPerPage: broj rezultata po stranici (max 1000 po Algolia limitu, ali
                     u praksi preporučeno 200 zbog stabilnosti)
      - page: broj stranice (0-indexed)
    """
    results = []
    page = 0

    while True:
        resp = requests.get(
            HN_API,
            params={
                "tags": tag,
                "numericFilters": f"created_at_i>{date_from},created_at_i<{date_to}",
                "hitsPerPage": 200,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()

        hits = body.get("hits", [])
        results.extend(hits)

        if page >= body.get("nbPages", 1) - 1:
            break

        page += 1

    return results


def lambda_handler(event, context):
    print("Fetching HackerNews data via Algolia API...")

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    date_from = int(yesterday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    date_to   = int(yesterday.replace(hour=23, minute=59, second=59, microsecond=0).timestamp())

    data = []
    for tag in POST_TYPES:
        items = fetch_by_type(tag, date_from, date_to)
        data.extend(items)
        print(f"  {tag}: {len(items)} items")

    now = datetime.now(timezone.utc)
    key = (
        f"hackernews/"
        f"year={now.year}/month={now.month:02d}/day={now.day:02d}/hn.json"
    )

    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data),
        ContentType="application/json",
    )

    print(f"Uploaded {len(data)} HackerNews items to s3://{BUCKET_NAME}/{key}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "HackerNews bronze ingest successful",
            "records": len(data),
            "s3_key": key,
        }),
    }