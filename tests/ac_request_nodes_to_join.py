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
str_HB_LENGTH = 'hb_length'
str_HB_WINDOW = 'hb_window'
str_HB_INTERVAL = 'hb_interval'

# === STEP 1: Parse arguments ===
parser = argparse.ArgumentParser(description="Send join request to Coordinator")

parser.add_argument("uuid", help="UUID of the node to join")
parser.add_argument("--swarm", required=True, help="Target swarm table name")

# Heartbeat toggle
parser.add_argument("--heartbeat", choices=["true", "false"], default="false", help="Enable heartbeat for this node")

# New heartbeat parameters (optional, only used if --heartbeat true)
parser.add_argument("--length", type=int, help="Heartbeat chain length (e.g., 100, 500, 1000, ...)")
parser.add_argument("--window", type=int, help="Heartbeat verification window (e.g., 2, 3, 4, 5)")
parser.add_argument("--interval", type=float, help="Heartbeat interval in seconds (e.g., 1, 2, 3)")

args = parser.parse_args()

uuid = args.uuid
swarm = args.swarm
heartbeat_enabled = args.heartbeat.lower() == "true"

# === STEP 2: Build message with dynamic UUID, swarm, and heartbeat ===
message = {
    str_TYPE: str_NODE_JOIN_LIST,
    str_NODE_IDS: [uuid],
    str_SWARM: swarm,
    str_HEARTBEAT: heartbeat_enabled
}

# Add heartbeat parameters only if heartbeat is enabled
if heartbeat_enabled:
    if args.length is not None:
        message[str_HB_LENGTH] = args.length
    if args.window is not None:
        message[str_HB_WINDOW] = args.window
    if args.interval is not None:
        message[str_HB_INTERVAL] = args.interval

# Serialize
str_message = json.dumps(message)
print("message is: ")
print(str_message)
# === STEP 3: Send message to Coordinator over TCP ===
host = "10.1.255.254"
port = 9999

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        encoded_message = str_message.encode()
        print(f"encoded message: ", encoded_message)
        s.sendall(encoded_message)
        try:
            data = s.recv(1024)
            if not data:
                print("No Data Received")
            else: 
                data_json = json.loads(data)
                print("✅ Join request accepted. Response:")
                print(json.dumps(data_json, indent=2))
        except Exception as e:
            print(e)
        # sys.exit(0)

except Exception as e:
    print(f"❌ Socket error: {e}")
    # sys.exit(1)
