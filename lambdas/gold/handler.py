import os
import json
import pandas as pd
import awswrangler as wr
from datetime import datetime, timezone

SILVER_BUCKET = os.environ["SILVER_BUCKET"]
GOLD_BUCKET = os.environ["GOLD_BUCKET"]


def compute_data_quality_score(df: pd.DataFrame, required_columns: list) -> float:
    if df.empty:
        return 0.0
    valid_rows = df[required_columns].dropna().shape[0]
    return round(valid_rows / len(df) * 100, 2)


def lambda_handler(event, context):
    today = datetime.now(timezone.utc).date()
    today_str = str(today)

    posts = wr.s3.read_parquet(f"s3://{SILVER_BUCKET}/posts/")
    users = wr.s3.read_parquet(f"s3://{SILVER_BUCKET}/users/")

    posts["created_at"] = pd.to_datetime(posts["created_at"], utc=True)
    posts["date"] = posts["created_at"].dt.date.astype(str)

    users = (
        users
        .sort_values("followers_count", ascending=False, na_position="last")
        .drop_duplicates(subset=["platform", "username"], keep="first")
        .reset_index(drop=True)
    )

    hn_posts = posts[posts["platform"] == "HackerNews"].copy()

    fact_hn_daily_posts = (
        hn_posts.groupby(["date", "post_type"])
        .size()
        .reset_index(name="total_posts")
    )

    users["created_at"] = pd.to_datetime(users["created_at"], utc=True, errors="coerce")
    users["created_date"] = users["created_at"].dt.date.astype(str)

    platform_totals = (
        users.groupby("platform")["username"]
        .nunique()
        .reset_index(name="total_users")
    )

    new_users_today = (
        users[users["created_date"] == today_str]
        .groupby("platform")["username"]
        .nunique()
        .reset_index(name="new_users")
    )

    fact_daily_users = platform_totals.merge(new_users_today, on="platform", how="left")
    fact_daily_users["new_users"] = fact_daily_users["new_users"].fillna(0).astype(int)
    fact_daily_users["date"] = today_str
    fact_daily_users = fact_daily_users[["date", "platform", "total_users", "new_users"]]

    x_users = users[
        (users["platform"] == "Twitter") &
        (users["followers_count"].notna())
    ].copy()

    dim_top_x_users = (
        x_users[["username", "platform", "followers_count"]]
        .nlargest(10, "followers_count")
        .copy()
    )
    dim_top_x_users["date"] = today_str

    hn_users = users[
        (users["platform"] == "HackerNews") &
        (users["karma_score"].notna())
    ].copy()

    dim_top_hn_users = (
        hn_users[["username", "platform", "karma_score"]]
        .nlargest(10, "karma_score")
        .copy()
    )
    dim_top_hn_users["date"] = today_str

    dim_bottom_hn_users = (
        hn_users[["username", "platform", "karma_score"]]
        .nsmallest(10, "karma_score")
        .copy()
    )
    dim_bottom_hn_users["date"] = today_str

    hn_jobs = hn_posts[
        (hn_posts["post_type"] == "job") &
        (hn_posts["score"].notna())
    ]

    dim_top_jobs = (
        hn_jobs[["post_id", "author_username", "created_at", "post_type", "score"]]
        .nlargest(10, "score")
        .copy()
    )
    dim_top_jobs["date"] = today_str

    hn_stories = hn_posts[
        (hn_posts["post_type"] == "story") &
        (hn_posts["score"].notna())
    ]

    dim_top_stories = (
        hn_stories[["post_id", "author_username", "created_at", "post_type", "score"]]
        .nlargest(10, "score")
        .copy()
    )
    dim_top_stories["date"] = today_str

    kpi_data_quality = pd.DataFrame([
        {
            "date": today_str,
            "dataset": "posts",
            "score": compute_data_quality_score(
                posts,
                ["post_id", "platform", "author_username", "created_at", "post_type"],
            ),
        },
        {
            "date": today_str,
            "dataset": "users",
            "score": compute_data_quality_score(
                users,
                ["username", "platform"],
            ),
        },
    ])

    wr.s3.to_parquet(
        df=fact_hn_daily_posts,
        path=f"s3://{GOLD_BUCKET}/fact_hn_daily_posts/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date", "post_type"],
    )

    wr.s3.to_parquet(
        df=fact_daily_users,
        path=f"s3://{GOLD_BUCKET}/fact_daily_users/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["platform", "date"],
    )

    wr.s3.to_parquet(
        df=dim_top_x_users,
        path=f"s3://{GOLD_BUCKET}/dim_top_x_users/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date"],
    )

    wr.s3.to_parquet(
        df=dim_top_hn_users,
        path=f"s3://{GOLD_BUCKET}/dim_top_hn_users/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date"],
    )

    wr.s3.to_parquet(
        df=dim_bottom_hn_users,
        path=f"s3://{GOLD_BUCKET}/dim_bottom_hn_users/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date"],
    )

    wr.s3.to_parquet(
        df=dim_top_jobs,
        path=f"s3://{GOLD_BUCKET}/dim_top_jobs/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date"],
    )

    wr.s3.to_parquet(
        df=dim_top_stories,
        path=f"s3://{GOLD_BUCKET}/dim_top_stories/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date"],
    )

    wr.s3.to_parquet(
        df=kpi_data_quality,
        path=f"s3://{GOLD_BUCKET}/kpi_data_quality/",
        dataset=True,
        mode="overwrite_partitions",
        partition_cols=["date", "dataset"],
    )

    dq_posts = float(kpi_data_quality[kpi_data_quality["dataset"] == "posts"]["score"].iloc[0])
    dq_users = float(kpi_data_quality[kpi_data_quality["dataset"] == "users"]["score"].iloc[0])

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Gold layer successfully built",
            "date": today_str,
            "facts": {
                "hn_daily_posts_rows": len(fact_hn_daily_posts),
                "daily_users_rows": len(fact_daily_users),
            },
            "dims": {
                "top_hn_users": len(dim_top_hn_users),
                "bottom_hn_users": len(dim_bottom_hn_users),
                "top_x_users": len(dim_top_x_users),
                "top_jobs": len(dim_top_jobs),
                "top_stories": len(dim_top_stories),
            },
            "kpi": {
                "data_quality_posts": dq_posts,
                "data_quality_users": dq_users,
            },
        }),
    }