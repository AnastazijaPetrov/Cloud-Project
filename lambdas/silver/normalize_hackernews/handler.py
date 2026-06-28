import os
import json
import html
import urllib.parse
from datetime import datetime, timezone

import boto3
import pandas as pd
import awswrangler as wr
from bs4 import BeautifulSoup

s3 = boto3.client("s3")

SILVER_BUCKET = os.environ["SILVER_BUCKET"]


def clean_html(value):
    if not value:
        return None

    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = " ".join(text.split())

    return text or None


def parse_hn_time(value):
    if value is None:
        return None

    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def lambda_handler(event, context):
    all_posts = []
    all_users = []
    all_post_children = []

    for bucket, key in iter_s3_objects(event):

        obj = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())

        for item in data:
            post_id = str(item.get("id"))
            author_username = item.get("by")
            created_at = parse_hn_time(item.get("time"))

            content_text = clean_html(item.get("text")) or clean_html(item.get("title"))

            all_posts.append({
                "post_id": post_id,
                "platform": "HackerNews",
                "author_username": author_username,
                "content_text": content_text,
                "title": clean_html(item.get("title")),
                "created_at": created_at,
                "post_type": item.get("type"),
                "score": item.get("score"),
                "favorite_count": None,
                "retweet_count": None,
                "lang": None,
                "hashtags": None,
                "user_mentions": None,
                "place": None,
                "sentiment": None,
                "kids_count": len(item.get("kids", [])),
            })

            if author_username:
                all_users.append({
                    "username": author_username,
                    "platform": "HackerNews",
                    "karma_score": None,
                    "followers_count": None,
                    "is_verified": None,
                    "created_at": None,
                })

            for child_id in item.get("kids", []):
                all_post_children.append({
                    "parent_post_id": post_id,
                    "child_post_id": str(child_id),
                    "platform": "HackerNews",
                })

    df_posts = pd.DataFrame(all_posts)
    df_users = pd.DataFrame(all_users)
    df_post_children = pd.DataFrame(all_post_children)

    if not df_posts.empty:
        df_posts = df_posts.drop_duplicates(subset=["platform", "post_id"])
        df_posts["created_at"] = pd.to_datetime(df_posts["created_at"], utc=True)
        df_posts["year"] = df_posts["created_at"].dt.year
        df_posts["month"] = df_posts["created_at"].dt.month
        df_posts["day"] = df_posts["created_at"].dt.day

        wr.s3.to_parquet(
            df=df_posts,
            path=f"s3://{SILVER_BUCKET}/posts/",
            dataset=True,
            mode="overwrite_partitions",
            partition_cols=["platform", "year", "month", "day"],
        )

    if not df_users.empty:
        df_users = df_users.drop_duplicates(subset=["platform", "username"])

        wr.s3.to_parquet(
            df=df_users,
            path=f"s3://{SILVER_BUCKET}/users/",
            dataset=True,
            mode="append",
            partition_cols=["platform"],
        )

    if not df_post_children.empty:
        df_post_children = df_post_children.drop_duplicates(
            subset=["platform", "parent_post_id", "child_post_id"]
        )

        wr.s3.to_parquet(
            df=df_post_children,
            path=f"s3://{SILVER_BUCKET}/post_children/",
            dataset=True,
            mode="append",
            partition_cols=["platform"],
        )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "HackerNews silver normalization successful",
            "posts": len(df_posts),
            "users": len(df_users),
            "post_children": len(df_post_children),
        }),
    }

def iter_s3_objects(event):
    if "Records" in event:
        for record in event["Records"]:
            yield (
                record["s3"]["bucket"]["name"],
                urllib.parse.unquote_plus(record["s3"]["object"]["key"]),
            )
    else:
        yield (
            event["detail"]["bucket"]["name"],
            urllib.parse.unquote_plus(event["detail"]["object"]["key"]),
        )