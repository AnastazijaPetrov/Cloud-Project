import os
import json
import urllib.parse

import boto3
import pandas as pd
import awswrangler as wr

s3 = boto3.client("s3")

SILVER_BUCKET = os.environ["SILVER_BUCKET"]


def lambda_handler(event, context):
    all_posts = []
    all_users = []

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])

        obj = s3.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())

        for item in data:
            created_at = pd.to_datetime(item.get("created_at"), utc=True, errors="coerce")
            content_text = item.get("clean_tweet") or item.get("original_text")

            post_id = str(item.get("post_id") or item.get("id"))
            author_username = item.get("original_author")

            all_posts.append({
                "post_id": post_id,
                "platform": "X",
                "author_username": author_username,
                "content_text": content_text,
                "title": None,
                "created_at": created_at,
                "post_type": "tweet",
                "score": None,
                "favorite_count": item.get("favorite_count"),
                "retweet_count": item.get("retweet_count"),
                "lang": item.get("lang"),
                "hashtags": item.get("hashtags"),
                "user_mentions": item.get("user_mentions"),
                "place": item.get("place"),
                "sentiment": item.get("sentiment"),
                "kids_count": None,
            })

            if author_username:
                followers_count = item.get("followers_count")
                is_verified = item.get("is_verified")

                all_users.append({
                    "username": author_username,
                    "platform": "X",
                    "karma_score": None,
                    "followers_count": int(followers_count) if followers_count not in [None, ""] else None,
                    "is_verified": bool(is_verified) if is_verified not in [None, ""] else None,
                    "created_at": None,
                })

    df_posts = pd.DataFrame(all_posts)
    df_users = pd.DataFrame(all_users)

    if not df_posts.empty:
        df_posts = df_posts.drop_duplicates(subset=["platform", "post_id"])
        df_posts = df_posts.dropna(subset=["created_at"])

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

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Twitter silver normalization successful",
            "posts": len(df_posts),
            "users": len(df_users),
        }),
    }