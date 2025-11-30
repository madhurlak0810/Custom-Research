import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as ec2 from "aws-cdk-lib/aws-ec2";

export interface DatabaseStackProps extends cdk.StackProps {
  vpc: ec2.Vpc;
}

export class DatabaseStack extends cdk.Stack {
  public readonly dbCluster: rds.DatabaseCluster;
  public readonly dbSecret: rds.DatabaseSecret;

  constructor(scope: Construct, id: string, props: DatabaseStackProps) {
    super(scope, id, props);

    const { vpc } = props;

    // Create secret
    const dbSecret = new rds.DatabaseSecret(this, "DbSecret", {
      username: "postgres",
    });

    this.dbSecret = dbSecret;

    // Security group
    const dbSecurityGroup = new ec2.SecurityGroup(this, "DbSecurityGroup", {
      vpc,
      allowAllOutbound: true,
      description: "Security group for Aurora PostgreSQL",
    });

    dbSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(5432),
      "Allow Postgres access temporarily"
    );

    // Aurora PostgreSQL Serverless v2
    this.dbCluster = new rds.DatabaseCluster(this, "CustomResearchCluster", {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_1,
      }),

      credentials: rds.Credentials.fromSecret(dbSecret),
      defaultDatabaseName: "customresearchdb",

      // Serverless v2 instances
      writer: rds.ClusterInstance.serverlessV2("writer", {
        scaleWithWriter: true,
      }),

      readers: [
        rds.ClusterInstance.serverlessV2("reader", {
          scaleWithWriter: true,
        }),
      ],

      vpc,
      securityGroups: [dbSecurityGroup],
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },

      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    new cdk.CfnOutput(this, "DatabaseEndpoint", {
      value: this.dbCluster.clusterEndpoint.hostname,
    });
  }
}