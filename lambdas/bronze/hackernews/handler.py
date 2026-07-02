import os
import json
import boto3
import requests
from datetime import datetime, timedelta, timezone

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ["BRONZE_BUCKET"]
HN_API = "https://hn.algolia.com/api/v1/search_by_date"
HN_FIREBASE = "https://hacker-news.firebaseio.com/v0"

POST_TYPES = ["story", "ask_hn", "show_hn", "poll", "comment"]

# ID aktuelnog "Ask HN: Who is Hiring?" threada.
# Objavljuje se prvi ponedeljak svakog meseca — ovaj ID treba
# da se azurira mesecno. Jun 2026: 48357725
WHO_IS_HIRING_ID = 48747976


def fetch_by_type(tag: str, date_from: int, date_to: int) -> list:
    results = []
    page = 0
    while True:
        resp = requests.get(
            HN_API,
            params={
                "tags": tag,
                "numericFilters": [
                    f"created_at_i>{date_from}",
                    f"created_at_i<{date_to}",
                ],
                "hitsPerPage": 200,
                "page": page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("hits", []))
        if page >= min(body.get("nbPages", 1) - 1, 49):
            break
        page += 1
    return results


def fetch_who_is_hiring_comments(story_id: int, date_from: int, date_to: int) -> list:
    story_resp = requests.get(
        f"{HN_FIREBASE}/item/{story_id}.json",
        timeout=15,
    )
    story_resp.raise_for_status()
    story = story_resp.json()

    if not story or not story.get("kids"):
        return []

    job_items = []
    for kid_id in story["kids"]:
        try:
            item_resp = requests.get(
                f"{HN_FIREBASE}/item/{kid_id}.json",
                timeout=10,
            )
            item_resp.raise_for_status()
            item = item_resp.json()

            if not item or item.get("deleted") or item.get("dead"):
                continue

            item_time = item.get("time", 0)
            if date_from <= item_time <= date_to:
                job_items.append({
                    "objectID": str(item.get("id", "")),
                    "author": item.get("by"),
                    "created_at_i": item_time,
                    "created_at": datetime.fromtimestamp(item_time, tz=timezone.utc).isoformat(),
                    "comment_text": item.get("text"),
                    "_tags": ["comment", f"author_{item.get('by', '')}", f"story_{story_id}"],
                    "story_id": story_id,
                    "parent_id": story_id,
                    "points": None,
                    "_job_override": True,  # silver ce ga mapirati kao post_type='job'
                })
        except Exception:
            continue

    return job_items


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

    job_items = fetch_who_is_hiring_comments(WHO_IS_HIRING_ID, date_from, date_to)
    data.extend(job_items)
    print(f"  job (Who is Hiring Firebase): {len(job_items)} items")

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

    print(f"Uploaded {len(data)} total items to s3://{BUCKET_NAME}/{key}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "HackerNews bronze ingest successful",
            "records": len(data),
            "s3_key": key,
        }),
    }