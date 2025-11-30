import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as apigw from "aws-cdk-lib/aws-apigateway";
import * as lambda from "aws-cdk-lib/aws-lambda";

export interface ApiStackProps extends cdk.StackProps {
  searchFunction: lambda.Function;
  scraperFunction: lambda.Function;
}

export class ApiStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: ApiStackProps) {
    super(scope, id, props);

    const { searchFunction, scraperFunction } = props;

    const api = new apigw.RestApi(this, "CustomResearchApi", {
      restApiName: "Custom Research API",
    });

    // /search endpoint
    const search = api.root.addResource("search");
    search.addMethod("POST", new apigw.LambdaIntegration(searchFunction));

    // /scrape endpoint
    const scrape = api.root.addResource("scrape");
    scrape.addMethod("POST", new apigw.LambdaIntegration(scraperFunction));

    new cdk.CfnOutput(this, "ApiUrl", {
      value: api.url ?? "undefined",
    });
  }
}