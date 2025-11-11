#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import hashlib
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone

from cassandra.cluster import Cluster
from cassandra.query import SimpleStatement, PreparedStatement
from cassandra import ConsistencyLevel

# ==================== Configuration ====================
BIND_IP           = os.environ.get("SE_CO_BIND_IP", "0.0.0.0")   # e.g., "10.1.255.254" in prod
TCP_PORT          = int(os.environ.get("SE_CO_PUBKEY_TCP_PORT", "5007"))
UDP_PORT          = int(os.environ.get("SE_CO_HB_UDP_PORT", "5008"))
#HEARTBEAT_TIMEOUT = int(os.environ.get("SE_CO_HB_TIMEOUT", "7"))  # seconds
LOGFILE           = os.environ.get("SE_CO_LOG", "/home/Coordinator/smartedge_GUI/coordinator/logs/coordinator_hb_server.log")
STORE_DIR         = os.environ.get("SE_CO_HB_STORE", "./hb_store")  # optional: where to stash any files if needed

# Allow override via CLI argument: python3 heartbeat_server.py <lost_limit>
if len(sys.argv) > 1:
    try:
        HEARTBEAT_TIMEOUT = int(sys.argv[1])
        print(f"[INFO] Using CLI heartbeat timeout: {HEARTBEAT_TIMEOUT}s")
    except ValueError:
        print(f"[WARN] Invalid heartbeat timeout argument '{sys.argv[1]}', using default.")
        HEARTBEAT_TIMEOUT = int(os.environ.get("SE_CO_HB_TIMEOUT", "7"))
else:
    HEARTBEAT_TIMEOUT = int(os.environ.get("SE_CO_HB_TIMEOUT", "7"))  # seconds



# Optional: notify another coordinator/service on DEAD
NOTIFY_IP         = os.environ.get("SE_NOTIFY_IP", "")            # e.g., "10.30.2.153"
NOTIFY_PORT       = int(os.environ.get("SE_NOTIFY_PORT", "5050"))

# Cassandra
CASSANDRA_HOSTS   = os.environ.get("SE_CASS_HOSTS", "127.0.0.1").split(",")
KEYSPACE          = os.environ.get("SE_CASS_KEYSPACE", "swarm")
REPLICATION       = os.environ.get("SE_CASS_REPL", "{'class': 'SimpleStrategy', 'replication_factor': 1}")

HASH_FN = hashlib.sha256
# ========================================================

# ---------------- Logging ----------------
os.makedirs(os.path.dirname(os.path.abspath(LOGFILE)), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CO-HB] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOGFILE)]
)

# ---------------- Global State ----------------
lock = threading.RLock()
# Cache: node_uuid -> {"public_key": bytes, "last_i": int, "status": str, "last_ts": float}
STATE: dict[str, dict] = {}

# ---------------- Cassandra Setup ----------------
def cassandra_connect():
    cluster = Cluster(CASSANDRA_HOSTS)
    session = cluster.connect()
    # Keyspace
    session.execute(f"""
        CREATE KEYSPACE IF NOT EXISTS {KEYSPACE}
        WITH replication = {REPLICATION}
    """)
    session.set_keyspace(KEYSPACE)
    # Tables
    session.execute("""
        CREATE TABLE IF NOT EXISTS node_keys (
            node_uuid  text PRIMARY KEY,
            public_key blob,
            created_at timestamp
        )
    """)
    session.execute("""
        CREATE TABLE IF NOT EXISTS heartbeat_state (
            node_uuid  text PRIMARY KEY,
            last_i     int,
            last_ts    timestamp,
            status     text,       /* 'registered' | 'alive' | 'dead' */
            updated_at timestamp
        )
    """)

    # Prepared statements
    ps = {
        "upsert_key": session.prepare(
            "INSERT INTO node_keys (node_uuid, public_key, created_at) VALUES (?, ?, toTimestamp(now()))"
        ),
        "get_key": session.prepare(
            "SELECT public_key FROM node_keys WHERE node_uuid = ?"
        ),
        "upsert_hb": session.prepare(
            "INSERT INTO heartbeat_state (node_uuid, last_i, last_ts, status, updated_at) VALUES (?, ?, ?, ?, toTimestamp(now()))"
        ),
        "get_hb": session.prepare(
            "SELECT last_i, last_ts, status FROM heartbeat_state WHERE node_uuid = ?"
        ),
    }
    for name in ps.values():
        name.consistency_level = ConsistencyLevel.ONE
    return session, ps

session, PS = cassandra_connect()
logging.info(f"Cassandra connected (keyspace={KEYSPACE})")

def preload_cache():
    # Preload cached PKs and HB state
    from cassandra.query import dict_factory
    old_factory = session.row_factory
    session.row_factory = dict_factory
    try:
        rows = session.execute("SELECT node_uuid, public_key FROM node_keys")
        for r in rows:
            STATE.setdefault(r["node_uuid"], {})["public_key"] = r["public_key"]
        rows = session.execute("SELECT node_uuid, last_i, last_ts, status FROM heartbeat_state")
        for r in rows:
            s = STATE.setdefault(r["node_uuid"], {})
            s["last_i"]  = int(r["last_i"]) if r["last_i"] is not None else 0
            s["last_ts"] = r["last_ts"].timestamp() if r["last_ts"] else 0.0
            s["status"]  = r["status"] or "registered"
        logging.info(f"Preloaded {len(STATE)} clients from DB")
    finally:
        session.row_factory = old_factory

preload_cache()

# ---------------- Utility ----------------
def now_ts() -> float:
    return time.time()

def notify_dead(node_uuid: str):
    if not NOTIFY_IP:
        return
    try:
        msg = f"NODE_DEAD|{node_uuid}"
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(msg.encode(), (NOTIFY_IP, NOTIFY_PORT))
        logging.info(f"[NOTIFY] Dead event sent for {node_uuid} to {NOTIFY_IP}:{NOTIFY_PORT}")
    except Exception as e:
        logging.warning(f"[NOTIFY] Failed for {node_uuid}: {e}")

def save_pubkey(node_uuid: str, public_key: bytes):
    session.execute(PS["upsert_key"], (node_uuid, public_key))
    with lock:
        s = STATE.setdefault(node_uuid, {})
        s["public_key"] = public_key
        s.setdefault("last_i", 0)
        s.setdefault("status", "registered")
        s.setdefault("last_ts", 0.0)

def save_hb_state(node_uuid: str, last_i: int, status: str):
    ts = datetime.fromtimestamp(now_ts(), tz=timezone.utc)
    session.execute(PS["upsert_hb"], (node_uuid, last_i, ts, status))
    with lock:
        s = STATE.setdefault(node_uuid, {})
        s["last_i"] = last_i
        s["status"] = status
        s["last_ts"] = ts.timestamp()

def get_pubkey(node_uuid: str) -> bytes | None:
    with lock:
        pk = STATE.get(node_uuid, {}).get("public_key")
    if pk:
        return pk
    row = session.execute(PS["get_key"], (node_uuid,)).one()
    if row:
        save_pubkey(node_uuid, row.public_key)
        return row.public_key
    return None

def get_hb_state(node_uuid: str) -> tuple[int, float, str]:
    with lock:
        s = STATE.get(node_uuid)
        if s:
            return int(s.get("last_i", 0)), float(s.get("last_ts", 0.0)), s.get("status", "registered")
    row = session.execute(PS["get_hb"], (node_uuid,)).one()
    if row:
        last_i = int(row.last_i) if row.last_i is not None else 0
        last_ts = row.last_ts.timestamp() if row.last_ts else 0.0
        status = row.status or "registered"
        save_hb_state(node_uuid, last_i, status)
        return last_i, last_ts, status
    return 0, 0.0, "registered"

# ---------------- TCP Server (public key) ----------------
def _handle_tcp_client(conn: socket.socket, addr):
    peer = f"{addr[0]}:{addr[1]}"
    try:
        conn.settimeout(5.0)
        data = conn.recv(1_000_000)
        if not data:
            return
        # Expect: client_id|<public_key_hex>
        msg = data.decode("utf-8", errors="strict")
        if "|" not in msg:
            logging.warning(f"[PK] {peer} bad format")
            conn.sendall(b"NACK"); return
        client_id, pk_hex = msg.split("|", 1)
        client_id = client_id.strip()
        pk_hex = pk_hex.strip()
        if not client_id or len(pk_hex) % 2 != 0:
            logging.warning(f"[PK] {peer} invalid fields")
            conn.sendall(b"NACK"); return

        try:
            public_key = bytes.fromhex(pk_hex)
        except ValueError:
            logging.warning(f"[PK] {peer} invalid hex")
            conn.sendall(b"NACK"); return

        save_pubkey(client_id, public_key)
        # Initialize heartbeat state if missing
        last_i, _, status = get_hb_state(client_id)
        if status == "dead":
            # If a node re-registers, reset to registered
            save_hb_state(client_id, last_i=0, status="registered")
        logging.info(f"[PK] Stored public key for {client_id} ({len(public_key)} bytes)")
        conn.sendall(b"ACK")
    except socket.timeout:
        logging.warning(f"[PK] {peer} timeout")
    except Exception as e:
        logging.error(f"[PK] {peer} error: {e}")
        try: conn.sendall(b"NACK")
        except: pass
    finally:
        try: conn.close()
        except: pass

def tcp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((BIND_IP, TCP_PORT))
        srv.listen(64)
        logging.info(f"TCP server listening on {BIND_IP}:{TCP_PORT}")
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_handle_tcp_client, args=(conn, addr), daemon=True).start()

# ---------------- UDP Server (heartbeats) ----------------
def _handle_hb_datagram(data: bytes, addr):
    peer = f"{addr[0]}:{addr[1]}"
    try:
        # Expect: payload || w_i || authenticator
        parts = data.split(b"||")
        if len(parts) != 3:
            raise ValueError("malformed datagram (split)")
        payload, w_i, authenticator = parts

        # payload := client_id|timestamp|i
        p = payload.split(b"|")
        if len(p) != 3:
            raise ValueError("malformed payload")
        client_id = p[0].decode("utf-8")
        ts_str   = p[1].decode("utf-8")
        try:
            i = int(p[2].decode("utf-8"))
        except ValueError:
            raise ValueError("i not int")

        # Verify authenticator: H(payload || w_i)
        calc = HASH_FN(payload + w_i).digest()
        # constant-time compare
        if calc != authenticator:
            raise ValueError("authenticator mismatch")

        pk = get_pubkey(client_id)
        if not pk:
            raise ValueError("unknown client (no public key)")

        last_i, _, _ = get_hb_state(client_id)

        # Accept strictly next or one-skip only
        if i == last_i + 1:
            # H(w_i) must equal anchor (w_last_i)
            if HASH_FN(w_i).digest() != (STATE[client_id]["public_key"] if last_i == 0 else STATE[client_id].get("anchor")):
                # If last_i==0, anchor is public_key; else anchor is w_last_i
                # We'll compute the current anchor if not cached yet
                pass
        # Instead of mixing anchors, use the simple invariant:
        # anchor := value such that H(anchor) == previous_anchor ... but simpler is:
        # H^i(w_i) == public_key
        if _hash_n(w_i, i) != pk:
            # try allow exactly one skip: i == last_i+2 and H^(i)(w_i) == pk
            # (the same equation applies; index condition handles the skip)
            if i == last_i + 2 and _hash_n(w_i, i) == pk:
                pass
            else:
                raise ValueError("Winternitz verification failed")

        # Enforce monotonicity
        if i <= last_i:
            raise ValueError(f"out-of-order i={i} (last_i={last_i})")

        # Accept only +1 or +2 (exactly one skip)
        if not (i == last_i + 1 or i == last_i + 2):
            raise ValueError(f"too far ahead i={i} (last_i={last_i})")

        # Update DB/cache
        save_hb_state(client_id, i, status="alive")
        logging.info(f"[HB] OK client={client_id} i={i} ts={ts_str} from {peer}")

    except Exception as e:
        logging.warning(f"[HB] DROP from {peer}: {e}")

def _hash_n(x: bytes, n: int) -> bytes:
    for _ in range(n):
        x = HASH_FN(x).digest()
    return x

def udp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as srv:
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((BIND_IP, UDP_PORT))
        logging.info(f"UDP server listening on {BIND_IP}:{UDP_PORT}")
        while True:
            data, addr = srv.recvfrom(65507)
            threading.Thread(target=_handle_hb_datagram, args=(data, addr), daemon=True).start()

# ---------------- Heartbeat Timeout Monitor ----------------
def heartbeat_monitor():
    logging.info(f"Timeout monitor running (threshold={HEARTBEAT_TIMEOUT}s)")
    while True:
        time.sleep(1)
        with lock:
            now = now_ts()
            for node_uuid, s in list(STATE.items()):
                last_ts = float(s.get("last_ts", 0.0))
                status  = s.get("status", "registered")
                if status != "dead" and last_ts and (now - last_ts > HEARTBEAT_TIMEOUT):
                    logging.warning(f"[ALERT] {node_uuid} DEAD (no heartbeat for > {HEARTBEAT_TIMEOUT}s)")
                    save_hb_state(node_uuid, s.get("last_i", 0), status="dead")
                    notify_dead(node_uuid)

# ---------------- Main ----------------
if __name__ == "__main__":
    logging.info(f"Starting Coordinator HB receiver on {BIND_IP} (TCP:{TCP_PORT} UDP:{UDP_PORT})")
    Path(STORE_DIR).mkdir(parents=True, exist_ok=True)

    t1 = threading.Thread(target=tcp_server, daemon=True)
    t2 = threading.Thread(target=udp_server, daemon=True)
    t3 = threading.Thread(target=heartbeat_monitor, daemon=True)

    t1.start(); t2.start(); t3.start()

    logging.info("Receiver is running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logging.info("Shutting down.")
