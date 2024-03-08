import streamlit as st
import json
import base64
import boto3
import toml
from PIL import Image
import io

# Load secrets from toml file
secrets = toml.load("secrets.toml")
AWS_ACCESS_KEY_ID = secrets["bedrock"]["aws_access_key_id"]
AWS_SECRET_ACCESS_KEY = secrets["bedrock"]["aws_secret_access_key"]
REGION_NAME = secrets["bedrock"]["region_name"]

# Set up Boto3 client
bedrock_runtime = boto3.client(
    service_name="bedrock-runtime",
    region_name=REGION_NAME,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

# Function to stream the prompt with conversation history, handling both text and image in one user message
def stream_prompt(model_id, conversation_history, max_tokens=10000):
    messages = []
    for entry in conversation_history:
        content_block = {"type": entry['type']}
        if entry['type'] == 'text':
            content_block["text"] = entry['content']
        elif entry['type'] == 'image':
            content_block["source"] = {"type": "base64", "media_type": entry['media_type'], "data": entry['content']}

        # Append new content block to the last message if it's from the same "user" role
        if messages and messages[-1]["role"] == "user" and entry['role'] == "user":
            messages[-1]["content"].append(content_block)
        else:
            messages.append({"role": entry['role'], "content": [content_block]})

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages
    })

    response = bedrock_runtime.invoke_model_with_response_stream(
        body=body, modelId=model_id)

    output_text = ""
    for event in response.get("body"):
        chunk = json.loads(event["chunk"]["bytes"])
        if chunk['type'] == 'content_block_delta':
            if chunk['delta']['type'] == 'text_delta':
                output_text += chunk['delta']['text']

    return output_text

# Streamlit app setup
st.set_page_config(page_title="Claude Sonnet V3 Multimodal Chat Demo")

# Initialize session state for conversation history if it doesn't exist
if 'conversation_history' not in st.session_state:
    st.session_state['conversation_history'] = []

# Function to display the conversation history
def display_conversation_history():
    for entry in st.session_state['conversation_history']:
        if entry['type'] == 'text':
            with st.chat_message(entry['role'], avatar="🙋🏼‍♂️" if entry['role'] == 'user' else "🤖"):
                st.markdown(entry['content'])
        elif entry['type'] == 'image':
            # Decode base64 image data
            image_data = base64.b64decode(entry['content'])
            # Create a BytesIO object from the image data
            image = Image.open(io.BytesIO(image_data))
            with st.chat_message(entry['role'], avatar="🙋🏼‍♂️" if entry['role'] == 'user' else "🤖"):
                st.image(image, use_column_width=True)

# Display conversation history
st.title("💬  Claude 3 Sonnet Multimodal Chat")
st.write("Demo V08 via AWS Bedrock Runtime API with Anthropic Claude V3 Sonnet.")
st.write("If an image is uploaded, it will be used within the prompt. Otherwise, the text input will be used as the prompt. To continue the conversation without the image/another image, just remove/replace the upload.")
st.divider()

display_conversation_history()

# User input area
user_input = st.chat_input(
    "Ask me anything...",  # Placeholder
    key="user_input",
    # label_visibility="collapsed",
)

# Accept both JPEG and PNG image formats
uploaded_file = st.file_uploader("Choose an image (optional)", type=["jpg", "jpeg", "png"], key="uploaded_file")
submit_button = st.button("▶️ Submit")

# Submit button action
if submit_button or user_input:
    model_id = "anthropic.claude-3-sonnet-20240229-v1:0"
    max_tokens = 10000

    # Check and append user input to the conversation history
    if user_input:
        st.session_state['conversation_history'].append({'role': 'user', 'content': user_input, 'type': 'text'})
    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        buffered = io.BytesIO()
        if image.format.lower() == 'png':
            media_type = 'image/png'
        else:
            media_type = 'image/jpeg'
        image.save(buffered, format=image.format)
        image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
        st.session_state['conversation_history'].append({'role': 'user', 'content': image_data, 'type': 'image', 'media_type': media_type})

    # Ensure there's input to process
    if user_input or uploaded_file is not None:
        # Call the function with conversation history
        output_text = stream_prompt(model_id, st.session_state['conversation_history'], max_tokens)

        # Append model's response to conversation history
        st.session_state['conversation_history'].append({'role': 'assistant', 'content': output_text, 'type': 'text'})

        # Clear the user input
        user_input = ""

        # Force the app to re-render the conversation history
        st.experimental_rerun()
    else:
        st.error("Please enter a prompt or upload an image.")
