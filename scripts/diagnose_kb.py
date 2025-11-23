#!/usr/bin/env python3
"""Diagnose Bedrock KB retrieval, S3 objects, and Aurora table contents.

Usage:
  python scripts/diagnose_kb.py [--query "text to search"]

This script prints the raw Bedrock Agent `retrieve` response, lists the S3
objects in the KB bucket, and queries the first rows from
`bedrock_integration.bedrock_kb` to show stored `chunks` content.
"""
import os
import json
import subprocess
from pathlib import Path
import sys
import boto3
from botocore.exceptions import ClientError


def get_terraform_output(key, default=None):
    try:
        stack_dir = Path(__file__).resolve().parents[1] / 'stack2'
        cmd = ['terraform', '-chdir=' + str(stack_dir), 'output', '-json', key]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            if isinstance(data, str):
                return data
            if isinstance(data, dict) and 'value' in data:
                return data['value']
            return data
    except Exception:
        pass
    return os.environ.get(key.upper(), default)


def extract_bucket_name(s):
    if not s:
        return None
    # terraform sometimes returns arn:aws:s3:::bucket-name or just bucket-name
    if s.startswith('arn:aws:s3:::'):
        return s.split(':::', 1)[1]
    return s


def pretty_print(obj):
    print(json.dumps(obj, indent=2, default=str))


def inspect_kb_retrieval(kb_id, query_text, region):
    client = boto3.client('bedrock-agent-runtime', region_name=region)
    print(f"Calling Bedrock Agent retrieve for KB '{kb_id}' with query: '{query_text}'")
    try:
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query_text},
            retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': 5}}
        )
        print("Raw retrieve response:")
        pretty_print(resp)
    except ClientError as e:
        print(f"Error calling retrieve: {e}")


def list_s3_objects(bucket_name, region):
    if not bucket_name:
        print("No S3 bucket name provided; skipping S3 listing.")
        return
    s3 = boto3.client('s3', region_name=region)
    print(f"Listing objects in bucket: {bucket_name}")
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name):
            if 'Contents' in page:
                for obj in page['Contents']:
                    print('-', obj['Key'], f"({obj['Size']} bytes)")
            else:
                print('Bucket appears empty or listing returned no Contents')
    except ClientError as e:
        print(f"Error listing S3 objects: {e}")


def query_aurora_chunks(resource_arn, secret_arn, database, region):
    if not resource_arn or not secret_arn:
        print("Missing RDS resourceArn or secretArn; skipping Aurora query.")
        return
    client = boto3.client('rds-data', region_name=region)
    sql = (
        "SELECT id, left(chunks, 1000) as preview, length(chunks) as len "
        "FROM bedrock_integration.bedrock_kb LIMIT 10;"
    )
    print("Querying Aurora table `bedrock_integration.bedrock_kb` (preview of `chunks`):")
    try:
        resp = client.execute_statement(
            resourceArn=resource_arn,
            secretArn=secret_arn,
            database=database,
            sql=sql,
        )
        records = resp.get('records', [])
        if not records:
            print('No rows returned from table.')
            return
        # records is list of rows; each row is list of field dicts
        for row in records:
            vals = []
            for fld in row:
                # choose the present value key
                v = fld.get('stringValue') or fld.get('blobValue') or fld.get('longValue') or fld.get('doubleValue')
                vals.append(v)
            print('ROW:', vals)
    except ClientError as e:
        print(f"Error querying Aurora table: {e}")


def main():
    region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-west-2'))
    query_text = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else 'excavator specs'

    kb_id = os.environ.get('KB_ID') or get_terraform_output('bedrock_knowledge_base_id') or '9HOYRJWGB7'
    bucket_out = get_terraform_output('s3_bucket_name')
    bucket = extract_bucket_name(bucket_out) or os.environ.get('UPLOAD_BUCKET_NAME')

    resource_arn = os.environ.get('RDS_RESOURCE_ARN') or get_terraform_output('aurora_arn')
    secret_arn = os.environ.get('RDS_SECRET_ARN') or get_terraform_output('rds_secret_arn')
    database = os.environ.get('RDS_DATABASE') or 'myapp'

    print('\n=== Bedrock KB retrieval ===')
    inspect_kb_retrieval(kb_id, query_text, region)

    print('\n=== S3 bucket objects ===')
    list_s3_objects(bucket, region)

    print('\n=== Aurora table preview ===')
    query_aurora_chunks(resource_arn, secret_arn, database, region)


if __name__ == '__main__':
    main()
