import os
import json
import html
import urllib.parse
from datetime import datetime, timezone

import boto3
import pandas as pd
import awswrangler as wr
from bs4 import BeautifulSoup
import requests

HN_USER_API = "https://hn.algolia.com/api/v1/users/"

s3_client = boto3.client("s3")

SILVER_BUCKET = os.environ["SILVER_BUCKET"]


def fetch_user_karma(username: str):
    try:
        resp = requests.get(f"{HN_USER_API}{username}", timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("karma")
    except:
        return None


def clean_html(value):
    if not value:
        return None
    text = html.unescape(str(value))
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = " ".join(text.split())
    return text or None


def parse_post_type(tags: list) -> str | None:
    """
    Algolia _tags field contains a list of tags like:
    ["story", "author_pg", "story_123456"]         -> story
    ["story", "show_hn", "author_x", "story_123"]  -> show_hn  (FIX: prioritize specific types)
    ["story", "ask_hn", "author_x", "story_123"]   -> ask_hn
    ["job", "author_x", "story_123"]               -> job
    ["comment", "author_x", "story_123"]           -> comment
    ["poll", "author_x", "story_123"]              -> poll

    Priority order matters: more specific types must come before generic "story",
    because Algolia includes both "story" and "show_hn"/"ask_hn" in the same _tags list.
    Without priority, "story" would always win since it appears first.
    """
    # More specific types take priority over the generic "story" tag
    priority_types = ["ask_hn", "show_hn", "job", "poll", "comment", "story"]
    tag_set = set(tags or [])
    for t in priority_types:
        if t in tag_set:
            return t
    return None


def lambda_handler(event, context):
    all_posts = []
    all_users = []
    all_post_children = []

    for bucket, key in iter_s3_objects(event):
        obj = s3_client.get_object(Bucket=bucket, Key=key)
        data = json.loads(obj["Body"].read())

        seen_users = {}

        for item in data:
            post_id         = str(item.get("objectID") or item.get("id", ""))
            author_username = item.get("author") or item.get("by")
            post_type       = parse_post_type(item.get("_tags", [])) or item.get("type")
            score           = item.get("points") or item.get("score")

            raw_time = item.get("created_at_i")
            if raw_time is not None:
                created_at = datetime.fromtimestamp(int(raw_time), tz=timezone.utc)
            else:
                created_at = pd.to_datetime(
                    item.get("created_at"), utc=True, errors="coerce"
                )

            content_text = (
                clean_html(item.get("story_text"))
                or clean_html(item.get("comment_text"))
                or clean_html(item.get("text"))
                or clean_html(item.get("title"))
            )

            children = item.get("children") or item.get("kids") or []

            all_posts.append({
                "post_id":        post_id,
                "platform":       "HackerNews",
                "author_username": author_username,
                "content_text":   content_text,
                "title":          clean_html(item.get("title")),
                "created_at":     created_at,
                "post_type":      post_type,
                "score":          score,
                "favorite_count": None,
                "retweet_count":  None,
                "lang":           None,
                "hashtags":       None,
                "user_mentions":  None,
                "place":          None,
                "sentiment":      None,
                "kids_count":     len(children),
            })

            if author_username and author_username not in seen_users:
                karma = fetch_user_karma(author_username)
                seen_users[author_username] = {
                    "username":        author_username,
                    "platform":        "HackerNews",
                    "karma_score":     karma,
                    "followers_count": None,
                    "is_verified":     None,
                    "created_at":      None,
                }

            for child_id in children:
                all_post_children.append({
                    "parent_post_id": post_id,
                    "child_post_id":  str(child_id),
                    "platform":       "HackerNews",
                })

        all_users.extend(seen_users.values())

    df_posts        = pd.DataFrame(all_posts)
    df_users        = pd.DataFrame(all_users)
    df_post_children = pd.DataFrame(all_post_children)

    if not df_posts.empty:
        df_posts = df_posts.drop_duplicates(subset=["platform", "post_id"])
        df_posts["created_at"] = pd.to_datetime(df_posts["created_at"], utc=True)
        df_posts["year"]  = df_posts["created_at"].dt.year
        df_posts["month"] = df_posts["created_at"].dt.month
        df_posts["day"]   = df_posts["created_at"].dt.day

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
        df_users["karma_score"]     = pd.to_numeric(df_users["karma_score"],     errors="coerce").astype("Float64")
        df_users["is_verified"]     = df_users["is_verified"].astype("boolean")

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
            "posts":         len(df_posts),
            "users":         len(df_users),
            "post_children": len(df_post_children),
        }),
    }


def iter_s3_objects(event):
    # S3 direct trigger
    if isinstance(event, dict) and "Records" in event:
        for record in event["Records"]:
            yield (
                record["s3"]["bucket"]["name"],
                urllib.parse.unquote_plus(record["s3"]["object"]["key"]),
            )
        return

    # EventBridge trigger
    if isinstance(event, dict) and "detail" in event:
        yield (
            event["detail"]["bucket"]["name"],
            urllib.parse.unquote_plus(event["detail"]["object"]["key"]),
        )
        return

    raise ValueError(f"Unsupported event format: {json.dumps(event)[:500]}")