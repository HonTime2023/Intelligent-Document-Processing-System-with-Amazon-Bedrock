#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from pathlib import Path

# Configuration
def get_terraform_output(key, default=None):
    """Try to read Terraform output from stack1; fallback to env var then default."""
    print(f"DEBUG: Trying to get terraform output for key={key}")
    sys.stdout.flush()
    try:
        stack1_dir = Path(__file__).resolve().parents[1] / 'stack1'
        print(f"DEBUG: stack1_dir = {stack1_dir}")
        sys.stdout.flush()
        cmd = ['terraform', '-chdir=' + str(stack1_dir), 'output', '-json', key]
        print(f"DEBUG: Running command: {' '.join(cmd)}")
        sys.stdout.flush()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=10
        )
        print(f"DEBUG: Return code: {result.returncode}")
        print(f"DEBUG: Stdout: {result.stdout}")
        print(f"DEBUG: Stderr: {result.stderr}")
        sys.stdout.flush()
        if result.returncode == 0:
            data = json.loads(result.stdout)
            print(f"DEBUG: Parsed JSON: {data}")
            print(f"DEBUG: Type: {type(data)}")
            sys.stdout.flush()
            # terraform output -json returns the value directly (not wrapped in {value: ...})
            if isinstance(data, str):
                print(f"DEBUG: Returning string: {data}")
                return data
            elif isinstance(data, dict) and 'value' in data:
                print(f"DEBUG: Returning dict value: {data['value']}")
                return data['value']
            else:
                print(f"DEBUG: Returning data as-is: {data}")
                return data
    except Exception as e:
        print(f"DEBUG: Exception: {e}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
    print(f"DEBUG: Returning default: {default}")
    return default

RESOURCE_ARN = os.environ.get("RDS_RESOURCE_ARN") or get_terraform_output("aurora_arn")
SECRET_ARN = os.environ.get("RDS_SECRET_ARN") or get_terraform_output("rds_secret_arn")

if not RESOURCE_ARN or not SECRET_ARN:
    print("ERROR: Missing RDS ARNs. Set RDS_RESOURCE_ARN and RDS_SECRET_ARN environment variables or ensure terraform outputs are available.")
    sys.exit(2)

print(f"FINAL RESOURCE_ARN: {RESOURCE_ARN}")
print(f"FINAL SECRET_ARN: {SECRET_ARN}")
