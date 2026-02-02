import socket
import struct
import traceback

import boto3

# Dictionary with established VPC endpoint service connections
# Key: VPC Endpoint ID
# Value: Owner AWS Account ID
VPC_ENDPOINT_SERVICE_CONNECTIONS = dict()

ec2 = boto3.client("ec2")


def update_vpc_endpoint_service_connections():
    connections = ec2.describe_vpc_endpoint_connections().get('VpcEndpointConnections', [])
    for connection in connections:
        VPC_ENDPOINT_SERVICE_CONNECTIONS[connection["VpcEndpointId"]] = connection["VpcEndpointOwner"]


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

    ip_protocol_version = header[13]
    offset = 12 if ip_protocol_version == 0x11 else 36
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


def get_vpc_endpoint_id(pp2_payload):
    # Parse and iterate over Type-Length-Value (TLV) vectors
    for key, value in parse_tlv(pp2_payload):
        if key == 0xEA and value[0] == 0x01:  # PP2_TYPE_AWS and PP2_SUBTYPE_AWS_VPCE_ID
            vpce_id = value[1:].decode("UTF-8")
            return vpce_id

    return None


def main():
    update_vpc_endpoint_service_connections()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 80))
    server.listen(5)

    print("VPC_ENDPOINT_SERVICE_CONNECTIONS", VPC_ENDPOINT_SERVICE_CONNECTIONS)

    while True:
        connection, (source_ip, _) = server.accept()
        print(f"Accepted connection from {source_ip}")
        # We need to always read it before the application can start reading data
        # We should connect only via NLB to avoid confusion
        pp2_payload = read_proxy_protocol_payload(connection)
        try:
            vpce_id = get_vpc_endpoint_id(pp2_payload)
            if vpce_id:
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
