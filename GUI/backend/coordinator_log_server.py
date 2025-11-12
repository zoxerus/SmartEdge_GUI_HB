import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websocket_handler import connect_client, disconnect_client, broadcast_to_db_clients
from cassandra_interface import fetch_and_broadcast_data
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from collections import deque
from cassandra.query import dict_factory
from cassandra.cluster import Cluster
from fastapi import Request
import subprocess
import os
import json
from log_parser import parse_log_line
from collections import defaultdict
from lib.logger_utils import get_logger
from fastapi import Body
from fastapi import FastAPI, HTTPException
from cassandra.cluster import Cluster
from cassandra.query import dict_factory
import heartbeat_api
import signal
from fastapi import Body
from cassandra_interface import fetch_and_broadcast_data



# Organized structured log buffers
logs_by_type_and_source = defaultdict(lambda: defaultdict(lambda: deque(maxlen=MAX_LOG_BUFFER_SIZE)))
logger_snapshot = get_logger("Database", "Snapshot")


# === Config ===
TCP_LOG_PORT = 5000
HTTP_PORT = 8000
MAX_LOG_BUFFER_SIZE = 1000

# === State ===
app = FastAPI()
app.include_router(heartbeat_api.router)

log_buffer = deque(maxlen=MAX_LOG_BUFFER_SIZE)

log_buffer_lock = asyncio.Lock()
websocket_lock = asyncio.Lock()

# === Serve Frontend ===
BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Global tracked process (if any)
_HB_PROCESS = None

class WebSocketClient:
    def __init__(self, websocket):
        self.websocket = websocket
        self.filters = {"type": None, "source": None}

def matches_filter(entry, filters):
    if not filters:
        return True
    if filters["type"] and entry.get("type") != filters["type"]:
        return False
    if filters["source"] and entry.get("source") != filters["source"]:
        return False
    return True

active_websocket: WebSocketClient | None = None




@app.post("/trigger-db-update")
async def trigger_db_update(payload: dict = Body(...)):
    """
    Called by Coordinator when a Cassandra table changes.
    Triggers a selective re-fetch and WebSocket broadcast.
    """
    table = payload.get("table")

    if not table:
        return {"status": "error", "detail": "Missing 'table' field"}

    try:
        print(f"[DB Trigger] Received update request for table: {table}")
        await fetch_and_broadcast_data(table)
        return {"status": "ok", "table": table}
    except Exception as e:
        print(f"[DB Trigger] Error handling update for {table}: {e}")
        return {"status": "error", "detail": str(e)}




@app.get("/fetch-db")
async def manual_db_fetch():
    """
    Manually trigger DB fetch and broadcast (from frontend).
    """
    try:
        await fetch_and_broadcast_data()
        return JSONResponse({"status": "ok"})
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)

@app.get("/")
def get_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# === WebSocket for logs ===
@app.websocket("/ws/logs")
async def websocket_log_stream(websocket: WebSocket):
    global active_websocket
    await websocket.accept()
    print("[WebSocket] GUI client connected")

    client = WebSocketClient(websocket)

    async with websocket_lock:
        active_websocket = client

    # Send historical logs matching filter
    async with log_buffer_lock:
        for entry in log_buffer:
            if matches_filter(entry, client.filters):
                await websocket.send_text(json.dumps(entry))

    try:
        while True:
            msg = await websocket.receive_text()
            try:
                parsed = json.loads(msg)
                if isinstance(parsed, dict) and "subscribe" in parsed:
                    client.filters["type"] = parsed["subscribe"].get("type")
                    client.filters["source"] = parsed["subscribe"].get("source")
                    print(f"[WebSocket] Client updated filters: {client.filters}")
            except Exception as e:
                print(f"[WebSocket] Failed to parse message: {e}")
    except WebSocketDisconnect:
        print("[WebSocket] GUI client disconnected")
        async with websocket_lock:
            if active_websocket == client:
                active_websocket = None


@app.websocket("/ws/db")
async def websocket_db_stream(websocket: WebSocket):
    await connect_client(websocket)
    print("[WebSocket] DB GUI client connected")
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        print("[WebSocket] DB GUI client disconnected")
        await disconnect_client(websocket)


@app.get("/art-nodes")
def get_art_nodes():
    try:
        cluster = Cluster(['127.0.0.1'])  # Change if needed
        session = cluster.connect("ks_swarm")
        session.row_factory = dict_factory

        rows = session.execute("SELECT uuid, current_swarm, current_ap, last_update FROM art")
    except Exception as e:
        print("[/art-nodes] Cassandra error:", e)
        return []

    result = []

    for row in rows:
        result.append({
            "uuid": row.get("uuid"),
            "swarm_id": row.get("current_swarm"),
            "current_ap": row.get("current_ap"),
            "last_update": row.get("last_update").isoformat() if row.get("last_update") else None  
        })

    return result


@app.get("/swarms")
def get_swarms():
    try:
        cluster = Cluster(["127.0.0.1"])
        session = cluster.connect("ks_swarm")
        rows = session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'ks_swarm'")
        swarm_tables = [row.table_name for row in rows if row.table_name.startswith("swarm_table")]
    except Exception as e:
        print("[/swarms] Error:", e)
        return []

    return [{"name": f"Swarm {i+1}", "table": table_name} for i, table_name in enumerate(sorted(swarm_tables))]


@app.get("/swarms/{table_name}")
def get_swarm_members(table_name: str):
    try:
        cluster = Cluster(["127.0.0.1"])
        session = cluster.connect("ks_swarm")
        session.row_factory = dict_factory
        rows = session.execute(f"SELECT uuid FROM {table_name}")
        return [row["uuid"] for row in rows]
    except Exception as e:
        print(f"[/swarms/{table_name}] Error:", e)
        return []

@app.get("/fetch-heartbeat-characteristics/{node_uuid}")
def fetch_heartbeat_characteristics(node_uuid: str):
    try:
        cluster = Cluster(["127.0.0.1"])   # adjust host if needed
        session = cluster.connect("swarm")  # your keyspace
        session.row_factory = dict_factory

        # Query node_keys
        row_key = session.execute(
            "SELECT * FROM node_keys WHERE node_uuid = %s", [node_uuid]
        ).one()

        # Query heartbeat_state
        row_state = session.execute(
            "SELECT * FROM heartbeat_state WHERE node_uuid = %s", [node_uuid]
        ).one()

    except Exception as e:
        print("[/fetch-heartbeat-characteristics] Error:", e)
        return {"node_keys": None, "heartbeat_state": None}

    return {
        "node_keys": row_key if row_key else None,
        "heartbeat_state": row_state if row_state else None,
    }


def infer_log_source(line: str) -> str:
    if "Access Point" in line or "AP" in line:
        return "Access Point"
    elif "Coordinator" in line:
        return "Coordinator"
    return "UNKNOWN"


async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    print(f"[TCP] Connection from {addr}")
    try:
        while True:
            data = await reader.readline()
            if not data:
                break

            line = data.decode().strip()
            if not line:  # Skip empty lines
                continue

            print(f"[DEBUG] Raw TCP log received: {repr(line)}")
            
            # Try to parse as structured log
            parsed = parse_log_line(line)
            if parsed:
                await add_log_entry(parsed)
            else:
                # Treat as raw Console log
                await add_log_entry({
                    "type": "Console",
                    "source": "Access Point" if "Access Point" in line else "Coordinator",
                    "message": line
                })

    except Exception as e:
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        print(f"[TCP] Connection closed: {addr}")
        writer.close()
        await writer.wait_closed()


async def add_log_entry(entry: dict):
    print("[DEBUG] Parsed log entry:", entry)
    log_type = entry.get("type", "Console")
    source = entry.get("source", "UNKNOWN").upper()

    # Store in per-source/type buffer
    logs_by_type_and_source[log_type][source].append(entry)

    # Still add to flat buffer for legacy GUI stream
    async with log_buffer_lock:
        log_buffer.append(entry)

    # Send over WebSocket
    await send_log_to_websocket(entry)


async def send_log_to_websocket(entry: dict):
    global active_websocket
    async with websocket_lock:
        if active_websocket:
            try:
                #if matches_filter(entry, active_websocket.filters):
                if entry.get("type") in ["Console", "Metric"]: 
                    raw_source = entry.get("source", "UNKNOWN").upper()

                    # Normalize to frontend-expected values
                    if raw_source == "ACCESS POINT":
                        normalized_source = "AP"
                    elif raw_source == "COORDINATOR":
                        normalized_source = "COORDINATOR"
                    else:
                        normalized_source = raw_source  # Fallback

                    payload = {
                        "type": "log",
                        "log_type": entry.get("type", "Console"),
                        "source": normalized_source,
                        "message": entry.get("message")
                    }

                    print(f"[WebSocket] Sending log to frontend: {payload}")
                    await active_websocket.websocket.send_text(json.dumps(payload))

            except Exception as e:
                print(f"[WebSocket] Error sending log: {e}")
                active_websocket = None


async def send_json_to_websocket(payload: dict):
    global active_websocket
    async with websocket_lock:
        if active_websocket:
            try:
                await active_websocket.send_text(json.dumps(payload))
            except Exception as e:
                print(f"[WebSocket] Error sending JSON payload: {e}")
                active_websocket = None

async def start_tcp_server():
    server = await asyncio.start_server(handle_tcp_client, "0.0.0.0", TCP_LOG_PORT)
    print(f"[TCP] Listening for Coordinator logs on port {TCP_LOG_PORT}...")
    async with server:
        await server.serve_forever()

async def periodic_db_fetch():
    while True:
        await fetch_and_broadcast_data()
        await asyncio.sleep(1)

async def send_db_snapshot():
    while True:
        try:
            cluster = Cluster(["127.0.0.1"])
            session = cluster.connect("ks_swarm")
            session.row_factory = dict_factory

            tables = ["art"] + [
                row["table_name"]
                for row in session.execute("SELECT table_name FROM system_schema.tables WHERE keyspace_name = 'ks_swarm'")
                if row["table_name"].startswith("swarm_table")
            ]

            snapshot = {}

            for table in tables:
                rows = session.execute(f"SELECT * FROM {table}")
                snapshot[table] = [dict(row) for row in rows]

            logger_snapshot.info(json.dumps(snapshot, default=str))

        except Exception as e:
            logger_snapshot.error(f"Failed to fetch DB snapshot: {e}")

        await asyncio.sleep(5)


@app.post("/request-join")
async def request_join(request: Request):
    data = await request.json()
    uuid = data.get("uuid")
    swarm = data.get("swarm")
    heartbeat = data.get("heartbeat", False)

    # New optional parameters
    hb_length = data.get("hb_length")
    hb_window = data.get("hb_window")
    hb_interval = data.get("hb_interval")

    if not uuid:
        return {"success": False, "error": "No UUID provided"}
    if not swarm:
        return {"success": False, "error": "No swarm selected"}

    print(f"[JOIN REQUEST] Node UUID: {uuid}, Target Swarm: {swarm}, Heartbeat: {heartbeat}")

    # --- Validate heartbeat parameters if heartbeat is enabled ---
    args = ["python3", "../../tests/ac_request_nodes_to_join.py", uuid, "--swarm", swarm]

    if heartbeat:
        print(f"[HEARTBEAT PARAMETERS] length={hb_length}, window={hb_window}, interval={hb_interval}")
        args.extend([
            "--heartbeat", "true",
            "--length", str(hb_length),
            "--window", str(hb_window),
            "--interval", str(hb_interval)
        ])
    else:
        args.extend(["--heartbeat", "false"])

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=20  # seconds
        )

        print("[SCRIPT STDOUT]:", result.stdout)
        print("[SCRIPT STDERR]:", result.stderr)
        print("[SCRIPT RETURN CODE]:", result.returncode)

        if result.returncode != 0:
            return {"success": False, "error": result.stderr or "Script failed"}

        return {"success": True, "output": result.stdout.strip()}

    except Exception as e:
        print("[ERROR] Exception while executing join script:", e)
        return {"success": False, "error": str(e)}


@app.post("/stop-heartbeat-server")
async def stop_heartbeat_server():
    """
    Stop the heartbeat_server.py process if running.
    Prefer stopping the tracked process (_HB_PROCESS), but fall back to pkill.
    """
    global _HB_PROCESS
    try:
        # --- Case 1: Stop tracked process (if available) ---
        if _HB_PROCESS and (_HB_PROCESS.poll() is None):
            try:
                os.killpg(os.getpgid(_HB_PROCESS.pid), signal.SIGTERM)
            except Exception:
                # fallback to direct terminate
                _HB_PROCESS.terminate()
            _HB_PROCESS = None
            print("[HB-API] ✅ Heartbeat server stopped (tracked process).")
            return {"success": True, "output": "Heartbeat server stopped successfully."}

        # --- Case 2: Fallback — kill any running process by name ---
        res = subprocess.run(
            ["pkill", "-f", "heartbeat_server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if res.returncode == 0:
            print("[HB-API] ✅ Heartbeat server stopped via pkill fallback.")
            return {"success": True, "output": "Heartbeat server process stopped (fallback)."}
        else:
            print("[HB-API] ⚠️ No heartbeat server process found (already stopped).")
            return {"success": True, "output": "No heartbeat server process found (already stopped)."}

    except Exception as e:
        print(f"[HB-API] ❌ Error stopping heartbeat server: {e}")
        return {"success": False, "error": f"Failed to stop heartbeat server: {e}"}


@app.post("/request-leave")
async def request_leave(request: Request):
    """
    Handle leave requests from GUI.
    Executes the leave script for the provided node UUID(s).
    After successful removal, checks if swarm_table is empty.
    If empty → automatically stops heartbeat_server.py.
    """
    data = await request.json()
    node_ids = data.get("nids")

    if not node_ids or not isinstance(node_ids, list) or not node_ids[0]:
        return {"success": False, "error": "No UUID provided"}

    try:
        # --- Step 1: Run the leave script ---
        args = ["python3", "../../tests/ac_request_nodes_to_leave.py"]
        args.extend(node_ids)

        result = subprocess.run(args, capture_output=True, text=True, timeout=20)

        if result.returncode != 0:
            return {"success": False, "error": result.stderr or "Script failed"}

        # --- Step 2: Wait briefly and check swarm_table count ---
        await asyncio.sleep(1.0)  # allow DB to update
        try:
            session.set_keyspace("ks_swarm")
            row = session.execute("SELECT COUNT(*) AS count FROM swarm_table;").one()
            count = row["count"] if row and "count" in row else 0
            print(f"[HB-API] Swarm count after leave = {count}")
        except Exception as e:
            print(f"[HB-API] ⚠️ Could not check swarm_table count: {e}")
            count = -1

        # --- Step 3: If swarm is empty, stop heartbeat server ---
        if count == 0:
            print("[HB-API] 🟡 Swarm is empty → stopping heartbeat_server.py ...")
            try:
                stop_result = await stop_heartbeat_server()
                msg = stop_result.get("output", "Heartbeat server stopped.") if isinstance(stop_result, dict) else "Heartbeat server stopped."
                return {"success": True, "output": f"{result.stdout.strip()} | {msg}"}
            except Exception as e:
                print(f"[HB-API] ⚠️ Failed to stop heartbeat server automatically: {e}")
                return {"success": True, "output": f"{result.stdout.strip()} | Warning: failed to stop heartbeat server."}

        # --- Step 4: Swarm not empty → normal success ---
        return {"success": True, "output": result.stdout.strip()}

    except Exception as e:
        print(f"[HB-API] ❌ Error in request_leave: {e}")
        return {"success": False, "error": str(e)} 




@app.post("/start/coordinator")
async def start_coordinator():
    try:
        subprocess.Popen(
            "cd /home/Coordinator/smartedge_GUI && source .venv/bin/activate && source run.sh co 10 > coord.log 2>&1 &",
            shell=True,
            executable="/bin/bash"
        )
        return {"message": "Coordinator started"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/stop/coordinator")
async def stop_coordinator():
    try:
        # This kills the python process running coordinator.py
        result = subprocess.run(
            "sudo /usr/bin/pkill -f coordinator.py > stop.log 2>&1 &",
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"error": f"Coordinator not stopped correctly. {result.stderr.strip()}"}
        return {"message": "Coordinator stopped"}
    except Exception as e:
        return {"error": str(e)}



@app.post("/start/ap")
async def start_access_point():
    try:
        result = subprocess.Popen(
            "ssh ap1@10.30.2.151 'cd /home/ap1/smartedge && source .venv/bin/activate && source run.sh ap 10 > ap.log 2>&1 &'",
            shell=True,
            executable="/bin/bash"
        )
        return {"message": "Access Point started"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/stop/ap")
async def stop_ap():
    try:
        subprocess.run(
            "ssh ap1@10.30.2.151 'sudo pkill -f \"python.*ap_manager.py\"'",
            shell=True,
            executable="/bin/bash",
            check=True
        )
        return {"message": "Access Point stopped"}
    except subprocess.CalledProcessError as e:
        return {"error": f"pkill failed: {e.stderr or str(e)}"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/start-heartbeat-server")
async def start_heartbeat_server(data: dict):
    lost_limit = data.get("lost_limit", 3)
    subprocess.Popen(
        ["python3", "../../coordinator/heartbeat_server.py", str(lost_limit)]
    )
    return {"success": True, "output": f"Server started with lost_limit={lost_limit}"}



# === Main startup ===
async def main():
    print("[System] Starting Coordinator Log Server...")
    asyncio.create_task(start_tcp_server())
    # asyncio.create_task(periodic_db_fetch())
    
    asyncio.create_task(fetch_and_broadcast_data())
    asyncio.create_task(send_db_snapshot())

    config = uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Shutdown] Coordinator log server stopped.")
