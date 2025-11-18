#!/usr/bin/env python3


import os
import re
import signal
import asyncio
import subprocess
from collections import deque, defaultdict
from typing import Dict, Set, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from cassandra.cluster import Cluster
from cassandra.query import dict_factory
import aiofiles

router = APIRouter()

# =================================================
# =============== Cassandra Setup =================
# =================================================
cluster = Cluster(["127.0.0.1"])
session = cluster.connect()
session.row_factory = dict_factory

from pathlib import Path

# Absolute path to this script file
SCRIPT_FILE_PATH = Path(__file__).resolve()

# Absolute path to the directory containing this script
SCRIPT_DIR = SCRIPT_FILE_PATH.parent

# =================================================
# =============== Configuration ===================
# =================================================
# IMPORTANT: must match the path used by heartbeat_server.py
LOG_FILE = SCRIPT_DIR / "../../coordinator/logs/coordinator_hb_server.log"

# Path to the heartbeat server script
HB_SCRIPT = SCRIPT_DIR / "../../coordinator/heartbeat_server.py"

# Tail behavior / history size
TAIL_INTERVAL = 1.0   # seconds between file reads
HISTORY_LIMIT = 150   # number of lines to keep per UUID

# Launch logging for the server process (stdout/stderr from launcher, not the server's own log)
LAUNCH_LOG = SCRIPT_DIR / "../../coordinator/logs/hb_launch.log"

# Track the running process we launched (optional; we also have a fallback kill-by-name)
_HB_PROCESS: Optional[subprocess.Popen] = None

# =================================================
# =============== REST ENDPOINTS ==================
# =================================================

@router.get("/api/swarm/members")
def get_swarm_members():
    """Return all swarm members with their current status and identifiers."""
    session.set_keyspace("ks_swarm")
    rows = session.execute("SELECT * FROM swarm_table;")
    members = []
    for r in rows:
        members.append({
            "uuid": r.get("uuid"),
            "status": r.get("status"),
            "swarm": r.get("current_ap"),
            "virt_ip": r.get("virt_ip"),
            "virt_mac": r.get("virt_mac"),
        })
    return members


@router.get("/api/swarm/member/{uuid}")
def get_node_details(uuid: str):
    """
    Return detailed information about a specific node,
    including heartbeat state, public key, and swarm info.
    """
    local_cluster = Cluster(["127.0.0.1"])
    local_session = local_cluster.connect()
    local_session.row_factory = dict_factory

    result = {"uuid": uuid}

    # Heartbeat state
    try:
        local_session.set_keyspace("swarm")
        hb = local_session.execute(
            "SELECT status, last_ts FROM heartbeat_state WHERE node_uuid=%s",
            [uuid]
        ).one()
        if hb:
            result["status"] = hb.get("status", "-")
            ts = hb.get("last_ts")
            result["last_ts"] = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
    except Exception:
        pass

    # Node public key
    try:
        key = local_session.execute(
            "SELECT public_key FROM node_keys WHERE node_uuid=%s", [uuid]
        ).one()
        if key and "public_key" in key:
            pk = key["public_key"]
            if isinstance(pk, (bytes, bytearray)):
                pk = pk.hex()
            result["public_key"] = pk
    except Exception:
        pass

    # Swarm info
    try:
        local_session.set_keyspace("ks_swarm")
        sw = local_session.execute(
            "SELECT current_ap, virt_ip, virt_mac FROM swarm_table WHERE uuid=%s", [uuid]
        ).one()
        if sw:
            result["swarm"] = sw.get("current_ap", "-")
            result["virt_ip"] = sw.get("virt_ip", "-")
            result["virt_mac"] = sw.get("virt_mac", "-")
    except Exception:
        pass

    local_cluster.shutdown()
    return result


@router.get("/api/swarm/swarm_table/is-empty")
def is_swarm_empty():
    """
    Check if the single swarm_table is empty.
    True → empty, False → has members.
    """
    try:
        session.set_keyspace("ks_swarm")
        row = session.execute("SELECT COUNT(*) AS count FROM swarm_table;").one()
        count = row["count"] if row and "count" in row else 0
        return {"empty": count == 0}
    except Exception as e:
        print(f"[HB-API] ❌ Error checking swarm emptiness: {e}")
        # Fail-safe: assume empty to allow initialization
        return {"empty": True, "error": str(e)}




@router.get("/api/heartbeat-server/status")
def heartbeat_server_status():
    """
    Returns whether a heartbeat server process appears to be running.
    This checks the tracked process if we launched it, otherwise does a simple
    `pgrep -f` fallback to detect presence.
    """
    global _HB_PROCESS
    running = False
    try:
        if _HB_PROCESS and (_HB_PROCESS.poll() is None):
            running = True
        else:
            # fallback: check if any heartbeat_server.py process exists
            rc = os.system("pgrep -f 'heartbeat_server.py' > /dev/null 2>&1")
            running = (rc == 0)
    except Exception:
        running = False
    return {"running": running}


@router.post("/start-heartbeat-server")
async def start_heartbeat_server(data: dict):
    """
    Start the heartbeat server with a given lost_limit (int).
    If already running, we keep it running (idempotent).
    """
    global _HB_PROCESS

    # Validate input
    try:
        lost_limit = int(data.get("lost_limit", 5))
        if not (1 <= lost_limit <= 10):
            return {"success": False, "error": "lost_limit must be between 1 and 10"}
    except Exception:
        return {"success": False, "error": "Invalid lost_limit"}

    # Ensure log directory exists
    os.makedirs(os.path.dirname(LAUNCH_LOG), exist_ok=True)

    # Check if we have a tracked process
    if _HB_PROCESS and (_HB_PROCESS.poll() is None):
        return {"success": True, "output": "Heartbeat server already running (tracked)."}

    # Check externally if a heartbeat_server is running (reliable way)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "heartbeat_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            print(f"[HB-API] Detected running heartbeat_server.py (PID={result.stdout.strip()})")
            return {"success": True, "output": "Heartbeat server already running (detected)."}
    except Exception as e:
        print(f"[HB-API] Warning: pgrep check failed: {e}")

    # Start new process
    try:
        with open(LAUNCH_LOG, "a") as lf:
            _HB_PROCESS = subprocess.Popen(
                ["nohup", "python3", HB_SCRIPT, str(lost_limit)],
                stdout=lf,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setpgrp
            )
        print(f"[HB-API] ✅ Started heartbeat_server.py (PID={_HB_PROCESS.pid}, limit={lost_limit})")
        return {"success": True, "output": f"Started heartbeat server (limit={lost_limit})"}
    except Exception as e:
        _HB_PROCESS = None
        print(f"[HB-API] ❌ Failed to start heartbeat_server.py: {e}")
        return {"success": False, "error": f"Failed to start heartbeat server: {e}"}



@router.post("/stop-heartbeat-server")
async def stop_heartbeat_server():
    """
    Stop the heartbeat server process if running. We prefer stopping the tracked
    process, but also provide a fallback `pkill -f` in case it was started outside.
    """
    global _HB_PROCESS
    try:
        # Stop tracked process if available
        if _HB_PROCESS and (_HB_PROCESS.poll() is None):
            try:
                os.killpg(os.getpgid(_HB_PROCESS.pid), signal.SIGTERM)
            except Exception:
                # try direct kill if group kill fails
                _HB_PROCESS.terminate()
            _HB_PROCESS = None
            return {"success": True, "output": "Heartbeat server stopped successfully."}

        # Fallback: kill any matching process
        os.system("pkill -f 'heartbeat_server.py' > /dev/null 2>&1")
        return {"success": True, "output": "Heartbeat server process stopped (fallback)."}
    except Exception as e:
        return {"success": False, "error": f"Failed to stop heartbeat server: {e}"}


# =================================================
# ============== WEBSOCKET LOG STREAM =============
# =================================================

# Map of node UUID -> set of active websocket connections
_ws_by_uuid: Dict[str, Set[WebSocket]] = defaultdict(set)

# In-memory history buffer per UUID
_history_by_uuid: Dict[str, deque] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))

# Regex matcher for heartbeat log UUIDs (robust to formats like "client=SN010003" or "node: SN010003")
_UUID_RE = re.compile(r"(?:\b(?:client|node)\b\s*[:=]\s*)?(SN\d{6})", re.IGNORECASE)

# Background tail task (one shared across all WS clients)
_tail_task: Optional[asyncio.Task] = None


async def _dispatch_to_subscribers(node_uuid: str, line: str):
    """
    Send one log line to all active WebSocket subscribers of `node_uuid`.
    """
    node_uuid = node_uuid.upper()
    conns = _ws_by_uuid.get(node_uuid)
    if not conns:
        return

    dead: Set[WebSocket] = set()
    for ws in list(conns):
        try:
            await ws.send_text(line)
        except Exception:
            dead.add(ws)

    for ws in dead:
        conns.discard(ws)
    if dead:
        print(f"[HB-API] Pruned {len(dead)} WS for {node_uuid}; {len(conns)} remain")


async def _tail_heartbeat_log():
    """
    Continuously read the heartbeat_server log file and stream lines
    to WebSocket clients filtered by UUID.
    If the log file doesn't exist yet, waits until it appears.
    """
    print(f"[HB-API] Log tail started: {LOG_FILE}")

    # Wait for log file to exist
    while not os.path.exists(LOG_FILE):
        print(f"[HB-API] Waiting for log file {LOG_FILE} ...")
        await asyncio.sleep(2)

    # Tail from end
    async with aiofiles.open(LOG_FILE, mode="r") as f:
        await f.seek(0, os.SEEK_END)
        while True:
            line = await f.readline()
            if not line:
                await asyncio.sleep(TAIL_INTERVAL)
                continue

            msg = line.strip()
            if not msg:
                continue

            # Extract node UUID (if any)
            m = _UUID_RE.search(msg)
            if not m:
                continue

            node_uuid = m.group(1).upper()

            # Save to short history buffer
            _history_by_uuid[node_uuid].append(msg)

            # Dispatch to connected clients
            await _dispatch_to_subscribers(node_uuid, msg)


@router.websocket("/ws/heartbeat_logs/{uuid}")
async def websocket_endpoint(ws: WebSocket, uuid: str):
    """
    WebSocket endpoint:
      - Subscribes to log updates for a given node UUID.
      - Replays recent logs for that node (if any).
      - Keeps connection alive and streams new lines.
    """
    uuid = uuid.upper()
    await ws.accept()
    _ws_by_uuid[uuid].add(ws)
    print(f"[HB-API] WS connected -> {uuid} | total={len(_ws_by_uuid[uuid])}")

    # Start the shared log-tail task (if not already running)
    global _tail_task
    if _tail_task is None or _tail_task.done():
        _tail_task = asyncio.create_task(_tail_heartbeat_log())

    # Replay cached history to new client
    try:
        history = list(_history_by_uuid[uuid])
        if history:
            print(f"[HB-API] Replaying {len(history)} lines to {uuid}")
        for line in history:
            await ws.send_text(line)
    except Exception:
        _ws_by_uuid[uuid].discard(ws)
        if not _ws_by_uuid[uuid]:
            _ws_by_uuid.pop(uuid, None)
        print(f"[HB-API] WS dropped during replay -> {uuid}")
        return

    async def _keepalive():
        """Send lightweight pings periodically to keep WS alive."""
        try:
            while True:
                await asyncio.sleep(25)
                await ws.send_text("")  # ping
        except Exception:
            pass

    ka_task = asyncio.create_task(_keepalive())

    try:
        # Keep connection alive
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        ka_task.cancel()
        _ws_by_uuid[uuid].discard(ws)
        if not _ws_by_uuid[uuid]:
            _ws_by_uuid.pop(uuid, None)
        print(f"[HB-API] WS disconnected -> {uuid}")

