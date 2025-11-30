#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { NetworkingStack } from '../lib/networking-stack';
import { DatabaseStack } from '../lib/database-stack';
import { LambdaStack } from '../lib/lambda-stack';
import { ApiStack } from '../lib/api-stack';

const app = new cdk.App();

// 1. Networking/VPC stack
const networking = new NetworkingStack(app, 'NetworkingStack', {});

// 2. Database stack (Aurora)
const database = new DatabaseStack(app, 'DatabaseStack', {
  vpc: networking.vpc,
});

// 3. Lambda stack
const lambdas = new LambdaStack(app, 'LambdaStack', {
  vpc: networking.vpc,
  dbCluster: database.dbCluster,
});

// 4. API Gateway stack
new ApiStack(app, 'ApiStack', {
  searchFunction: lambdas.searchLambda,
});
