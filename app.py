import streamlit as st
import boto3
from botocore.exceptions import ClientError
import json
from bedrock_utils import query_knowledge_base, generate_response, valid_prompt


# Streamlit UI
st.title("Bedrock Chat Application")

# Sidebar for configurations
st.sidebar.header("Configuration")
model_id = st.sidebar.selectbox("Select LLM Model", ["anthropic.claude-3-haiku-20240307-v1:0", "anthropic.claude-3-5-sonnet-20240620-v1:0"])
# Default the KB ID to the one you created; you can override in the sidebar if desired.
kb_id = st.sidebar.text_input("Knowledge Base ID", "9HOYRJWGB7")
temperature = st.sidebar.select_slider("Temperature", [i/10 for i in range(0,11)],1)
top_p = st.sidebar.select_slider("Top_P", [i/1000 for i in range(0,1001)], 1)

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What would you like to know?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    if valid_prompt(prompt, model_id):
        # Query Knowledge Base
        kb_results = query_knowledge_base(prompt, kb_id)
        
        # Prepare context from Knowledge Base results (handle multiple retrieval shapes)
        context_pieces = []
        for result in (kb_results or []):
            text_piece = None
            if isinstance(result, dict):
                # common normalized form: {'text': '...'}
                if 'text' in result and isinstance(result['text'], str):
                    text_piece = result['text']
                # Bedrock Agent format: {'content': {'text': '...'}} or {'content': [{'text': '...'}]}
                elif 'content' in result:
                    content = result['content']
                    if isinstance(content, dict) and 'text' in content and isinstance(content['text'], str):
                        text_piece = content['text']
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict) and 'text' in item and isinstance(item['text'], str):
                                text_piece = item['text']
                                break
                # fallback shapes
                elif 'chunks' in result and isinstance(result['chunks'], str):
                    text_piece = result['chunks']
                elif 'preview' in result and isinstance(result['preview'], str):
                    text_piece = result['preview']
            # last resort: stringify
            if not text_piece:
                try:
                    text_piece = json.dumps(result)
                except Exception:
                    text_piece = str(result)
            if text_piece:
                # keep pieces reasonably sized
                if len(text_piece) > 5000:
                    text_piece = text_piece[:5000] + "\n...[truncated]"
                context_pieces.append(text_piece)

        context = "\n".join(context_pieces)
        if len(context) > 15000:
            context = context[:15000] + "\n...[truncated]"
        
        # Generate response using LLM
        full_prompt = f"Context: {context}\n\nUser: {prompt}\n\n"
        response = generate_response(full_prompt, model_id, temperature, top_p)
    else:
        response = "I'm unable to answer this, please try again"
    
    # Display assistant response
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})