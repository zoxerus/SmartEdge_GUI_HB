import socket
import json
import sys
import argparse

# === Constants ===
str_TYPE = 'Type'
str_NODE_JOIN_LIST = 'njl'
str_NODE_LEAVE_LIST = 'nll'
str_NODE_IDS = 'nids'
str_SWARM = 'swarm'
str_HEARTBEAT = 'heartbeat'

# === STEP 1: Parse arguments ===
parser = argparse.ArgumentParser(description="Send join request to Coordinator")
parser.add_argument("uuid", help="UUID of the node to join")
parser.add_argument("--swarm", required=True, help="Target swarm table name")
parser.add_argument("--heartbeat", choices=["true", "false"], default="false", help="Enable heartbeat for this node")
args = parser.parse_args()

uuid = args.uuid
swarm = args.swarm
heartbeat = args.heartbeat.lower() == "true"   # convert to boolean

# === STEP 2: Build message with dynamic UUID, swarm, and heartbeat ===
message = {
    str_TYPE: str_NODE_JOIN_LIST,
    str_NODE_IDS: [uuid],
    str_SWARM: swarm,
    str_HEARTBEAT: heartbeat
}

str_message = json.dumps(message)

# === STEP 3: Send message to Coordinator over TCP ===
host = 'localhost'
port = 9999

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall(str_message.encode())
        data = s.recv(1024).decode()
        data_json = json.loads(data)
        print("✅ Join request accepted. Response:")
        print(json.dumps(data_json, indent=2))
        sys.exit(0)
except Exception as e:
    print(f"❌ Socket error: {e}")
    sys.exit(1)
