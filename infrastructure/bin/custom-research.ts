#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { NetworkingStack } from "../lib/networking-stack";
import { DatabaseStack } from "../lib/database-stack";
import { LambdaStack } from "../lib/lambda-stack";
import { ApiStack } from "../lib/api-stack";

const app = new cdk.App();

const networking = new NetworkingStack(app, "NetworkingStack", {});

const database = new DatabaseStack(app, "DatabaseStack", {
  vpc: networking.vpc,
});

const lambdaStack = new LambdaStack(app, "LambdaStack", {
  vpc: networking.vpc,
  dbCluster: database.dbCluster,
  dbSecret: database.dbSecret,
});

new ApiStack(app, "ApiStack", {
  searchFunction: lambdaStack.searchLambda,
  scraperFunction: lambdaStack.scraperLambda,
});