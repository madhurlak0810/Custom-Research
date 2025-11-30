#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { ServerlessRagStack } from '../lib/serverless-rag-stack';

const app = new cdk.App();

// Get configuration from context or environment
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
};

new ServerlessRagStack(app, 'ServerlessRagStack', {
  env,
  description: 'Serverless RAG system for research papers with AWS Bedrock',
});