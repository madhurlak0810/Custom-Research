import os
import logging
import json
from typing import Optional, Tuple, Any, List
import boto3

logger = logging.getLogger(__name__)

# Database connection - try multiple adapters
_connection = None
_db_adapter = None

def get_connection():
    """Get database connection with fallback adapters"""
    global _connection, _db_adapter
    
    if _connection is not None:
        return _connection
    
    # Get database credentials from Secrets Manager
    db_host, db_port, db_name, db_user, db_password = get_db_credentials()
    
    # Try different PostgreSQL adapters
    adapters = [
        ('psycopg2', _connect_psycopg2),
        ('pg8000', _connect_pg8000)
    ]
    
    for adapter_name, connect_func in adapters:
        try:
            logger.info(f"Attempting to connect using {adapter_name}")
            _connection = connect_func(db_host, db_port, db_name, db_user, db_password)
            _db_adapter = adapter_name
            logger.info(f"Successfully connected using {adapter_name}")
            return _connection
        except Exception as e:
            logger.warning(f"{adapter_name} connection failed: {e}")
            continue
    
    raise Exception("All database adapters failed to connect")

def _connect_psycopg2(host, port, dbname, user, password):
    """Connect using psycopg2"""
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    connection = psycopg2.connect(
        host=host,
        port=port,
        database=dbname,
        user=user,
        password=password,
        cursor_factory=RealDictCursor
    )
    return connection

def _connect_pg8000(host, port, dbname, user, password):
    """Connect using pg8000"""
    import pg8000.native
    
    connection = pg8000.native.Connection(
        host=host,
        port=int(port),
        database=dbname,
        user=user,
        password=password
    )
    return connection

def execute_query(query: str, params: Tuple = None, fetch: bool = False) -> List[Any]:
    """Execute database query with adapter-specific handling"""
    global _db_adapter
    
    connection = get_connection()
    
    try:
        if _db_adapter == 'psycopg2':
            return _execute_psycopg2(connection, query, params, fetch)
        elif _db_adapter == 'pg8000':
            return _execute_pg8000(connection, query, params, fetch)
        else:
            raise Exception(f"Unknown adapter: {_db_adapter}")
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        # Reset connection on error
        global _connection
        _connection = None
        raise

def _execute_psycopg2(connection, query: str, params: Tuple = None, fetch: bool = False):
    """Execute query using psycopg2"""
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        
        if fetch:
            return cursor.fetchall()
        else:
            connection.commit()
            return []

def _execute_pg8000(connection, query: str, params: Tuple = None, fetch: bool = False):
    """Execute query using pg8000"""
    try:
        # pg8000 uses positional parameters differently - need to convert %s to named or use direct substitution
        if params:
            # Convert %s to positional parameters for pg8000
            # Replace %s with :1, :2, etc.
            param_count = query.count('%s')
            if param_count > 0:
                for i in range(param_count):
                    query = query.replace('%s', f':{i+1}', 1)
                
                # Create named parameter dict
                param_dict = {str(i+1): params[i] for i in range(len(params))}
                result = connection.run(query, **param_dict)
            else:
                result = connection.run(query)
        else:
            result = connection.run(query)
        
        if fetch:
            return result if result else []
        else:
            return []
    except Exception as e:
        logger.error(f"pg8000 query execution failed: {e}")
        # Fallback - try with string formatting (less safe but might work)
        try:
            if params and '%s' in query:
                # Simple string substitution as last resort
                formatted_query = query % params
                result = connection.run(formatted_query)
                if fetch:
                    return result if result else []
                else:
                    return []
        except Exception as e2:
            logger.error(f"pg8000 fallback execution also failed: {e2}")
        
        raise e

def get_db_credentials() -> Tuple[str, str, str, str, str]:
    """Get database credentials from environment or Secrets Manager"""
    
    # For local testing
    if os.getenv('LOCAL_DEV'):
        return (
            os.getenv('DB_HOST', 'localhost'),
            os.getenv('DB_PORT', '5432'),
            os.getenv('DB_NAME', 'research'),
            os.getenv('DB_USER', 'postgres'),
            os.getenv('DB_PASSWORD', 'password')
        )
    
    # For Lambda - get from Secrets Manager
    secret_arn = os.getenv('DB_SECRET_ARN')
    if not secret_arn:
        raise Exception("DB_SECRET_ARN environment variable not set")
    
    try:
        secrets_client = boto3.client('secretsmanager')
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        secret_data = json.loads(response['SecretString'])
        
        return (
            secret_data['host'],
            str(secret_data.get('port', 5432)),
            secret_data['dbname'],
            secret_data['username'],
            secret_data['password']
        )
    except Exception as e:
        logger.error(f"Failed to get database credentials: {e}")
        raise

def close_connection():
    """Close database connection"""
    global _connection
    if _connection:
        try:
            if _db_adapter == 'psycopg2':
                _connection.close()
            elif _db_adapter == 'pg8000':
                _connection.close()
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
        finally:
            _connection = None

def test_connection():
    """Test database connection"""
    try:
        # Simple test query
        result = execute_query("SELECT 1", fetch=True)
        logger.info(f"Database test successful: {result}")
        return True
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return False

def initialize_database():
    """Initialize database schema if it doesn't exist"""
    try:
        # Test connection first
        if not test_connection():
            raise Exception("Database connection test failed")
        
        # Check if papers table exists
        check_query = """
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'papers'
        """
        
        result = execute_query(check_query, fetch=True)
        
        if not result:
            logger.info("Creating database schema...")
            
            # Enable vector extension
            execute_query("CREATE EXTENSION IF NOT EXISTS vector")
            
            # Create topics table
            create_topics_query = """
            CREATE TABLE IF NOT EXISTS topics (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            # Create papers table with vector column
            create_papers_query = """
            CREATE TABLE IF NOT EXISTS papers (
                id SERIAL PRIMARY KEY,
                arxiv_id VARCHAR(50) UNIQUE NOT NULL,
                title TEXT NOT NULL,
                authors TEXT,
                abstract TEXT,
                published_date DATE,
                categories TEXT,
                topic_id INTEGER REFERENCES topics(id),
                embedding VECTOR(1024),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            
            execute_query(create_topics_query)
            execute_query(create_papers_query)
            
            # Create index for vector similarity search
            create_index_query = """
            CREATE INDEX IF NOT EXISTS papers_embedding_idx 
            ON papers USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
            """
            execute_query(create_index_query)
            
            logger.info("Database schema created successfully")
        else:
            logger.info("Database schema already exists")
            
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def get_or_create_topic(name: str, description: str = None) -> int:
    """Get existing topic ID or create new topic"""
    global _db_adapter
    try:
        # Use standard SQL for both adapters
        query = "SELECT id FROM topics WHERE name = %s"
        result = execute_query(query, (name,), fetch=True)
        
        if result and len(result) > 0:
            # Handle different result formats
            if isinstance(result[0], dict):
                return result[0]['id']
            elif isinstance(result[0], (list, tuple)):
                return result[0][0] 
            else:
                return result[0]
        
        # Create new topic
        insert_query = "INSERT INTO topics (name, description) VALUES (%s, %s) RETURNING id"
            
        result = execute_query(insert_query, (name, description), fetch=True)
        
        if result and len(result) > 0:
            if isinstance(result[0], dict):
                return result[0]['id']
            elif isinstance(result[0], (list, tuple)):
                return result[0][0]
            else:
                return result[0]
        else:
            raise Exception("Failed to create topic - no ID returned")
        
    except Exception as e:
        logger.error(f"Error getting/creating topic: {e}")
        raise

def paper_exists(arxiv_id: str) -> bool:
    """Check if paper already exists in database"""
    global _db_adapter
    try:
        query = "SELECT id FROM papers WHERE arxiv_id = %s"
            
        result = execute_query(query, (arxiv_id,), fetch=True)
        return len(result) > 0
    except Exception as e:
        logger.error(f"Error checking if paper exists: {e}")
        return False

def insert_paper(paper: dict, topic_id: int) -> int:
    """Insert paper into database with embeddings"""
    global _db_adapter
    try:
        # Generate embeddings for the paper
        text_content = f"{paper['title']}\n\n{paper['abstract']}"
        
        # Import here to avoid circular imports
        try:
            from bedrock_utils import generate_embeddings
        except ImportError:
            # Try relative import for Lambda
            from .bedrock_utils import generate_embeddings
            
        embeddings = generate_embeddings([text_content])
        
        if not embeddings:
            raise Exception("Failed to generate embeddings")
        
        # Insert paper into database
        query = """
        INSERT INTO papers (arxiv_id, title, authors, abstract, published_date, 
                           categories, topic_id, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        
        # Format embedding as PostgreSQL vector format
        embedding = embeddings[0]
        if hasattr(embedding, 'tolist'):
            embedding_list = embedding.tolist()
        else:
            embedding_list = list(embedding)
        
        # Convert to PostgreSQL vector format with square brackets
        embedding_str = '[' + ','.join(map(str, embedding_list)) + ']'
        
        values = (
            paper['arxiv_id'],
            paper['title'],
            paper['authors'],
            paper['abstract'],
            paper['published_date'],
            paper['categories'],
            topic_id,
            embedding_str
        )
        
        result = execute_query(query, values, fetch=True)
        
        if result and len(result) > 0:
            if isinstance(result[0], dict):
                return result[0]['id']
            elif isinstance(result[0], (list, tuple)):
                return result[0][0]
            else:
                return result[0]
        else:
            raise Exception("Failed to insert paper - no ID returned")
        
    except Exception as e:
        logger.error(f"Error inserting paper: {e}")
        raise