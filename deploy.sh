#!/bin/bash

# AWS Serverless RAG Deployment Script
# This script automates the deployment process

set -e

echo "🚀 AWS Serverless RAG Deployment Script"
echo "========================================"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI not found. Please install AWS CLI first."
    exit 1
fi

# Check if CDK is installed
if ! command -v cdk &> /dev/null; then
    echo "📦 Installing AWS CDK..."
    npm install -g aws-cdk
fi

# Check AWS credentials
echo "🔐 Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "❌ AWS credentials not configured. Please run 'aws configure' first."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

echo "✅ Using AWS Account: $ACCOUNT_ID"
echo "✅ Using Region: $REGION"

# Install Node.js dependencies
echo "📦 Installing CDK dependencies..."
(cd infrastructure && npm install)

# Bootstrap CDK if needed
echo "🏗️ Bootstrapping CDK..."
cdk bootstrap aws://$ACCOUNT_ID/$REGION

# Create Lambda layer
echo "🐍 Creating Python Lambda layer..."
mkdir -p lambda_layer/python

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -t lambda_layer/python/ psycopg2-binary boto3 requests urllib3

# Create layer zip
cd lambda_layer
zip -r python-dependencies.zip python/
cd ..

echo "✅ Lambda layer created: lambda_layer/python-dependencies.zip"

# Check Bedrock model access
echo "🤖 Bedrock models are automatically enabled on first use!"
echo "✅ Amazon Titan Text Embeddings V2: Auto-enabled"
echo "✅ Anthropic Claude 3.5 Sonnet: Auto-enabled"
echo "   (Note: First-time Anthropic users may need to submit use case details)"

# Deploy the stack
echo "🚀 Deploying CDK stack..."
cd infrastructure
cdk deploy ServerlessRagStack --require-approval never
cd ..

# Get outputs
echo "📊 Getting deployment outputs..."
API_URL=$(aws cloudformation describe-stacks --stack-name ServerlessRagStack --query 'Stacks[0].Outputs[?OutputKey==`ApiGatewayUrl`].OutputValue' --output text 2>/dev/null || echo "")
RDS_ENDPOINT=$(aws cloudformation describe-stacks --stack-name ServerlessRagStack --query 'Stacks[0].Outputs[?OutputKey==`DatabaseEndpoint`].OutputValue' --output text 2>/dev/null || echo "")

if [ ! -z "$API_URL" ]; then
    echo "✅ API Gateway URL: $API_URL"
fi

if [ ! -z "$RDS_ENDPOINT" ]; then
    echo "✅ RDS Endpoint: $RDS_ENDPOINT"
fi

# Setup database schema
echo "🗄️ Setting up database schema..."
DB_SECRET_ARN=$(aws cloudformation describe-stacks --stack-name ServerlessRagStack --query 'Stacks[0].Outputs[?OutputKey==`DatabaseSecretArn`].OutputValue' --output text 2>/dev/null || echo "")

if [ ! -z "$DB_SECRET_ARN" ] && [ ! -z "$RDS_ENDPOINT" ]; then
    echo "📝 Database schema will be applied automatically by Lambda functions on first run"
else
    echo "⚠️  Database connection info not available. Schema setup will happen automatically."
fi

echo ""
echo "🎉 Deployment Complete!"
echo "======================"
echo ""
echo "🔗 API Endpoints:"
if [ ! -z "$API_URL" ]; then
    echo "   Ingest Papers: POST $API_URL/ingest"
    echo "   Chat with RAG: POST $API_URL/chat"
else
    echo "   Check CloudFormation stack outputs for API URLs"
fi
echo ""
echo "📊 Test the deployment:"
echo "   # Ingest papers"
echo "   curl -X POST '$API_URL/ingest' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"query\": \"machine learning\", \"max_results\": 5}'"
echo ""
echo "   # Chat with RAG"
echo "   curl -X POST '$API_URL/chat' \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"query\": \"What are recent developments in AI?\", \"max_results\": 3}'"
echo ""
echo "🔍 Monitor logs:"
echo "   aws logs tail /aws/lambda/ServerlessRagStack-IngestFunction --follow"
echo "   aws logs tail /aws/lambda/ServerlessRagStack-ChatFunction --follow"
echo ""
echo "🧹 To cleanup (delete all resources):"
echo "   cd infrastructure && cdk destroy ServerlessRagStack"