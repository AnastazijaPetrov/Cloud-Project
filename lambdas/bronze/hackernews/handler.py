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
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'HackerNews ingest placeholder'})
    }