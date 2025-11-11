#!/usr/bin/env python3
import os
import sys
import time
import socket
import signal
import hashlib
import argparse
import tempfile
import logging
import binascii

# ---------------- Config ----------------
DEFAULT_CHAIN_LENGTH = 100
DEFAULT_HASH_FUNCTION = hashlib.sha256
# ----------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HEARTBEAT] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

RUNNING = True

def sigterm_handler(sig, frame):
    global RUNNING
    logging.info("Termination signal received, stopping heartbeats.")
    RUNNING = False

signal.signal(signal.SIGINT, sigterm_handler)
signal.signal(signal.SIGTERM, sigterm_handler)

# ---------- Chain Generation ----------
def _safe_write(path, data):
    dirpath = os.path.dirname(path)
    os.makedirs(dirpath, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=dirpath, delete=False) as tmp:
        tmp.write(data)
        tempname = tmp.name
    os.replace(tempname, path)

def generate_winternitz_chain(output_dir, chain_length=DEFAULT_CHAIN_LENGTH,
                              hash_function=DEFAULT_HASH_FUNCTION, debug=False):
    os.makedirs(output_dir, exist_ok=True)

    x0 = os.urandom(32)
    chain = [x0]

    if debug:
        logging.debug(f"x_0 (private key): {x0.hex()}")

    for i in range(1, chain_length + 1):
        next_point = hash_function(chain[-1]).digest()
        chain.append(next_point)

        if debug and (i <= 5 or i == chain_length):
            logging.debug(f"x_{i}: {next_point.hex()}")

        if chain[i] != hash_function(chain[i - 1]).digest():
            raise RuntimeError(f"Chain generation error at step {i}")

    public_key = chain[-1]

    _safe_write(os.path.join(output_dir, "private_key.bin"), x0)
    _safe_write(os.path.join(output_dir, "winternitz_chain.bin"), b"".join(chain))
    _safe_write(os.path.join(output_dir, "public_key.bin"), public_key)

    logging.info(f"Winternitz chain generated with length={chain_length}.")
    logging.info(f"Public key is the last chain point: {public_key.hex()[:16]}...")

    return chain

def load_chain(chain_file):
    with open(chain_file, "rb") as f:
        chain_data = f.read()
    if len(chain_data) % 32 != 0:
        raise ValueError("Invalid chain length. Data size must be multiple of 32 bytes.")
    return [chain_data[i * 32:(i + 1) * 32] for i in range(len(chain_data) // 32)]

# ---------- Public Key Send ----------
def send_public_key(coord_ip: str, tcp_port: int, client_id: str, output_dir: str, timeout: float = 5.0) -> bool:
    """Read public_key.bin and send 'client_id|<hex>' to the Coordinator on TCP."""
    pk_path = os.path.join(output_dir, "public_key.bin")
    if not os.path.exists(pk_path):
        logging.error("public_key.bin not found; cannot register with Coordinator.")
        return False

    with open(pk_path, "rb") as f:
        pk_hex = binascii.hexlify(f.read()).decode()

    payload = f"{client_id}|{pk_hex}".encode()

    try:
        with socket.create_connection((coord_ip, tcp_port), timeout=timeout) as s:
            s.sendall(payload)
            ack = s.recv(8)
            if ack.strip() == b"ACK":
                logging.info(f"[PK] Public key registered with {coord_ip}:{tcp_port}")
                return True
            logging.error(f"[PK] Unexpected response from {coord_ip}:{tcp_port}: {ack!r}")
            return False
    except Exception as e:
        logging.error(f"[PK] Failed to deliver public key to {coord_ip}:{tcp_port}: {e}")
        return False

# ---------- Heartbeat Sending ----------
def send_heartbeat(sock, server_address, client_id, chain_points, i):
    if i >= len(chain_points):
        logging.error("Chain exhausted. Cannot send more heartbeats.")
        return False

    timestamp = str(time.time()).encode()
    # w_i = H^{N-i}(x0), with chain[-1] being H^N(x0) = public_key
    w_i = chain_points[-(i + 1)]

    payload = client_id.encode() + b"|" + timestamp + b"|" + str(i).encode()
    authenticator = DEFAULT_HASH_FUNCTION(payload + w_i).digest()

    message = payload + b"||" + w_i + b"||" + authenticator

    try:
        sock.sendto(message, server_address)
        logging.info(f"Sent heartbeat {i}/{len(chain_points)-1} - Timestamp={timestamp.decode()}")
    except Exception as e:
        logging.error(f"Failed to send heartbeat {i}: {e}")
        return False

    return True

# ---------- Main ----------
def main():
    parser = argparse.ArgumentParser(description="Standalone Heartbeat client")
    parser.add_argument("--output-dir", default="./heartbeat_keys", help="Directory for key/chain files")
    parser.add_argument("--length", type=int, default=DEFAULT_CHAIN_LENGTH, help="Length of Winternitz chain")
    parser.add_argument("--receiver-ip", required=True, help="Coordinator IP to send heartbeats to")
    parser.add_argument("--receiver-port", type=int, default=5008, help="Coordinator UDP port")
    parser.add_argument("--pubkey-port", type=int, default=5007, help="Coordinator TCP port for public key registration")
    parser.add_argument("--client-id", required=True, help="Unique client ID (UUID)")
    parser.add_argument("--interval", type=float, default=1.0, help="Heartbeat interval in seconds")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    chain_file = os.path.join(args.output_dir, "winternitz_chain.bin")

    # Generate chain if not present
    try:
        if not os.path.exists(chain_file):
            logging.info("No chain file found. Generating a new one...")
            chain_points = generate_winternitz_chain(args.output_dir, chain_length=args.length, debug=args.debug)
        else:
            chain_points = load_chain(chain_file)
            logging.info(f"Loaded Winternitz chain with {len(chain_points)} points from {chain_file}")
    except Exception as e:
        logging.error(f"Chain generation/loading failed: {e}")
        sys.exit(1)

    # Register public key before sending any heartbeat
    if not send_public_key(args.receiver_ip, args.pubkey_port, args.client_id, args.output_dir):
        logging.error("Public key registration failed; aborting heartbeat loop.")
        sys.exit(2)

    server_address = (args.receiver_ip, args.receiver_port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        i = 1
        while RUNNING and i < len(chain_points):
            if not send_heartbeat(sock, server_address, args.client_id, chain_points, i):
                break
            i += 1
            time.sleep(args.interval)

    logging.info("Heartbeat sender stopped. Chain exhausted or process terminated.")

if __name__ == "__main__":
    main()
