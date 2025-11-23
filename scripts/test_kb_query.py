import sys
from pathlib import Path

# Ensure project root is on sys.path so we can import bedrock_utils
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bedrock_utils import valid_prompt, query_knowledge_base, generate_response
import json

KB_ID = "9HOYRJWGB7"
# Selected a working model from the account's available models list
# (see scripts/list_bedrock_models.py). Use an ON_DEMAND active text model.
# Use an Anthropic Claude model which accepts the messages-style payload
MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

print('Running knowledge-base retrieval test...')
results = query_knowledge_base('excavator specs', KB_ID)
print('Retrieval results:')
if not results:
    print('No retrieval results returned. Full response object:')
    print(results)
else:
    for r in results:
        # defensive printing — some results may not include expected keys
        doc_id = r.get('documentId') or r.get('id') or '<no-id>'
        text = r.get('text') or r.get('contents') or ''
        print('-', doc_id, '-', text[:200])

print('\nSkipping model generation in this quick test to avoid long calls.\n')
print('If you want to run generation, re-enable the generation block in this script or run the following in a Python REPL:')
print("\nfrom bedrock_utils import generate_response\n# build prompt and call generate_response(...)")

# --- End-to-end generation (will call Bedrock model) ---
print('\nRunning end-to-end generation using retrieved context (this may incur charges)...')
context_pieces = []
for r in results[:3]:
    text = r.get('text') or r.get('contents') or ''
    if text:
        context_pieces.append(text)
    else:
        # fall back to metadata or id
        meta = r.get('metadata') or {}
        context_pieces.append(json.dumps(meta) if meta else f"DocumentID:{r.get('id')}")

context = '\n\n'.join(context_pieces) if context_pieces else 'No contextual passages found.'
prompt = f"You are a helpful assistant. Use the following context to answer the question.\n\nContext:\n{context}\n\nQuestion: What is the bucket capacity of the excavator X950?"
resp = generate_response(prompt, MODEL_ID, temperature=0.2, top_p=0.9, max_tokens=200)
print('\nModel response:')
print(resp)
