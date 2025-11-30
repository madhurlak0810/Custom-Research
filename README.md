# Serverless RAG Research System

## Overview

A complete serverless research paper ingestion and search system built on AWS. The system fetches papers from arXiv, generates embeddings using Amazon Titan, stores them in PostgreSQL with pgvector, and provides semantic search with AI-powered chat responses using OpenAI models via AWS Bedrock.

## Architecture

- **API Gateway** - REST endpoints for ingestion and chat
- **AWS Lambda** - Serverless compute for paper processing and chat
- **Amazon Bedrock** - AI services (Titan embeddings + OpenAI chat models)
- **Aurora PostgreSQL** - Vector database with pgvector extension
- **AWS CDK** - Infrastructure as code

## Features

- **Paper Ingestion** - Fetch and process papers from arXiv API
- **Vector Embeddings** - Amazon Titan Text Embeddings v2 (1024 dimensions)
- **Semantic Search** - pgvector-powered similarity search
- **AI Chat** - OpenAI GPT models via Bedrock for intelligent responses
- **Topic Management** - Automatic topic categorization and management
- **Deduplication** - Prevents duplicate paper storage
- **Serverless** - Fully managed, auto-scaling infrastructure

## Project Structure

```
├── infrastructure/          # AWS CDK infrastructure code
│   ├── lib/
│   │   └── serverless-rag-stack.ts
│   ├── bin/
│   │   └── app.ts
│   └── package.json
├── lambda_ingest/          # Paper ingestion Lambda function
│   ├── handler.py
│   ├── requirements.txt
│   └── common/
│       ├── bedrock_utils.py
│       └── db_utils.py
├── lambda_chat/           # Chat/search Lambda function
│   ├── handler.py
│   ├── requirements.txt
│   └── common/
│       ├── bedrock_utils.py
│       └── db_utils.py
├── lambda_layer/          # Python dependencies layer
│   └── python/
├── common/               # Shared utilities
│   ├── bedrock_utils.py  # AI services integration
│   └── db_utils.py       # Database operations
├── bedrock_utils.py     # Standalone utility (legacy)
└── AWS_DEPLOYMENT_GUIDE.md
```

## Setup & Deployment

### Prerequisites

1. **AWS Account** with appropriate permissions
2. **Node.js** (v18+) for CDK
3. **Python** (3.11+) for Lambda functions
4. **AWS CLI** configured with credentials

### Quick Deploy

1. **Clone and install dependencies:**
```bash
git clone <repository-url>
cd Custom-Research/infrastructure
npm install
```

2. **Deploy the infrastructure:**
```bash
cdk deploy --require-approval never
```

3. **Note the API endpoint** from deployment outputs:
```
Outputs:
ServerlessRagStack.ApiEndpoint = https://xxxxx.execute-api.us-east-1.amazonaws.com/prod/
```

## Usage

The system provides REST API endpoints for paper ingestion and semantic search. Use any HTTP client or build your own interface.

### Direct API Usage

#### 1. Ingest Papers
```bash
curl -X POST "https://your-api-endpoint/prod/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "quantum computing",
    "max_papers": 10
  }'
```

**Response:**
```json
{
  "message": "Successfully processed 10 papers",
  "total_papers_fetched": 10,
  "processed_count": 10,
  "database_enabled": true,
  "topic": "Quantum Computing",
  "papers": [...]
}
```

#### 2. Chat/Search
```bash
curl -X POST "https://your-api-endpoint/prod/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "what are quantum algorithms?",
    "topic": "Quantum Computing",
    "top_k": 5
  }'
```

**Response:**
```json
{
  "response": "Quantum algorithms are computational procedures...",
  "sources": [
    {
      "paper_title": "Quantum Algorithm Design",
      "arxiv_id": "2301.12345",
      "similarity": 0.89,
      "url": "https://arxiv.org/abs/2301.12345"
    }
  ],
  "context_chunks": 5
}
```

## Configuration

### Building Custom Interfaces

You can build custom interfaces using the API endpoints:

```python
import requests

# Ingest papers
response = requests.post(
    "https://your-api-endpoint/prod/ingest",
    json={"query": "quantum computing", "max_papers": 5}
)

# Search and chat
response = requests.post(
    "https://your-api-endpoint/prod/chat",
    json={"query": "what are quantum algorithms?", "topic": "Quantum Computing"}
)
```

### Environment Variables (Lambda)
- `DB_SECRET_ARN` - RDS secret ARN (auto-configured)
- `DB_CLUSTER_ARN` - Aurora cluster ARN (auto-configured)
- `REGION` - AWS region (auto-configured)

### Models Used
- **Embeddings:** `amazon.titan-embed-text-v2:0` (1024 dimensions)
- **Chat:** `openai.gpt-oss-20b-1:0` (OpenAI model via Bedrock)

## Database Schema

### Topics Table
```sql
CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Papers Table
```sql
CREATE TABLE papers (
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
);
```

## Security & Permissions

The system uses least-privilege IAM roles with permissions for:
- Bedrock model invocation (Titan embeddings + OpenAI chat)
- RDS cluster access via IAM database authentication
- Secrets Manager for database credentials
- VPC access for Lambda functions

## Cost Optimization

- **Lambda** - Pay per invocation, cold start optimized
- **Aurora Serverless** - Auto-scaling database, pay for what you use
- **Bedrock** - Pay per token for embeddings and chat
- **API Gateway** - Pay per request

## Monitoring

- CloudWatch logs for Lambda functions
- API Gateway metrics and access logs
- Aurora performance insights
- Bedrock usage metrics

## Troubleshooting

### Common Issues

1. **"Model not available"** - Ensure Bedrock models are enabled in your region
2. **Database connection errors** - Check VPC configuration and security groups
3. **Cold start timeouts** - Increase Lambda timeout for large paper batches
4. **Out of memory** - Increase Lambda memory for embedding generation

### Debug Commands

```bash
# Check Lambda logs
aws logs tail "/aws/lambda/ServerlessRagStack-IngestFunction..." --follow

# Test database connectivity
aws rds describe-db-clusters --db-cluster-identifier your-cluster-name

# Verify Bedrock model access
aws bedrock list-foundation-models --query 'modelSummaries[?contains(modelId, `titan`)]'
```

## Cleanup

To avoid ongoing costs, destroy the infrastructure when done:

```bash
cd infrastructure
cdk destroy
```

## Future Enhancements

- [ ] Multi-modal embeddings for figures and equations
- [ ] Real-time paper notifications
- [ ] Advanced query parsing and filters
- [ ] Paper recommendation system
- [ ] Collaboration features
- [ ] Citation network analysis

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request with clear descriptions

## License

This project is licensed under the MIT License - see the LICENSE file for details.
