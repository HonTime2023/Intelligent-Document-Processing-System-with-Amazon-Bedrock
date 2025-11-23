#!/usr/bin/env python3
"""Query Aurora RDS Data API for rows where `chunks` contains a substring.

Usage:
  python scripts/query_chunks_like.py "bucket"

Reads RDS ARNs from env vars `RDS_RESOURCE_ARN` and `RDS_SECRET_ARN` or from
terraform outputs in `stack1`.
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
        stack_dir = Path(__file__).resolve().parents[1] / 'stack1'
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/query_chunks_like.py <search-term>")
        sys.exit(1)
    term = sys.argv[1]
    resource_arn = os.environ.get('RDS_RESOURCE_ARN') or get_terraform_output('aurora_arn')
    secret_arn = os.environ.get('RDS_SECRET_ARN') or get_terraform_output('rds_secret_arn')
    database = os.environ.get('RDS_DATABASE') or 'myapp'
    region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-west-2'))

    if not resource_arn or not secret_arn:
        print('Missing RDS ARNs; set RDS_RESOURCE_ARN and RDS_SECRET_ARN in env or ensure terraform outputs are present.')
        sys.exit(2)

    client = boto3.client('rds-data', region_name=region)
    # Use ILIKE for case-insensitive search; return id and a snippet around the match
    sql = (
        "SELECT id, length(chunks) as len, left(chunks, 2000) as preview "
        "FROM bedrock_integration.bedrock_kb WHERE chunks ILIKE :p LIMIT 50;"
    )
    try:
        resp = client.execute_statement(
            resourceArn=resource_arn,
            secretArn=secret_arn,
            database=database,
            sql=sql,
            parameters=[{'name':'p','value':{'stringValue':'%{}%'.format(term)}}]
        )
        rows = resp.get('records', [])
        if not rows:
            print('No rows found containing', term)
            return
        for r in rows:
            vals = []
            for f in r:
                v = f.get('stringValue') or f.get('longValue') or f.get('doubleValue')
                vals.append(v)
            print('ROW:', vals)
    except ClientError as e:
        print('Error executing query:', e)


if __name__ == '__main__':
    main()
