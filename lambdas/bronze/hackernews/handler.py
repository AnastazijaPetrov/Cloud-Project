import os
import json
import boto3

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['BRONZE_BUCKET']


def lambda_handler(event, context):
    """
    Placeholder Hacker News ingest Lambda.
    Kolega 1 implementira logiku za poziv HN API-ja i upis u S3.
    """
    print(f"HackerNews Lambda triggered. Target bucket: {BUCKET_NAME}")
    
    # TODO: kolega 1 implementira
    # 1. Pozvati HN API
    # 2. Skinuti sve story/ask/comment/job/poll kreirane juče
    # 3. Upisati u S3 bucket pod prefiksom hackernews/year=.../month=.../day=.../
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'HackerNews ingest placeholder'})
    }