import os
import json
import boto3
import awswrangler as wr
import psycopg2
from sqlalchemy import create_engine

ssm = boto3.client("ssm")

GOLD_BUCKET = os.environ["GOLD_BUCKET"]
POSTGRES_HOST = os.environ["POSTGRES_HOST"]
POSTGRES_DB = os.environ["POSTGRES_DB"]
POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD_PARAM = os.environ["POSTGRES_PASSWORD_PARAM"]

_password = None


def get_postgres_password():
    global _password
    if _password is None:
        response = ssm.get_parameter(
            Name=POSTGRES_PASSWORD_PARAM,
            WithDecryption=True,
        )
        _password = response["Parameter"]["Value"]
    return _password


GOLD_TABLES = [
    "fact_hn_daily_posts",
    "fact_daily_users",
    "dim_top_x_users",
    "dim_top_hn_users",
    "dim_bottom_hn_users",
    "dim_top_jobs",
    "dim_top_stories",
    "kpi_data_quality",
]


def lambda_handler(event, context):
    print(f"Loading gold metrics to PostgreSQL at {POSTGRES_HOST}")

    password = get_postgres_password()
    engine = create_engine(
        f"postgresql://{POSTGRES_USER}:{password}@{POSTGRES_HOST}:5432/{POSTGRES_DB}"
    )

    loaded_tables = {}

    for table_name in GOLD_TABLES:
        try:
            df = wr.s3.read_parquet(
                path=f"s3://{GOLD_BUCKET}/{table_name}/",
                dataset=True,
                validate_schema=False,
            )

            if df.empty:
                print(f"Skipping {table_name}: no data")
                continue

            df.to_sql(
                table_name,
                engine,
                if_exists="replace",
                index=False,
                method="multi",
                chunksize=1000,
            )

            loaded_tables[table_name] = len(df)
            print(f"Loaded {table_name}: {len(df)} rows")

        except Exception as e:
            error_type = type(e).__name__
            if "NoFilesFound" in error_type:
                print(f"Skipping {table_name}: no parquet files")
                continue
            print(f"Error loading {table_name}: {e}")
            raise

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Gold metrics loaded to PostgreSQL",
            "tables": loaded_tables,
        }),
    }