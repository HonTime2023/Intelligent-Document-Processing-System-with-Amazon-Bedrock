#!/usr/bin/env python3
"""Run SQL file against an Aurora Serverless cluster using the RDS Data API.

This script reads `scripts/aurora_sql.sql`, splits statements while preserving
`$$` dollar-quoted blocks, and executes each statement via the RDS Data API.

Usage:
    pip install boto3
    python scripts/run_sql_rdsdata.py

The script reads resource ARN and secret ARN from the Terraform outputs in
stack1/terraform.tfstate; override with environment variables if needed.
"""
import os
import sys
import json
import subprocess
import boto3
from botocore.exceptions import ClientError
from pathlib import Path

# Configuration (read from Terraform outputs, or override with env vars)
def get_terraform_output(key, default=None):
    """Try to read Terraform output from stack1; fallback to env var then default.

    Uses: `terraform -chdir=<stack1_dir> output -json <key>` and parses the JSON.
    Returns the string value when Terraform returns a JSON string, or the
    `.get('value')` when Terraform returns an object with `value`.
    """
    try:
        stack1_dir = Path(__file__).resolve().parents[1] / 'stack1'
        cmd = ['terraform', '-chdir=' + str(stack1_dir), 'output', '-json', key]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            # terraform output -json may return a bare JSON string for simple values
            if isinstance(data, str):
                return data
            if isinstance(data, dict) and 'value' in data:
                return data['value']
            return data
    except Exception:
        pass
    return default

RESOURCE_ARN = os.environ.get("RDS_RESOURCE_ARN") or get_terraform_output("aurora_arn")
SECRET_ARN = os.environ.get("RDS_SECRET_ARN") or get_terraform_output("rds_secret_arn")
DATABASE = os.environ.get("RDS_DATABASE", "myapp")
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))
SQL_FILE = os.path.join(os.path.dirname(__file__), "aurora_sql.sql")


def split_sql_preserve_dollar(sql_text: str):
    """Split SQL into statements on semicolons but ignore semicolons inside $$...$$ blocks.

    Returns a list of statement strings (without the trailing semicolon).
    """
    statements = []
    current = []
    i = 0
    n = len(sql_text)
    in_dollar = False
    dollar_tag = "$$"

    while i < n:
        # detect start/end of dollar-quote
        if sql_text[i:i+2] == dollar_tag:
            in_dollar = not in_dollar
            current.append(dollar_tag)
            i += 2
            continue

        ch = sql_text[i]
        if ch == ';' and not in_dollar:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # any remaining
    last = ''.join(current).strip()
    if last:
        statements.append(last)
    return statements


def main():
    if not os.path.exists(SQL_FILE):
        print(f"SQL file not found: {SQL_FILE}")
        sys.exit(2)

    with open(SQL_FILE, 'r', encoding='utf-8') as f:
        sql_text = f.read()

    statements = split_sql_preserve_dollar(sql_text)
    print(f"Parsed {len(statements)} statements to execute")

    # Debug info to help when calls hang
    print(f"DEBUG: RESOURCE_ARN = {RESOURCE_ARN}")
    print(f"DEBUG: SECRET_ARN = {SECRET_ARN}")
    # Fail fast if either ARN is missing to avoid accidentally using placeholder values
    if not RESOURCE_ARN or not SECRET_ARN:
        print("ERROR: RDS resource ARN or secret ARN is not set.\nPlease set the environment variables RDS_RESOURCE_ARN and RDS_SECRET_ARN or ensure Terraform outputs are available.")
        sys.exit(2)
    print(f"DEBUG: DATABASE = {DATABASE}")
    print(f"DEBUG: REGION = {REGION}")
    sys.stdout.flush()

    client = boto3.client('rds-data', region_name=REGION)

    for idx, stmt in enumerate(statements, start=1):
        print(f"\n--- Statement {idx}/{len(statements)} (first 120 chars):\n{stmt[:120]}\n---")
        try:
            resp = client.execute_statement(
                resourceArn=RESOURCE_ARN,
                secretArn=SECRET_ARN,
                database=DATABASE,
                sql=stmt,
            )
            print("OK")
            # Optionally print rows for SELECTs
            if 'records' in resp:
                print(resp['records'])
        except ClientError as e:
            print(f"ERROR executing statement {idx}: {e}")
            # stop on error
            sys.exit(1)

    print("All statements executed.")


if __name__ == '__main__':
    main()
