import os
import json
import boto3

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['BRONZE_BUCKET']


def lambda_handler(event, context):
    """
    Placeholder Twitter ingest Lambda.
    Kolega 2 implementira logiku za preuzimanje dataset-a i upis u S3.
    """
    print(f"Twitter Lambda triggered. Target bucket: {BUCKET_NAME}")
    
    # TODO: kolega 2 implementira
    # 1. Preuzeti / pročitati Twitter dataset
    # 2. Upisati u S3 bucket pod prefiksom twitter/year=.../month=.../day=.../
    
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'Twitter ingest placeholder'})
    }