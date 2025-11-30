import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as rds from "aws-cdk-lib/aws-rds";

export interface LambdaStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  dbCluster: rds.DatabaseCluster;
  dbSecret: rds.DatabaseSecret;
}

export class LambdaStack extends cdk.Stack {
  public readonly scraperLambda: lambda.Function;
  public readonly searchLambda: lambda.Function;

  constructor(scope: Construct, id: string, props: LambdaStackProps) {
    super(scope, id, props);

    const { vpc, dbCluster, dbSecret } = props;

    // IAM role for Lambda
    const lambdaRole = new iam.Role(this, "LambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaVPCAccessExecutionRole"
        ),
      ],
    });

    // ------------ Scraper Lambda ------------
    this.scraperLambda = new lambda.Function(this, "ScraperLambda", {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: "scraper.handler",
      code: lambda.Code.fromAsset("../lambda/scraper"),
      vpc,
      securityGroups: dbCluster.connections.securityGroups,
      role: lambdaRole,
      environment: {
        DB_SECRET_ARN: dbSecret.secretArn,
        DB_HOST: dbCluster.clusterEndpoint.hostname,
        DB_NAME: "customresearchdb",
      },
      timeout: cdk.Duration.minutes(5),
    });

    dbSecret.grantRead(this.scraperLambda);

    // ------------ Search Lambda ------------
    this.searchLambda = new lambda.Function(this, "SearchLambda", {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: "search.handler",
      code: lambda.Code.fromAsset("../lambda/search"),
      vpc,
      securityGroups: dbCluster.connections.securityGroups,
      role: lambdaRole,
      environment: {
        DB_SECRET_ARN: dbSecret.secretArn,
        DB_HOST: dbCluster.clusterEndpoint.hostname,
        DB_NAME: "customresearchdb",
      },
      timeout: cdk.Duration.seconds(30),
    });

    dbSecret.grantRead(this.searchLambda);
  }
}