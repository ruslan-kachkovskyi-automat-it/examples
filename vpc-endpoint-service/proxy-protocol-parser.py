import socket
import struct
import traceback

import boto3

# Set of the NLBs private IP addresses
# PrivateLink traffic is coming from the NLB private IP address
# https://docs.aws.amazon.com/elasticloadbalancing/latest/network/edit-target-group-attributes.html#client-ip-preservation
VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES = set()

# Dictionary with established VPC endpoint service connections
# Key: VPC Endpoint ID
# Value: Owner AWS Account ID
VPC_ENDPOINT_SERVICE_CONNECTIONS = dict()

ec2 = boto3.client("ec2", region_name="eu-west-1")


def get_nlb_private_ip_addresses(arn):
    nlb_id = arn.split("/")[-1]
    filters = [
        {
            'Name': 'interface-type',
            'Values': ["network_load_balancer"]
        },
        {
            "Name": "description",
            "Values": [f"ELB net/nlb/{nlb_id}"]
        }
    ]

    network_interfaces = ec2.describe_network_interfaces(Filters=filters)
    for eni in network_interfaces.get("NetworkInterfaces", []):
        if eni["PrivateIpAddress"]:
            yield eni["PrivateIpAddress"]


def update_vpc_endpoint_connections_info():
    connections = ec2.describe_vpc_endpoint_connections().get('VpcEndpointConnections', [])
    nlb_ips = (
        ip
        for conn in connections
        for nlb in conn.get("NetworkLoadBalancerArns", [])
        for ip in get_nlb_private_ip_addresses(nlb)
    )

    service_clients = {
        connection["VpcEndpointId"]: connection["VpcEndpointOwner"]
        for connection in connections
    }

    VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES.update(nlb_ips)
    VPC_ENDPOINT_SERVICE_CONNECTIONS.update(service_clients)


def read_exact(sock, n):
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("Socket closed")
        data += chunk
    return data


# https://docs.aws.amazon.com/elasticloadbalancing/latest/network/edit-target-group-attributes.html#proxy-protocol
def read_proxy_protocol_payload(connection):
    header = read_exact(connection, 16)

    if header[:12] != b"\r\n\r\n\0\r\nQUIT\n":
        raise ValueError("Not Proxy Protocol v2")

    ver_cmd = header[12]
    if (ver_cmd >> 4) != 2 or (ver_cmd & 0x0F) != 1:
        raise ValueError("Unsupported PPv2 header")

    length = struct.unpack("!H", header[14:16])[0]
    payload = read_exact(connection, length)

    # Offset depends on the IP protocol version
    fam_proto = header[13]
    offset = 12 if fam_proto == 0x11 else 36
    return payload[offset:]


def parse_tlv(data):
    i = 0
    while i + 3 <= len(data):
        tlv_type = data[i]
        tlv_len = int.from_bytes(data[i + 1:i + 3], "big")
        i += 3
        value = data[i:i + tlv_len]
        i += tlv_len
        yield tlv_type, value


def parse_proxy_protocol_v2(payload):
    # Parse and iterate over Type-Length-Value (TLV) vectors
    for key, value in parse_tlv(payload):
        if key == 0xEA and value[0] == 0x01:  # PP2_TYPE_AWS and PP2_SUBTYPE_AWS_VPCE_ID
            vpce_id = value[1:].decode("UTF-8")
            return vpce_id

    return None


def main():
    update_vpc_endpoint_connections_info()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 80))
    server.listen(5)

    print("VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES", VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES)
    print("VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES", VPC_ENDPOINT_SERVICE_CONNECTIONS)

    while True:
        connection, (source_ip, _) = server.accept()
        print(f"Established connection from {source_ip}")
        # We need to always read it before the application data
        pp2_payload = read_proxy_protocol_payload(connection)
        try:
            if source_ip in VPC_ENDPOINT_SERVICE_PRIVATE_IP_ADDRESSES:
                vpce_id = parse_proxy_protocol_v2(pp2_payload)
                partner_aws_account_id = VPC_ENDPOINT_SERVICE_CONNECTIONS[vpce_id]
                payload = f"Your IP is hidden. Hello from the other side.\nConnection was established from {partner_aws_account_id} via {vpce_id}.\n"
            else:
                payload = f"Your IP is {source_ip}.\n"

            connection.send(payload.encode("utf-8"))
        except Exception:
            traceback.print_exc()
        finally:
            connection.close()


if __name__ == "__main__":
    main()
