#!/usr/bin/env python3
import os
import sys
import time
import json
import signal
import socket
import binascii
import hashlib
import tempfile
import logging
import multiprocessing
from pathlib import Path

# ---------- Config ----------
STATE_FILE      = os.environ.get("SE_SWARM_STATE", str(Path(__file__).parent / "swarm_status.json"))
KEYS_DIR        = os.environ.get("SE_HB_KEYS_DIR", str(Path(__file__).parent / "heartbeat_keys"))
LOG_FILE        = os.environ.get("SE_HB_MONITOR_LOG", "./heartbeat_monitor.log")
DEFAULT_PK_TCP  = 5007
DEFAULT_HB_UDP  = 5008
DEFAULT_INT     = 1.0
DEFAULT_COORD_IP = os.environ.get("SE_COORDINATOR_SWARM_IP", "10.1.255.254")
CHAIN_LENGTH    = 100
HASH_FUNCTION   = hashlib.sha256
# -------------------------------------------------------------

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(KEYS_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [HB-MONITOR] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE)]
)

HB_PROC = None
RUNNING_FOR = None   # tuple(client_id, coord_ip)
RUNNING = True

PRIVATE_KEY = os.path.join(KEYS_DIR, "private_key.bin")
PUBLIC_KEY  = os.path.join(KEYS_DIR, "public_key.bin")
CHAIN_FILE  = os.path.join(KEYS_DIR, "winternitz_chain.bin")

# ---------- Helpers ----------
def derive_coordinator_ip(ap_swarm_ip: str) -> str:
    """Derive Coordinator IP from AP swarm IP (10.0.x.y -> 10.1.x.y)."""
    try:
        parts = ap_swarm_ip.split(".")
        if parts[0] == "10" and parts[1] == "0":
            parts[1] = "1"
            coord_ip = ".".join(parts)
            logging.info(f"Derived Coordinator IP {coord_ip} from AP IP {ap_swarm_ip}")
            return coord_ip
        else:
            logging.warning(f"AP IP {ap_swarm_ip} not in expected 10.0.*.* range; using fallback {DEFAULT_COORD_IP}")
            return DEFAULT_COORD_IP
    except Exception as e:
        logging.error(f"Failed to derive Coordinator IP from {ap_swarm_ip}: {e}; using fallback {DEFAULT_COORD_IP}")
        return DEFAULT_COORD_IP

def read_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"joined": False}
    except Exception as e:
        logging.warning(f"Failed to read state file: {e}")
        return {"joined": False}

# ---------- Winternitz Chain ----------
def _safe_write(path, data):
    dirpath = os.path.dirname(path)
    os.makedirs(dirpath, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=dirpath, delete=False) as tmp:
        tmp.write(data)
        tempname = tmp.name
    os.replace(tempname, path)

def generate_winternitz_chain(output_dir, chain_length=CHAIN_LENGTH, hash_function=HASH_FUNCTION, debug=False):
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
def send_public_key(coord_ip, tcp_port, client_id, timeout=5):
    logging.info(f"Sending public key to Coordinator {coord_ip}:{tcp_port} for client_id={client_id}...")
    if not os.path.exists(PUBLIC_KEY):
        logging.error("public_key.bin not found.")
        return False
    with open(PUBLIC_KEY, "rb") as f:
        pk_hex = binascii.hexlify(f.read()).decode()
    payload = f"{client_id}|{pk_hex}".encode()

    try:
        with socket.create_connection((coord_ip, tcp_port), timeout=timeout) as s:
            s.sendall(payload)
            ack = s.recv(8)
            if ack.strip() == b"ACK":
                logging.info("ACK received from Coordinator.")
                return True
            logging.error(f"Unexpected ACK response: {ack!r}")
            return False
    except Exception as e:
        logging.error(f"Failed to deliver public key: {e}")
        return False

# ---------- Heartbeat Sender ----------
def send_heartbeat(sock, server_address, client_id, chain_points, i):
    if i >= len(chain_points):
        logging.error("Chain exhausted. Cannot send more heartbeats.")
        return False

    timestamp = str(time.time()).encode()
    w_i = chain_points[-(i + 1)]
    payload = client_id.encode() + b"|" + timestamp + b"|" + str(i).encode()
    authenticator = HASH_FUNCTION(payload + w_i).digest()
    message = payload + b"||" + w_i + b"||" + authenticator

    try:
        sock.sendto(message, server_address)
        logging.info(f"Sent heartbeat {i}/{len(chain_points)-1} - Timestamp={timestamp.decode()}")
    except Exception as e:
        logging.error(f"Failed to send heartbeat {i}: {e}")
        return False

    return True

def send_heartbeat_loop(coord_ip, udp_port, client_id, interval, chain_file):
    try:
        chain_points = load_chain(chain_file)
        logging.info(f"Loaded Winternitz chain with {len(chain_points)} points.")
    except FileNotFoundError:
        logging.info("No chain found, generating new one...")
        generate_winternitz_chain(os.path.dirname(chain_file))
        chain_points = load_chain(chain_file)

    server_address = (coord_ip, udp_port)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        i = 1
        while RUNNING and i < len(chain_points):
            if not send_heartbeat(sock, server_address, client_id, chain_points, i):
                break
            i += 1
            time.sleep(interval)

    logging.info("Heartbeat sender stopped. Chain exhausted or terminated.")

# ---------- Control ----------
def stop_heartbeat():
    global HB_PROC
    if HB_PROC and HB_PROC.is_alive():
        logging.info("Stopping heartbeat sender...")
        HB_PROC.terminate()
        HB_PROC.join(timeout=3)
    HB_PROC = None

def cleanup_keys():
    logging.info("Deleting heartbeat key/chain files...")
    for p in (PRIVATE_KEY, PUBLIC_KEY, CHAIN_FILE):
        try: os.remove(p)
        except FileNotFoundError: pass

def handle_leave():
    stop_heartbeat()
    cleanup_keys()
    global RUNNING_FOR
    RUNNING_FOR = None

def sigterm(_sig, _frm):
    global RUNNING
    logging.info("Received termination signal, cleaning up.")
    RUNNING = False
    handle_leave()
    sys.exit(0)

signal.signal(signal.SIGINT,  sigterm)
signal.signal(signal.SIGTERM, sigterm)

# ---------- Main Loop ----------
def loop():
    global HB_PROC, RUNNING_FOR
    backoff = 1
    while True:
        state = read_state()
        joined = bool(state.get("joined"))
        if not joined:
            if HB_PROC or RUNNING_FOR:
                logging.info("State says not joined; stopping heartbeat.")
                handle_leave()
            time.sleep(1.5)
            continue

        client_id   = state.get("client_id", "CLIENT_ID_PLACEHOLDER")
        ap_ip       = state.get("ap_swarm_ip")
        tcp_port    = int(state.get("pubkey_tcp_port", DEFAULT_PK_TCP))
        udp_port    = int(state.get("hb_udp_port", DEFAULT_HB_UDP))
        interval    = float(state.get("hb_interval", DEFAULT_INT))

        if not ap_ip:
            logging.warning("Joined but no ap_swarm_ip provided; waiting...")
            time.sleep(1.5)
            continue

        coord_ip = derive_coordinator_ip(ap_ip)
        target = (client_id, coord_ip, udp_port, interval)

        if RUNNING_FOR and target != RUNNING_FOR:
            logging.info("Join target changed; restarting heartbeat.")
            handle_leave()

        if HB_PROC is None or not HB_PROC.is_alive():
            logging.info("Preparing heartbeat process...")

            try:
                generate_winternitz_chain(KEYS_DIR)
            except Exception as e:
                logging.error(f"Chain generation failed: {e}")
                time.sleep(min(backoff, 15))
                backoff = min(backoff * 2, 15)
                continue

            if not send_public_key(coord_ip, tcp_port, client_id):
                time.sleep(min(backoff, 15))
                backoff = min(backoff * 2, 15)
                continue

            HB_PROC = multiprocessing.Process(
                target=send_heartbeat_loop,
                args=(coord_ip, udp_port, client_id, interval, CHAIN_FILE)
            )
            HB_PROC.start()
            RUNNING_FOR = target
            backoff = 1

        time.sleep(1.5)

if __name__ == "__main__":
    logging.info("Heartbeat monitor started.")
    loop()
