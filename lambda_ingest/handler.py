import json
import logging
import os
import sys
from typing import Dict, Any, List
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

# Configure SSL certificates BEFORE any boto3 imports
# Use system CA bundle instead of certifi
ca_bundle_paths = [
    '/etc/pki/tls/certs/ca-bundle.crt',  # Amazon Linux
    '/etc/ssl/certs/ca-certificates.crt',  # Debian/Ubuntu
    '/etc/ssl/ca-bundle.pem',  # OpenSUSE
]

for ca_path in ca_bundle_paths:
    if os.path.exists(ca_path):
        os.environ['AWS_CA_BUNDLE'] = ca_path
        os.environ['REQUESTS_CA_BUNDLE'] = ca_path
        break

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
    from common.bedrock_utils import generate_embeddings
    from common.db_utils import get_connection, execute_query, test_connection, initialize_database, get_or_create_topic, paper_exists, insert_paper
except ImportError as e:
    logger.error(f"Import error: {e}")
    raise

def fetch_arxiv_papers(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch papers from arXiv API using urllib
    
    Args:
        query: Search query string
        max_results: Maximum number of papers to fetch
        
    Returns:
        List of paper dictionaries with title, authors, abstract, etc.
    """
    papers = []
    
    try:
        # Construct arXiv API query URL
        base_url = "http://export.arxiv.org/api/query"
        search_query = f"all:{query.replace(' ', '+')}"
        params = {
            'search_query': search_query,
            'start': 0,
            'max_results': max_results
        }
        
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        logger.info(f"Fetching from arXiv: {url}")
        
        # Make the request
        with urllib.request.urlopen(url) as response:
            xml_content = response.read().decode('utf-8')
        
        # Parse XML response
        root = ET.fromstring(xml_content)
        
        # Extract namespace
        namespace = {'atom': 'http://www.w3.org/2005/Atom'}
        
        # Parse entries
        for entry in root.findall('atom:entry', namespace):
            # Extract paper information
            title = entry.find('atom:title', namespace)
            title_text = title.text.strip().replace('\n', ' ') if title is not None else "No title"
            
            # Get arXiv ID from the id field
            id_element = entry.find('atom:id', namespace)
            arxiv_id = id_element.text.split('/')[-1] if id_element is not None else "unknown"
            
            # Extract authors
            authors = []
            for author in entry.findall('atom:author', namespace):
                name_elem = author.find('atom:name', namespace)
                if name_elem is not None:
                    authors.append(name_elem.text.strip())
            
            # Extract abstract/summary
            summary = entry.find('atom:summary', namespace)
            abstract = summary.text.strip().replace('\n', ' ') if summary is not None else "No abstract"
            
            # Extract published date
            published = entry.find('atom:published', namespace)
            published_date = published.text[:10] if published is not None else "unknown"
            
            # Extract categories
            categories = []
            for category in entry.findall('atom:category', namespace):
                term = category.get('term')
                if term:
                    categories.append(term)
            
            paper = {
                'arxiv_id': arxiv_id,
                'title': title_text,
                'authors': '; '.join(authors),
                'abstract': abstract,
                'published_date': published_date,
                'categories': ', '.join(categories)
            }
            
            papers.append(paper)
            
        logger.info(f"Successfully fetched {len(papers)} papers")
        return papers
        
    except Exception as e:
        logger.error(f"Error fetching papers from arXiv: {e}")
        return []

def main(event, context):
    """
    Lambda handler for ingesting research papers from arXiv
    
    Expected event format:
    {
        "query": "machine learning",
        "max_results": 10,
        "topic_name": "Machine Learning"
    }
    """
    try:
        # Parse request
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', 'machine learning')
        max_results = body.get('max_results', 10)
        topic_name = body.get('topic_name', query.title())
        
        logger.info(f"Starting ingestion for query: {query}, max_results: {max_results}")
        
        # Fetch papers from arXiv
        papers = fetch_arxiv_papers(query, max_results)
        if not papers:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
                },
                'body': json.dumps({'error': 'No papers found'})
            }
        
        logger.info(f"Fetched {len(papers)} papers from arXiv")
        
        # Try to initialize database and store papers
        database_enabled = False
        processed_count = 0
        
        try:
            initialize_database()
            database_enabled = True
            logger.info("Database initialized successfully")
            
            # Get or create topic
            topic_id = get_or_create_topic(topic_name, f"Research papers about {topic_name}")
            
            # Process each paper
            for paper in papers:
                try:
                    # Check if paper already exists
                    if paper_exists(paper['arxiv_id']):
                        logger.info(f"Paper {paper['arxiv_id']} already exists, skipping")
                        continue
                    
                    # Insert paper with embeddings
                    paper_id = insert_paper(paper, topic_id)
                    processed_count += 1
                    logger.info(f"Successfully processed paper: {paper['arxiv_id']}")
                    
                except Exception as e:
                    logger.error(f"Error processing paper {paper.get('arxiv_id', 'unknown')}: {e}")
                    continue
            
        except Exception as db_error:
            logger.warning(f"Database operations failed: {db_error}")
            logger.info("Falling back to embedding-only mode")
            
            # Fallback: Test Bedrock embeddings on sample papers
            sample_papers = papers[:3]  # First 3 papers
            embeddings_generated = 0
            embedding_errors = []
            
            for paper in sample_papers:
                try:
                    text_content = f"{paper['title']}\\n\\n{paper['abstract']}"
                    embeddings = generate_embeddings([text_content])
                    embeddings_generated += 1
                    logger.info(f"Generated embedding for: {paper['title'][:50]}...")
                except Exception as e:
                    error_msg = f"Embedding failed for {paper['title'][:30]}...: {str(e)}"
                    embedding_errors.append(error_msg)
                    logger.error(error_msg)
            
            # Return fallback response
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Database unavailable. Processed {len(papers)} papers from arXiv (embeddings only)',
                    'total_papers_fetched': len(papers),
                    'embeddings_generated': embeddings_generated,
                    'embedding_errors': embedding_errors,
                    'database_enabled': False,
                    'database_error': str(db_error),
                    'sample_papers': [
                        {
                            'title': paper['title'],
                            'authors': paper['authors'],
                            'arxiv_id': paper['arxiv_id'],
                            'published_date': paper['published_date']
                        } for paper in sample_papers
                    ]
                })
            }
        
        # Return response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps({
                'message': f"Successfully processed {processed_count} papers",
                'total_papers_fetched': len(papers),
                'processed_count': processed_count,
                'database_enabled': database_enabled,
                'topic': topic_name,
                'papers': [
                    {
                        'title': paper['title'],
                        'authors': paper['authors'],
                        'arxiv_id': paper['arxiv_id'],
                        'published_date': paper['published_date']
                    } for paper in papers[:5]  # First 5 papers
                ]
            })
        }
        
    except Exception as e:
        logger.error(f"Error in ingest handler: {e}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
            },
            'body': json.dumps({'error': str(e)})
        }