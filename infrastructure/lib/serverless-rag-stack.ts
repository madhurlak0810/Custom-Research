import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as rds from 'aws-cdk-lib/aws-rds';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';
import * as path from 'path';

export class ServerlessRagStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // VPC for RDS
    const vpc = new ec2.Vpc(this, 'RagVPC', {
      maxAzs: 2,
      natGateways: 1, // Enable NAT Gateway for internet access
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
        {
          name: 'Isolated',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // Security group for RDS
    const dbSecurityGroup = new ec2.SecurityGroup(this, 'DatabaseSG', {
      vpc,
      description: 'Security group for RDS PostgreSQL',
      allowAllOutbound: false,
    });

    // Security group for Lambda
    const lambdaSecurityGroup = new ec2.SecurityGroup(this, 'LambdaSG', {
      vpc,
      description: 'Security group for Lambda functions',
      allowAllOutbound: true,
    });

    // Security group for EC2 (Chat UI)
    const webSecurityGroup = new ec2.SecurityGroup(this, 'WebSG', {
      vpc,
      description: 'Security group for Chat UI EC2 instance',
      allowAllOutbound: true,
    });

    webSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP traffic'
    );

    webSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(22),
      'Allow SSH access'
    );

    // Allow Lambda to connect to RDS
    dbSecurityGroup.addIngressRule(
      lambdaSecurityGroup,
      ec2.Port.tcp(5432),
      'Allow Lambda access to PostgreSQL'
    );

    // RDS PostgreSQL with pgvector
    const database = new rds.DatabaseCluster(this, 'RagDatabase', {
      engine: rds.DatabaseClusterEngine.auroraPostgres({
        version: rds.AuroraPostgresEngineVersion.VER_16_6,
      }),
      credentials: rds.Credentials.fromGeneratedSecret('ragadmin'),
      defaultDatabaseName: 'ragdb',
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
      },
      securityGroups: [dbSecurityGroup],
      writer: rds.ClusterInstance.serverlessV2('writer', {
        autoMinorVersionUpgrade: false,
      }),
      serverlessV2MinCapacity: 0.5,
      serverlessV2MaxCapacity: 2,
      deletionProtection: false, // Set to true for production
      removalPolicy: cdk.RemovalPolicy.DESTROY, // Change for production
    });

    // IAM role for Lambda functions
    const lambdaRole = new iam.Role(this, 'LambdaExecutionRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaVPCAccessExecutionRole'),
      ],
      inlinePolicies: {
        BedrockAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
                'bedrock:InvokeModelWithResponseStream',
              ],
              resources: [
                'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v1',
                'arn:aws:bedrock:*::foundation-model/amazon.titan-embed-text-v2:0',
                'arn:aws:bedrock:*::foundation-model/openai.gpt-oss-20b-1:0',
              ],
            }),
          ],
        }),
        RDSAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'rds-db:connect',
              ],
              resources: [database.clusterArn],
            }),
          ],
        }),
        SecretsManagerAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'secretsmanager:GetSecretValue',
              ],
              resources: [database.secret?.secretArn || '*'],
            }),
          ],
        }),
      },
    });

    // Python layer with dependencies
    const pythonLayer = new lambda.LayerVersion(this, 'PythonDepsLayer', {
      code: lambda.Code.fromAsset('../lambda_layer'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description: 'Python dependencies for RAG functions',
    });

    // Common environment variables
    const commonEnvVars = {
      DB_SECRET_ARN: database.secret?.secretArn || '',
      DB_CLUSTER_ARN: database.clusterArn,
      REGION: this.region,
    };

    // Ingest Lambda function
    const ingestFunction = new lambda.Function(this, 'IngestFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.main',
      code: lambda.Code.fromAsset('../lambda_ingest'),
      layers: [pythonLayer],
      role: lambdaRole,
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [lambdaSecurityGroup],
      timeout: cdk.Duration.minutes(15),
      memorySize: 1024,
      environment: {
        ...commonEnvVars,
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
    });

    // Chat Lambda function
    const chatFunction = new lambda.Function(this, 'ChatFunction', {
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.main',
      code: lambda.Code.fromAsset('../lambda_chat'),
      layers: [pythonLayer],
      role: lambdaRole,
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
      },
      securityGroups: [lambdaSecurityGroup],
      timeout: cdk.Duration.minutes(5),
      memorySize: 512,
      environment: {
        ...commonEnvVars,
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
    });

    // API Gateway
    const api = new apigateway.RestApi(this, 'RagApi', {
      restApiName: 'Serverless RAG API',
      description: 'API for serverless RAG system',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key'],
      },
    });

    // API Resources with CORS enabled
    const ingestResource = api.root.addResource('ingest');
    ingestResource.addMethod('POST', new apigateway.LambdaIntegration(ingestFunction, {
      proxy: true,
    }), {
      methodResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
            'method.response.header.Access-Control-Allow-Headers': true,
            'method.response.header.Access-Control-Allow-Methods': true,
          },
        },
        {
          statusCode: '400',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
          },
        },
        {
          statusCode: '500',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
          },
        },
      ],
    });

    const chatResource = api.root.addResource('chat');
    chatResource.addMethod('POST', new apigateway.LambdaIntegration(chatFunction, {
      proxy: true,
    }), {
      methodResponses: [
        {
          statusCode: '200',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
            'method.response.header.Access-Control-Allow-Headers': true,
            'method.response.header.Access-Control-Allow-Methods': true,
          },
        },
        {
          statusCode: '400',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
          },
        },
        {
          statusCode: '500',
          responseParameters: {
            'method.response.header.Access-Control-Allow-Origin': true,
          },
        },
      ],
    });

    // IAM role for EC2 instance
    const ec2Role = new iam.Role(this, 'ChatUIInstanceRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    const instanceProfile = new iam.InstanceProfile(this, 'ChatUIInstanceProfile', {
      role: ec2Role,
    });

    // User data script to setup the web server
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      'exec > >(tee /var/log/user-data.log) 2>&1',
      'set -x', // Enable debug output
      
      'echo "=== Starting user data script ==="',
      'date',
      
      // Update system
      'yum update -y',
      'yum install -y httpd git',
      
      // Start and enable Apache
      'systemctl start httpd',
      'systemctl enable httpd',
      'systemctl status httpd',
      
      // Setup web directory
      'cd /var/www/html',
      'pwd',
      'ls -la',
      
      // Remove default content
      'rm -rf * .git',
      'ls -la',
      
      // Clone repository with better error handling
      'echo "=== Cloning repository ==="',
      'git clone https://github.com/madhurlak0810/Custom-Research.git . || {',
      '  echo "Git clone failed, trying again..."',
      '  sleep 10',
      '  git clone https://github.com/madhurlak0810/Custom-Research.git . || {',
      '    echo "Second git clone failed, creating minimal structure"',
      '    mkdir -p chat_ui',
      '    echo "Error: Could not clone repository" > chat_ui/error.html',
      '  }',
      '}',
      
      // Verify structure
      'echo "=== Verifying directory structure ==="',
      'ls -la',
      'ls -la chat_ui/ || echo "chat_ui directory does not exist"',
      
      // Set permissions
      'chmod -R 755 /var/www/html',
      'chown -R apache:apache /var/www/html',
      
      // Create main index page
      'echo "=== Creating main index page ==="',
      `cat > /var/www/html/index.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>Research Assistant</title>
    <meta http-equiv="refresh" content="3; url=/chat_ui/">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            text-align: center; 
            margin: 50px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .container {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }
        .loading { color: #fff; margin: 20px 0; }
        a { color: #fff; text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🧠 Research Assistant</h1>
        <p class="loading">Initializing chat interface...</p>
        <p><a href="/chat_ui/">Continue to Chat UI</a></p>
        <hr style="margin: 20px 0; opacity: 0.3;">
        <p><small>API Endpoint: ${api.url}</small></p>
    </div>
</body>
</html>
EOF`,
      
      // Create config file if chat_ui exists
      'echo "=== Creating configuration ==="',
      'if [ -d "/var/www/html/chat_ui" ]; then',
      `  cat > /var/www/html/chat_ui/config.js << 'EOF'
// Auto-generated configuration
window.CONFIG = {
    apiEndpoint: '${api.url.replace(/\/$/, '')}',
    autoLoad: true
};
EOF`,
      '  echo "Config file created successfully"',
      '  cat /var/www/html/chat_ui/config.js',
      'else',
      '  echo "ERROR: chat_ui directory not found"',
      '  mkdir -p /var/www/html/chat_ui',
      '  echo "<h1>Chat UI Setup Error</h1><p>Repository clone failed</p>" > /var/www/html/chat_ui/index.html',
      'fi',
      
      // Configure Apache
      'echo "=== Configuring Apache ==="',
      `cat > /etc/httpd/conf.d/chatui.conf << 'EOF'
<VirtualHost *:80>
    DocumentRoot /var/www/html
    DirectoryIndex index.html
    
    # Enable CORS
    Header always set Access-Control-Allow-Origin "*"
    Header always set Access-Control-Allow-Methods "GET, POST, OPTIONS"
    Header always set Access-Control-Allow-Headers "Content-Type, Authorization"
    
    # Security headers
    Header always set X-Content-Type-Options nosniff
    Header always set X-Frame-Options DENY
    Header always set X-XSS-Protection "1; mode=block"
    
    # Allow access to all files
    <Directory "/var/www/html">
        AllowOverride None
        Require all granted
        Options -Indexes +FollowSymLinks
    </Directory>
    
    ErrorLog /var/log/httpd/error_log
    CustomLog /var/log/httpd/access_log combined
</VirtualHost>
EOF`,
      
      // Create enhanced health endpoint
      'echo "=== Creating health endpoint ==="',
      'mkdir -p /var/www/html/health',
      `cat > /var/www/html/health/index.html << 'EOF'
{
  "status": "healthy",
  "timestamp": "TIMESTAMP_PLACEHOLDER", 
  "service": "chat-ui",
  "api_endpoint": "${api.url.replace(/\/$/, '')}",
  "setup_completed": true
}
EOF`,
      'sed -i "s/TIMESTAMP_PLACEHOLDER/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" /var/www/html/health/index.html',
      
      // Final checks and restart
      'echo "=== Final verification ==="',
      'ls -la /var/www/html/',
      'ls -la /var/www/html/chat_ui/ || echo "No chat_ui directory"',
      'systemctl restart httpd',
      'systemctl status httpd',
      
      'echo "=== Setup completed ==="',
      'date',
      'echo "User data script finished"'
    );

    // EC2 instance for hosting chat UI
    const chatUIInstance = new ec2.Instance(this, 'ChatUIInstance', {
      vpc,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
      },
      securityGroup: webSecurityGroup,
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux2(),
      userData: userData,
      role: ec2Role,
      keyName: 'chatui-debug', // Enable SSH for debugging
    });

    // Outputs
    new cdk.CfnOutput(this, 'ApiEndpoint', {
      value: api.url,
      description: 'API Gateway endpoint URL',
    });

    new cdk.CfnOutput(this, 'DatabaseEndpoint', {
      value: database.clusterEndpoint.hostname,
      description: 'RDS cluster endpoint',
    });

    new cdk.CfnOutput(this, 'DatabaseSecretArn', {
      value: database.secret?.secretArn || '',
      description: 'Database credentials secret ARN',
    });

    new cdk.CfnOutput(this, 'ChatUIUrl', {
      value: `http://${chatUIInstance.instancePublicDnsName}`,
      description: 'Chat UI web interface URL',
    });

    new cdk.CfnOutput(this, 'ChatUIInstanceId', {
      value: chatUIInstance.instanceId,
      description: 'EC2 instance ID for Chat UI',
    });
  }
}