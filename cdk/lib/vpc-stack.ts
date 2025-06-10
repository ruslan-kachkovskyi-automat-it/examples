import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class VpcStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const azs = ["a", "b", "c"].map(az => `${props?.env?.region}${az}`);

    const vpc = new ec2.Vpc(this, 'TheVPC', {
      ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
      availabilityZones: azs,
      gatewayEndpoints: {
        s3: { service: ec2.GatewayVpcEndpointAwsService.S3 },
        dynamodb: { service: ec2.GatewayVpcEndpointAwsService.DYNAMODB }
      },
      flowLogs: {
        all: {
          trafficType: ec2.FlowLogTrafficType.REJECT,
          destination: ec2.FlowLogDestination.toCloudWatchLogs()
        },
        reject: {
          trafficType: ec2.FlowLogTrafficType.ALL,
          destination: ec2.FlowLogDestination.toS3()
        }
      },
      natGateways: azs.length
    })

    vpc.addInterfaceEndpoint("ECR.DKR", {service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER});
    vpc.addInterfaceEndpoint("ECR.API", {service: ec2.InterfaceVpcEndpointAwsService.ECR});
  }
}
