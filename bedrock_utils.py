import boto3
from botocore.exceptions import ClientError
import json
from typing import List, Dict, Any, Optional


# Initialize AWS Bedrock client (model runtime)
bedrock = boto3.client(
    service_name='bedrock-runtime',
    region_name='us-west-2'  # Replace with your AWS region if needed
)


# Initialize Bedrock Knowledge Base client (agent runtime)
bedrock_kb = boto3.client(
    service_name='bedrock-agent-runtime',
    region_name='us-west-2'
)


def _normalize_retrieval_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize varying retrieval result shapes into a predictable dict.

    Returns keys: id, text, metadata, score
    """
    if not isinstance(item, dict):
        return {'id': None, 'text': str(item), 'metadata': {}, 'score': None}

    # Common locations
    doc = item.get('document') or {}
    # Some retrieval responses include a `content` or `contents` field with nested text
    content = item.get('content') or item.get('contents')
    text = ''
    if isinstance(content, dict):
        text = content.get('text') or content.get('documentText') or ''
    elif isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            text = first.get('text') or first.get('documentText') or ''

    # fallback to other common keys
    if not text:
        text = item.get('text') or item.get('documentText') or doc.get('text') or ''

    doc_id = item.get('documentId') or item.get('id') or doc.get('id')
    metadata = item.get('metadata') or doc.get('metadata') or {}
    score = item.get('score') or item.get('similarity') or item.get('relevanceScore')
    return {'id': doc_id, 'text': text, 'metadata': metadata, 'score': score}


def query_knowledge_base(query: str, kb_id: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Query the Bedrock Agent knowledge base and return normalized retrieval items.

    Returns a list of dicts with keys: id, text, metadata, score
    """
    try:
        response = bedrock_kb.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={'text': query},
            retrievalConfiguration={'vectorSearchConfiguration': {'numberOfResults': top_k}}
        )

        # Response shapes may vary between SDK/calls. Try several common keys.
        results = response.get('retrievalResults') or response.get('results') or response.get('items') or response.get('hits') or []

        # If results is a dict with nested list, try extracting
        if isinstance(results, dict):
            # e.g., {'items': [...]}
            for k in ('items', 'results', 'hits'):
                if k in results and isinstance(results[k], list):
                    results = results[k]
                    break

        normalized = [_normalize_retrieval_item(r) for r in (results or [])]
        return normalized
    except ClientError as e:
        print(f"Error querying Knowledge Base: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error querying KB: {e}")
        return []


def generate_response(prompt: str, model_id: str, temperature: float = 0.0, top_p: float = 1.0,
                      max_tokens: int = 512) -> Optional[str]:
    """Invoke a Bedrock model to generate a response for a given prompt."""
    try:
        # Different foundation models expect different payload shapes.
        # Anthropic/Claude models expect a 'messages' style payload.
        # Most others (Llama, Mistral, Cohere, Meta) accept a generic 'input' payload.
        lower_id = (model_id or '').lower()
        if 'anthropic.' in lower_id or 'claude' in lower_id:
            messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }
        else:
            # Generic payload expected by many Bedrock models
            payload = {
                "input": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
            }

        response = bedrock.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps(payload)
        )

        # Response body may be a StreamingBody-like object
        body = response.get('body')
        if hasattr(body, 'read'):
            data = json.loads(body.read())
        else:
            data = json.loads(body)

        # Attempt to extract text from common locations for different models
        # Anthropic-style responses often include 'content' with list of {'text': ...}
        if isinstance(data, dict):
            if 'content' in data and isinstance(data['content'], list) and data['content']:
                first = data['content'][0]
                if isinstance(first, dict) and 'text' in first:
                    return first['text']

            # Generic models may return {'output': '...'} or {'generatedText': '...'} or {'results': [...]}
            for key in ('output', 'generatedText', 'text', 'result'):
                if key in data and isinstance(data[key], str):
                    return data[key]

            # Some models wrap text in results list
            if 'results' in data and isinstance(data['results'], list) and data['results']:
                r0 = data['results'][0]
                if isinstance(r0, dict):
                    for k in ('output', 'text', 'generatedText'):
                        if k in r0 and isinstance(r0[k], str):
                            return r0[k]

        # Fallback: stringify entire content
        return json.dumps(data)
    except ClientError as e:
        print(f"Error generating response: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error invoking model: {e}")
        return None


def valid_prompt(prompt: str, model_id: str) -> Dict[str, Any]:
    """Classify prompt into categories and return a structured result.

    Returns {'category': 'A'..'E', 'raw': '<model output>'}
    """
    try:
        system_message = (
            "Classify the user request into one category: A,B,C,D,E. "
            "Respond with a single line like: 'Category E'"
        )
        # Reuse generate_response logic to respect model payload differences
        full_prompt = system_message + "\n\n" + prompt
        resp_text = generate_response(full_prompt, model_id, temperature=0.0, top_p=1.0, max_tokens=8)
        raw = resp_text or ''

        # crude extraction of letter
        for ch in ('A', 'B', 'C', 'D', 'E'):
            if ch in raw.upper():
                return {'category': ch, 'raw': raw}

        return {'category': None, 'raw': raw}
    except Exception as e:
        print(f"Error validating prompt: {e}")
        return {'category': None, 'raw': str(e)}