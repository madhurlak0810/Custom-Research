# AWS Serverless RAG System Deployment Guide

## Prerequisites

1. **AWS Account**: Ensure you have an active AWS account
2. **AWS CLI**: Install and configure AWS CLI with your credentials
3. **Node.js**: Install Node.js 18+ and npm
4. **Python**: Python 3.11+ installed locally

## Step 1: Install AWS CLI and Configure Credentials

```bash
# Install AWS CLI (if not already installed)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Configure your AWS credentials
aws configure
# Enter your Access Key ID, Secret Access Key, region (us-east-1), and output format (json)
```

## Step 2: Install CDK and Dependencies

```bash
# Install AWS CDK globally
npm install -g aws-cdk

# Navigate to the project directory
cd /root/src/Custom-Research

# Install CDK dependencies
cd infrastructure
npm install
cd ..

# Verify CDK installation
cdk --version
```

## Step 3: Bootstrap CDK (One-time setup per AWS account/region)

```bash
# Bootstrap CDK in your AWS account
cdk bootstrap aws://YOUR-ACCOUNT-ID/us-east-1
# Replace YOUR-ACCOUNT-ID with your actual AWS account ID (find it with: aws sts get-caller-identity)
```

## Step 4: Create Python Lambda Layer

```bash
# Create layer directory
mkdir -p lambda_layer/python

# Install Python dependencies for Lambda
pip install -t lambda_layer/python/ psycopg2-binary boto3 requests

# Create the layer zip
cd lambda_layer
zip -r python-dependencies.zip python/
cd ..
```

## Step 5: Amazon Bedrock Models (Automatic Access)

**Good News!** AWS Bedrock models are now automatically enabled when first invoked - no manual activation needed!

- **Amazon Titan Text Embeddings V2**: Automatically available
- **Anthropic Claude 3.5 Sonnet**: Automatically available (some first-time users may need to submit use case details)

The models will be activated automatically when your Lambda functions first invoke them during deployment testing.

## Step 6: Deploy the Infrastructure

```bash
# Deploy the CDK stack (from infrastructure directory)
cd infrastructure
cdk deploy ServerlessRagStack

# This will create:
# - VPC with public/private subnets
# - RDS Aurora PostgreSQL with pgvector
# - Lambda functions for ingestion and chat
# - API Gateway endpoints
# - IAM roles and security groups
```

## Step 7: Set Up Database Schema

```bash
# Get the RDS endpoint from CDK output
RDS_ENDPOINT=$(aws rds describe-db-clusters --db-cluster-identifier serverlessrag-aurora-cluster --query 'DBClusters[0].Endpoint' --output text)

# Connect to the database (password will be retrieved from Secrets Manager)
# Use the database schema file to set up tables
psql -h $RDS_ENDPOINT -U postgres -d ragdb -f database_schema.sql
```

## Step 8: Test the Deployment

### Test Paper Ingestion
```bash
# Get the API Gateway URL from CDK output
API_URL=$(aws cloudformation describe-stacks --stack-name ServerlessRagStack --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' --output text)

# Test paper ingestion
curl -X POST "$API_URL/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "max_results": 5
  }'
```

### Test Chat Interface
```bash
# Test RAG chat
curl -X POST "$API_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the latest developments in transformer architectures?",
    "max_results": 3
  }'
```

## Step 9: Monitor and Manage

### View Logs
```bash
# View Lambda logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/ServerlessRag"

# Stream logs in real-time
aws logs tail /aws/lambda/ServerlessRagStack-IngestFunction --follow
aws logs tail /aws/lambda/ServerlessRagStack-ChatFunction --follow
```

### Update Lambda Code
```bash
# After making changes to Lambda functions, redeploy
cdk deploy ServerlessRagStack
```

## Configuration Options

### Environment Variables
The CDK stack automatically configures these environment variables for Lambda:
- `DB_SECRET_ARN`: Database credentials in Secrets Manager
- `DB_NAME`: Database name (ragdb)
- `BEDROCK_REGION`: AWS region for Bedrock (us-east-1)

### Scaling Configuration
- **Lambda**: Auto-scales based on demand
- **RDS Aurora**: Serverless v2 auto-scaling (0.5-16 ACU)
- **API Gateway**: Built-in scaling

## Cost Optimization

1. **Aurora Serverless v2**: Automatically pauses when not in use
2. **Lambda**: Pay per invocation
3. **Bedrock**: Pay per token/embedding generated
4. **API Gateway**: Pay per request

## Troubleshooting

### Common Issues

1. **Bedrock Access Denied**
   - Models are automatically enabled on first use - no manual activation needed
   - For Anthropic models, first-time users may need to submit use case details
   - Check IAM permissions for Lambda execution role

2. **Database Connection Issues**
   - Verify VPC security groups allow Lambda to RDS connection
   - Check Secrets Manager has correct database credentials

3. **Lambda Timeout**
   - Increase timeout in CDK stack if processing large papers
   - Consider async processing for bulk ingestion

### Cleanup
```bash
# To delete all resources (from infrastructure directory)
cd infrastructure
cdk destroy ServerlessRagStack

# This will remove:
# - All Lambda functions
# - RDS cluster and database
# - VPC and networking components
# - API Gateway
# - IAM roles
```

## Next Steps

1. **Custom Domain**: Add a custom domain to API Gateway
2. **Authentication**: Implement API authentication (AWS Cognito)
3. **Frontend**: Build a web interface to interact with the API
4. **Monitoring**: Set up CloudWatch dashboards and alerts
5. **CI/CD**: Implement automated deployment pipeline