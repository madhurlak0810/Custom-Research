import json
import logging
import os
import sys
from typing import Dict, Any, List

# Set up logging first
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import common utilities - add paths for Lambda runtime
sys.path.insert(0, '/opt/python')  # Lambda layer path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    import boto3
    from common.db_utils import get_connection, execute_query, test_connection
    from common.bedrock_utils import generate_embeddings, generate_chat_response
except ImportError as e:
    logger.error(f"Import error: {e}")
    raise
logger.setLevel(logging.INFO)

def main(event, context):
    """
    Lambda handler for chat functionality with RAG
    
    Expected event format:
    {
        "query": "What are the latest developments in quantum computing?",
        "topic_id": 1,
        "top_k": 5
    }
    """
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        user_query = body.get('query', '')
        topic_id = body.get('topic_id')
        topic_name = body.get('topic')  # Allow topic name instead of ID
        top_k = body.get('top_k', 5)
        
        if not user_query:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Query is required'})
            }
        
        # If topic name is provided, convert to topic_id
        if topic_name and not topic_id:
            topic_id = get_topic_id_by_name(topic_name)
        
        logger.info(f"Processing chat query: {user_query}, topic_id: {topic_id}")
        
        # Generate embedding for the user query
        query_embeddings = generate_embeddings([user_query])
        query_embedding = query_embeddings[0]
        
        # Search for relevant chunks
        relevant_chunks = search_relevant_chunks(
            query_embedding, 
            topic_id=topic_id, 
            top_k=top_k
        )
        
        if not relevant_chunks:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'response': 'I could not find relevant information to answer your query.',
                    'sources': []
                })
            }
        
        # Prepare context from relevant chunks
        context = prepare_context(relevant_chunks)
        
        # Generate response using Claude
        response = generate_response_with_context(user_query, context)
        
        # Prepare sources for citation
        sources = [
            {
                'paper_title': chunk['paper_title'],
                'arxiv_id': chunk['arxiv_id'],
                'similarity': round(chunk['similarity'], 3),
                'url': chunk['url']
            }
            for chunk in relevant_chunks
        ]
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'response': response,
                'sources': sources,
                'context_chunks': len(relevant_chunks)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in chat handler: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def search_relevant_chunks(query_embedding: List[float], topic_id: int = None, top_k: int = 5) -> List[Dict[str, Any]]:
    """Search for relevant papers using vector similarity"""
    try:
        # Convert embedding to PostgreSQL vector format
        if hasattr(query_embedding, 'tolist'):
            embedding_list = query_embedding.tolist()
        else:
            embedding_list = list(query_embedding)
        
        # Format as PostgreSQL vector with square brackets
        embedding_str = '[' + ','.join(map(str, embedding_list)) + ']'
        
        # Build query with optional topic filter
        base_query = """
            SELECT 
                p.abstract as content,
                p.embedding <=> %s::vector as similarity,
                p.title as paper_title,
                p.arxiv_id
            FROM papers p
        """
        
        params = [embedding_str]
        
        if topic_id:
            base_query += " WHERE p.topic_id = %s"
            params.append(topic_id)
        
        base_query += """
            ORDER BY p.embedding <=> %s::vector
            LIMIT %s
        """
        params.extend([embedding_str, top_k])
        
        results = execute_query(base_query, params, fetch=True)
        
        # Convert to list of dictionaries
        chunks = []
        for result in results:
            if isinstance(result, dict):
                chunk_data = {
                    'content': result['content'],
                    'similarity': float(result['similarity']),
                    'paper_title': result['paper_title'],
                    'arxiv_id': result['arxiv_id'],
                    'url': f"https://arxiv.org/abs/{result['arxiv_id']}"
                }
            else:
                # Handle tuple result
                chunk_data = {
                    'content': result[0],
                    'similarity': float(result[1]),
                    'paper_title': result[2],
                    'arxiv_id': result[3],
                    'url': f"https://arxiv.org/abs/{result[3]}"
                }
            chunks.append(chunk_data)
        
        logger.info(f"Found {len(chunks)} relevant papers for query")
        return chunks
        
    except Exception as e:
        logger.error(f"Error searching for chunks: {e}")
        return []

def prepare_context(chunks: List[Dict[str, Any]]) -> str:
    """Prepare context string from relevant chunks"""
    context_parts = []
    
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['paper_title']} (arXiv:{chunk['arxiv_id']})]\n"
            f"{chunk['content']}\n"
        )
    
    return "\\n".join(context_parts)

def generate_response_with_context(user_query: str, context: str) -> str:
    """Generate response using Claude with retrieved context"""
    try:
        messages = [
            {
                "role": "user",
                "content": f"""Based on the following research paper excerpts, please answer this question: {user_query}

Research Context:
{context}

Please provide a comprehensive answer based on the information in these sources."""
            }
        ]
        
        response = generate_chat_response(messages)
        return response
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return f"Error details: {str(e)}"

def get_topic_id_by_name(topic_name: str) -> int:
    """Get topic ID by topic name"""
    try:
        query = "SELECT id FROM topics WHERE name = %s"
        result = execute_query(query, (topic_name,), fetch=True)
        
        if result and len(result) > 0:
            if isinstance(result[0], dict):
                return result[0]['id']
            elif isinstance(result[0], (list, tuple)):
                return result[0][0]
            else:
                return result[0]
        else:
            logger.warning(f"Topic '{topic_name}' not found")
            return None
            
    except Exception as e:
        logger.error(f"Error looking up topic: {e}")
        return None