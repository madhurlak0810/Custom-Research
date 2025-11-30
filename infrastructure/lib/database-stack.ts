import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export interface DatabaseStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
}

export class DatabaseStack extends cdk.Stack {
  public readonly dbCluster: rds.ServerlessCluster;

  constructor(scope: Construct, id: string, props: DatabaseStackProps) {
    super(scope, id, props);

    const { vpc } = props;

    // Security group for Aurora Postgres
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DbSecurityGroup', {
      vpc,
      allowAllOutbound: true,
      description: 'Security group for Aurora Serverless PostgreSQL',
    });

    // Allow Lambda functions (in future) to connect
    dbSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(5432),
      'Allow Postgres access'
    );

    // Aurora Serverless v2 Cluster
    this.dbCluster = new rds.ServerlessCluster(this, 'CustomResearchCluster', {
      engine: rds.DatabaseClusterEngine.AURORA_POSTGRESQL,
      parameterGroup: rds.ParameterGroup.fromParameterGroupName(
        this,
        'ParameterGroup',
        'default.aurora-postgresql15'
      ),
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      securityGroups: [dbSecurityGroup],

      defaultDatabaseName: 'customresearchdb',

      // Cost control
      scaling: {
        minCapacity: 1, // lowest ACU
        maxCapacity: 1,   // prevent bill shock
        autoPause: cdk.Duration.minutes(30), // automatically pause
      },
    });

    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: this.dbCluster.clusterEndpoint.hostname,
    });
  }
}
