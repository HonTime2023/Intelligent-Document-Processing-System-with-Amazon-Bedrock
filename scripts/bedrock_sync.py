#!/usr/bin/env python3
"""Trigger and poll a Bedrock Agent knowledge-base sync using the AWS CLI.

This script uses the AWS CLI to start a knowledge-base sync (if supported by your
installed AWS CLI) and polls the knowledge-base status until it reaches a terminal
state (ACTIVE or FAILED). It accepts a knowledge-base ID via `--kb-id` or will
attempt to read it from Terraform state in `stack2`.

Usage:
  python scripts/bedrock_sync.py --kb-id DOQID9QB63
  # or let the script read the KB id from stack2 terraform output
  python scripts/bedrock_sync.py --auto

Notes:
  - This script calls the AWS CLI (subprocess). Ensure the `aws` CLI is installed
    and configured in your environment and has permissions to manage Bedrock Agent resources.
  - If your CLI does not expose Bedrock Agent commands, use the AWS Console to start a sync.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, '', f"command not found: {cmd[0]}"


def aws_cli_available():
    return shutil.which('aws') is not None


def start_sync_cli(kb_id):
    # Try multiple plausible Bedrock Agent CLI command names until one works.
    candidates = [
        'bedrock-agent',
        'bedrock-agentcore',
        'bedrockagent',
    ]
    last_err = None
    for cmd_name in candidates:
        start_cmd = ['aws', cmd_name, 'start-knowledge-base-sync', '--knowledge-base-id', kb_id]
        code, out, err = run_cmd(start_cmd)
        if code == 0:
            try:
                return True, json.loads(out)
            except Exception:
                return True, out
        last_err = (cmd_name, code, out, err)

    # Nothing worked — return last error for diagnostics.
    return False, last_err


def get_kb_status_cli(kb_id):
    get_cmd = ['aws', 'bedrockagent', 'get-knowledge-base', '--knowledge-base-id', kb_id, '--output', 'json']
    code, out, err = run_cmd(get_cmd)
    if code != 0:
        return None, (code, out, err)
    try:
        data = json.loads(out)
        # status might be in data['status'] or data['knowledgeBase']['status'] depending on API
        status = data.get('status') or data.get('knowledgeBase', {}).get('status')
        return status, data
    except Exception:
        return None, out


def read_kb_from_terraform():
    # Attempt to read stack2 terraform output (terraform must be in PATH)
    tf_stack2 = Path(__file__).resolve().parents[1] / 'stack2'
    if not tf_stack2.exists():
        return None
    # First try `terraform output` (preferred).
    cmd = ['terraform', 'output', '-chdir=' + str(tf_stack2), '-raw', 'bedrock_knowledge_base_id']
    code, out, err = run_cmd(cmd)
    if code == 0 and out:
        return out.strip()

    # If that failed, give more diagnostics in logs and try reading terraform.tfstate.
    # Try environment variable fallback.
    env_kb = os.environ.get('BEDROCK_KB_ID')
    if env_kb:
        return env_kb.strip()

    tfstate_path = tf_stack2 / 'terraform.tfstate'
    if tfstate_path.exists():
        try:
            with open(tfstate_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            outputs = data.get('outputs', {})
            for key in ('bedrock_knowledge_base_id', 'bedrock_knowledge_base', 'knowledge_base_id'):
                if key in outputs:
                    val = outputs[key].get('value') if isinstance(outputs[key], dict) else outputs[key]
                    if val:
                        return str(val)
        except Exception:
            pass

    # Could not find KB id via terraform output or tfstate.
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kb-id', help='Knowledge Base ID to sync')
    parser.add_argument('--auto', action='store_true', help='Auto-detect KB ID from stack2 terraform output')
    parser.add_argument('--poll-interval', type=int, default=10, help='Polling interval seconds')
    args = parser.parse_args()

    kb_id = args.kb_id
    if args.auto and not kb_id:
        kb_id = read_kb_from_terraform()
        if not kb_id:
            print('Could not read KB id from Terraform output. Provide --kb-id or run terraform in stack2 first.')
            sys.exit(2)

    if not kb_id:
        print('Please provide a knowledge-base id with --kb-id or use --auto to read from terraform.')
        sys.exit(2)

    if not aws_cli_available():
        print('The AWS CLI is not available in PATH. Install and configure it, then re-run this script.')
        sys.exit(2)

    print(f'Starting sync for knowledge base: {kb_id}')
    ok, result = start_sync_cli(kb_id)
    if not ok:
        # start_sync_cli returns a diagnostics tuple (cmd_name, code, out, err)
        # or similar; guard against different shapes and print helpful info.
        print('Failed to start sync via AWS CLI. Diagnostics:')
        if isinstance(result, tuple) and len(result) == 4:
            cmd_name, code, out, err = result
            print('Tried CLI command:', cmd_name)
            print('Exit code:', code)
            print('Stdout:', out)
            print('Stderr:', err)
        else:
            print(result)
        print('\nYour installed AWS CLI may not include Bedrock Agent operations.\n')
        print('To trigger a sync manually, open the Bedrock Console:')
        print(f'https://console.aws.amazon.com/bedrock/home?region=us-west-2#/knowledge-bases/{kb_id}')
        sys.exit(1)

    print('Sync started. Polling status...')
    while True:
        status, info = get_kb_status_cli(kb_id)
        if status is None:
            print('Could not read KB status. Response:', info)
            sys.exit(1)
        print('Status:', status)
        if str(status).upper() in ('ACTIVE', 'COMPLETED', 'FAILED'):
            print('Terminal status reached:', status)
            break
        time.sleep(args.poll_interval)

    print('Final KB info:')
    print(json.dumps(info, indent=2))


if __name__ == '__main__':
    main()
