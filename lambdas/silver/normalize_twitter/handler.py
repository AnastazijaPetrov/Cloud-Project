import os
import json
import urllib.parse
import boto3
import pandas as pd
import awswrangler as wr

s3_client = boto3.client("s3")

SILVER_BUCKET = os.environ["SILVER_BUCKET"]

def safe_float(x):
    try:
        if x is None or x == "" or x == "null":
            return None
        return float(x)
    except:
        return None


def safe_bool(x):
    if x in [True, "true", "True", 1, "1"]:
        return True
    if x in [False, "false", "False", 0, "0", None, ""]:
        return False
    return None

def iter_s3_objects(event):
    if "Records" in event:
        for record in event["Records"]:
            yield (
                record["s3"]["bucket"]["name"],
                urllib.parse.unquote_plus(record["s3"]["object"]["key"]),
            )
        return

    if "detail" in event:
        yield (
            event["detail"]["bucket"]["name"],
            urllib.parse.unquote_plus(event["detail"]["object"]["key"]),
        )
        return

    raise ValueError(f"Unsupported event format: {json.dumps(event)[:500]}")

def lambda_handler(event, context):
    print("Twitter Silver Lambda triggered")

    all_posts = []
    all_users = []

    for bucket, key in iter_s3_objects(event):
        print(f"Processing s3://{bucket}/{key}")

        obj = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())

        if isinstance(data, dict):
            data = data.get("data") or data.get("tweets") or []

        seen_users = {}

        for item in data:
            post_id = str(item.get("post_id") or item.get("id"))
            author_username = item.get("original_author")

            created_at = pd.to_datetime(
                item.get("created_at"), utc=True, errors="coerce"
            )

            content_text = item.get("clean_tweet") or item.get("original_text")

            all_posts.append({
                "post_id": post_id,
                "platform": "Twitter",
                "author_username": author_username,
                "content_text": content_text,
                "title": None,
                "created_at": created_at,
                "post_type": "tweet",
                "score": None,
                "favorite_count": safe_float(item.get("favorite_count")),
                "retweet_count": safe_float(item.get("retweet_count")),
                "lang": item.get("lang"),
                "hashtags": item.get("hashtags"),
                "user_mentions": item.get("user_mentions"),
                "place": item.get("place"),
                "sentiment": item.get("sentiment"),
                "kids_count": None,
            })

            if author_username and author_username not in seen_users:

                raw_followers = item.get("followers_count")
                raw_verified = item.get("is_verified")

                seen_users[author_username] = {
                    "username": author_username,
                    "platform": "Twitter",
                    "karma_score": None,
                    "followers_count": safe_float(raw_followers),
                    "is_verified": safe_bool(raw_verified),
                    "created_at": pd.to_datetime(
                        item.get("user_created_at")
                        or item.get("account_created_at"),
                        utc=True,
                        errors="coerce"
                    ),
                }

        all_users.extend(seen_users.values())

    df_posts = pd.DataFrame(all_posts)
    df_users = pd.DataFrame(all_users)

    if df_posts.empty:
        print("No posts found - exiting")
        return {"statusCode": 200, "body": "No posts"}

    df_posts = df_posts.drop_duplicates(subset=["platform", "post_id"])
    df_posts = df_posts.dropna(subset=["created_at"])

    df_posts["created_at"] = pd.to_datetime(df_posts["created_at"], utc=True)
    df_posts["year"] = df_posts["created_at"].dt.year
    df_posts["month"] = df_posts["created_at"].dt.month
    df_posts["day"] = df_posts["created_at"].dt.day

    df_posts["hashtags"] = df_posts["hashtags"].apply(
        lambda x: json.dumps(x) if isinstance(x, list) else (x if isinstance(x, str) else None)
    )
    df_posts["user_mentions"] = df_posts["user_mentions"].apply(
        lambda x: json.dumps(x) if isinstance(x, list) else (x if isinstance(x, str) else None)
    )

    wr.s3.to_parquet(
        df=df_posts,
        path=f"s3://{SILVER_BUCKET}/posts/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["platform", "year", "month", "day"],
    )

    if not df_users.empty:
        df_users = df_users.drop_duplicates(subset=["platform", "username"])
        df_users["followers_count"] = pd.to_numeric(df_users["followers_count"], errors="coerce").astype("Float64")
        df_users["karma_score"] = pd.to_numeric(df_users["karma_score"], errors="coerce").astype("Float64")
        df_users["is_verified"] = df_users["is_verified"].astype("boolean")

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