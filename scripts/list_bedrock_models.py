import boto3
import json

client = boto3.client('bedrock')

print('Trying to list models via different APIs...')

# Try common method names
methods_to_try = ['list_foundation_models', 'list_models', 'list_model_versions', 'list_model_packages']
for m in methods_to_try:
    try:
        fn = getattr(client, m)
        print(f'Calling {m}()')
        resp = fn()
        print(json.dumps(resp, indent=2, default=str))
        break
    except AttributeError:
        print(f'Method {m} not available on client')
    except Exception as e:
        print(f'Call {m} failed: {e}')

print('\nDone')
