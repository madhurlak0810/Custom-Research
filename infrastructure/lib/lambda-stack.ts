import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as rds from 'aws-cdk-lib/aws-rds';

export interface LambdaStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
  dbCluster: rds.ServerlessCluster;
}

export class LambdaStack extends cdk.Stack {
  public readonly scraperLambda: lambda.Function;
  public readonly searchLambda: lambda.Function;

  constructor(scope: Construct, id: string, props: LambdaStackProps) {
    super(scope, id, props);

    const { vpc, dbCluster } = props;

    // IAM role for lambdas to access RDS Data API
    const lambdaRole = new iam.Role(this, 'LambdaAuroraRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
    });

    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        'service-role/AWSLambdaVPCAccessExecutionRole'
      )
    );

    lambdaRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName(
        'AmazonRDSDataFullAccess'
      )
    );

    // ------------ Scraper Lambda ------------
    this.scraperLambda = new lambda.Function(this, 'ScraperLambda', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'scraper.handler',
      code: lambda.Code.fromAsset('../lambda/scraper'),
      vpc,
      securityGroups: dbCluster.connections.securityGroups,
      role: lambdaRole,
      environment: {
        DB_SECRET_ARN: dbCluster.secret!.secretArn,
        DB_CLUSTER_ARN: dbCluster.clusterArn,
        DATABASE_NAME: 'customresearchdb',
      },
      timeout: cdk.Duration.minutes(5),
    });

    dbCluster.grantDataApiAccess(this.scraperLambda);

    // ------------ Search Lambda ------------
    this.searchLambda = new lambda.Function(this, 'SearchLambda', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'search.handler',
      code: lambda.Code.fromAsset('../lambda/search'),
      vpc,
      securityGroups: dbCluster.connections.securityGroups,
      role: lambdaRole,
      environment: {
        DB_SECRET_ARN: dbCluster.secret!.secretArn,
        DB_CLUSTER_ARN: dbCluster.clusterArn,
        DATABASE_NAME: 'customresearchdb',
      },
      timeout: cdk.Duration.seconds(30),
    });

    dbCluster.grantDataApiAccess(this.searchLambda);
  }
}
