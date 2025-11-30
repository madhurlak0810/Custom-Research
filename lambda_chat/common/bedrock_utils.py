import json
import boto3
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Initialize Bedrock client
bedrock_runtime = boto3.client('bedrock-runtime', region_name='us-east-1')

# Model configurations
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
CHAT_MODEL = "openai.gpt-oss-20b-1:0"  # Using OpenAI model via Bedrock

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
    """Generate chat response using OpenAI GPT model via AWS Bedrock"""
    try:
        # Convert messages to the format expected by OpenAI models in Bedrock
        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        body = {
            "messages": formatted_messages,
            "temperature": 0.2,
            "max_tokens": 2048
        }
        
        response = bedrock_runtime.invoke_model(
            modelId=CHAT_MODEL,
            body=json.dumps(body)
        )
        
        result = json.loads(response['body'].read())
        return result['choices'][0]['message']['content']
        
    except Exception as e:
        logger.error(f"OpenAI chat response generation failed: {e}")
        raise