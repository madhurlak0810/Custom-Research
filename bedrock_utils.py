import json
import boto3
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Initialize Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# Model configurations
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
CHAT_MODEL = "anthropic.claude-3-5-sonnet-20240620-v1:0"

def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of texts using Amazon Titan"""
    try:
        embeddings = []
        
        for text in texts:
            body = {
                "inputText": text,
                "dimensions": 1024,
                "normalize": True
            }
            
            response = bedrock_runtime.invoke_model(
                modelId=EMBEDDING_MODEL,
                body=json.dumps(body)
            )
            
            result = json.loads(response['body'].read())
            embeddings.append(result['embedding'])
        
        return embeddings
        
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise

def generate_chat_response(messages: List[Dict[str, str]]) -> str:
    """Generate chat response using Claude"""
    try:
        # Extract system messages
        system_messages = [msg['content'] for msg in messages if msg['role'] == 'system']
        system_prompt = '\n'.join(system_messages) if system_messages else ""
        
        # Filter user/assistant messages
        chat_messages = [
            {
                "role": msg["role"],
                "content": [{"type": "text", "text": msg["content"]}]
            }
            for msg in messages if msg["role"] in ["user", "assistant"]
        ]
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": chat_messages,
            "temperature": 0.2,
            "max_tokens": 2048
        }
        
        # Only add system prompt if it exists
        if system_prompt:
            body["system"] = system_prompt
        
        response = bedrock_runtime.invoke_model(
            modelId=CHAT_MODEL,
            body=json.dumps(body)
        )
        
        result = json.loads(response['body'].read())
        return result['content'][0]['text']
        
    except Exception as e:
        logger.error(f"Chat response generation failed: {e}")
        raise