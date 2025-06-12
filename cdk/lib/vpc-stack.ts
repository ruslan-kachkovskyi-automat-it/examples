import * as cdk from 'aws-cdk-lib';
import {Construct} from 'constructs';
import * as ec2 from 'aws-cdk-lib/aws-ec2';

export class VpcStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props?: cdk.StackProps) {
        super(scope, id, props);

        const number_of_availability_zones_to_use = 3;

        const vpc = new ec2.Vpc(this, 'TheVPC', {
            ipAddresses: ec2.IpAddresses.cidr('10.0.0.0/16'),
            availabilityZones: this.availabilityZones.slice(0, number_of_availability_zones_to_use),
            reservedAzs:  this.availabilityZones.length - number_of_availability_zones_to_use,
            subnetConfiguration: [{
                name: "public-",
                subnetType: ec2.SubnetType.PUBLIC,
                cidrMask: 24
            }, {
                name: "private-",
                subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
                cidrMask: 24
            }, {
                name: "private-db-",
                subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
                cidrMask: 24
            }],
            gatewayEndpoints: {
                s3: {service: ec2.GatewayVpcEndpointAwsService.S3},
                dynamodb: {service: ec2.GatewayVpcEndpointAwsService.DYNAMODB}
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
            natGateways: number_of_availability_zones_to_use
        })

        vpc.addInterfaceEndpoint("ECR.DKR", {service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER});
        vpc.addInterfaceEndpoint("ECR.API", {service: ec2.InterfaceVpcEndpointAwsService.ECR});
    }
}
