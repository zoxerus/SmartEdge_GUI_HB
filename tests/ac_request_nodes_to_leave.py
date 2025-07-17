import socket
import json
import sys

str_TYPE = 'Type'
str_NODE_LEAVE_LIST = 'nll'
str_NODE_IDS = 'nids'

# === STEP 1: Parse UUID from command-line args ===
if len(sys.argv) < 2:
    print("❌ Error: No UUID provided.")
    sys.exit(1)

uuid = sys.argv[1]

# === STEP 2: Build message with dynamic UUID ===
message = {
    str_TYPE: str_NODE_LEAVE_LIST,
    str_NODE_IDS: [uuid]
}

str_message = json.dumps(message)

host = 'localhost'
port = 9999

try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((host, port))
        s.sendall(str_message.encode())
        data = s.recv(1024).decode()
        data_json = json.loads(data)
        print("✅ Leave request accepted. Response:")
        print(json.dumps(data_json, indent=2))
        sys.exit(0)
except Exception as e:
    print(f"❌ Socket error: {e}")
    sys.exit(1)
