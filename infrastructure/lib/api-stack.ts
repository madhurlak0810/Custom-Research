import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as apigw from 'aws-cdk-lib/aws-apigateway';
import * as lambda from 'aws-cdk-lib/aws-lambda';

export interface ApiStackProps extends cdk.StackProps {
  searchFunction: lambda.Function;
}

export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    const { searchFunction } = props;

    // REST API
    const api = new apigw.RestApi(this, 'CustomResearchApi', {
      restApiName: 'Custom Research API',
      description: 'API for research paper semantic search',
      deployOptions: {
        stageName: 'prod',
      },
    });

    // /search endpoint
    const search = api.root.addResource('search');
    search.addMethod(
      'POST',
      new apigw.LambdaIntegration(searchFunction)
    );

    // Output the API URL
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: `${api.url}search`,
    });
  }
}
