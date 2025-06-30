# coordinator_log_server.py

import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from websocket_handler import connect_client, disconnect_client
from cassandra_interface import fetch_and_broadcast_data
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from collections import deque
from cassandra.query import dict_factory
#from lib.database_comms import get_session
from cassandra.cluster import Cluster
#from datetime import datetime, timedelta
import os
import json

# === Config ===
TCP_LOG_PORT = 5000
HTTP_PORT = 8000
MAX_LOG_BUFFER_SIZE = 1000

# === State ===
app = FastAPI()
log_buffer = deque(maxlen=MAX_LOG_BUFFER_SIZE)
active_websocket = None
log_buffer_lock = asyncio.Lock()
websocket_lock = asyncio.Lock()

# === Serve Frontend ===
BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

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

    async with websocket_lock:
        active_websocket = websocket

    async with log_buffer_lock:
        for entry in log_buffer:
            try:
                json_payload = json.dumps({
                    "type": "log",
                    "source": entry["source"],
                    "message": entry["message"]
                })
                await websocket.send_text(json_payload)
            except Exception as e:
                print(f"[WebSocket] Error sending buffered log: {e}")
                break

    #async with websocket_lock:
        #active_websocket = websocket
    try:
        while True:
            await websocket.receive_text()  # Keep alive
    except WebSocketDisconnect:
        print("[WebSocket] GUI client disconnected")
        async with websocket_lock:
            if active_websocket == websocket:
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
        disconnect_client(websocket)

# @app.get("/art-nodes")
# def get_art_nodes():
#     try:
#         rows = db.DATABASE_SESSION.execute("SELECT uuid, current_ap FROM ks_swarm.art;")
#         return [
#             {
#                 "uuid": row.uuid,
#                 "swarm_id": row.current_ap,
#                 "status": "online"  # or logic to detect actual status
#             }
#             for row in rows
#         ]
#     except Exception as e:
#         print("❌ /art-nodes ERROR:", str(e))
#         return {"error": str(e)}

@app.get("/art-nodes")
def get_art_nodes():
    try:
        cluster = Cluster(['127.0.0.1'])  # Change if needed
        session = cluster.connect("ks_swarm")
        session.row_factory = dict_factory

        rows = session.execute("SELECT uuid, current_ap FROM art")
    except Exception as e:
        print("[/art-nodes] Cassandra error:", e)
        return []

    result = []

    for row in rows:
        result.append({
            "uuid": row.get("uuid"),
            "swarm_id": row.get("current_ap")  # use 'current_ap' to match your DB
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

# === TCP log receiver ===
# async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
#     addr = writer.get_extra_info("peername")
#     print(f"[TCP] Connection from {addr}")
#     try:
#         while True:
#             data = await reader.readline()
#             if not data:
#                 break
#             log_line = data.decode().strip()
#             print(f"[TCP] Log: {log_line}")
#             await add_log(log_line)
#     except Exception as e:
#         print(f"[TCP] Error with {addr}: {e}")
#     finally:
#         print(f"[TCP] Connection closed: {addr}")
#         writer.close()
#         await writer.wait_closed()

async def handle_tcp_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    addr = writer.get_extra_info("peername")
    print(f"[TCP] Connection from {addr}")
    try:
        buffer = ""
        while True:
            data = await reader.readline()
            if not data:
                if buffer:
                    await add_log(buffer.strip())
                break

            line = data.decode().strip()
            print(f"[DEBUG] Raw TCP log received: {repr(line)}")

            # If this line looks like a new log entry (starts with APxxxxxx or COxxxxxx timestamp ...)
            if line.startswith("AP") or line.startswith("CO"):
                if buffer:
                    await add_log(buffer.strip())  # flush previous
                buffer = line
            else:
                # continuation of previous log (likely the message)
                buffer += "\n" + line
    except Exception as e:
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        print(f"[TCP] Connection closed: {addr}")
        writer.close()
        await writer.wait_closed()


async def add_log(log_line: str):
    if log_line.startswith("AP"):
        source = "AP"
    elif log_line.startswith("CO"):
        source = "COORDINATOR"
    else:
        source = "UNKNOWN"

    entry = {
        "source": source,
        "message": log_line
    }

    async with log_buffer_lock:
        log_buffer.append(entry)

    await send_log_to_websocket(log_line)



# async def add_log(log_line: str):
#     async with log_buffer_lock:
#         log_buffer.append(log_line)
#     await send_log_to_websocket(log_line)

# async def send_log_to_websocket(log_message: str):
#     """Sends a log message to the connected GUI client if available."""
#     global active_websocket
#     async with websocket_lock:
#         if active_websocket:
#             try:
#                 json_payload = json.dumps({
#                     "type": "log",
#                     "source": "COORDINATOR",
#                     "message": log_message
#                 })
#                 await active_websocket.send_text(json_payload)
#             except Exception as e:
#                 print(f"[WebSocket] Error sending log: {e}")
#                 active_websocket = None

# async def send_log_to_websocket(log_message: str):
#     global active_websocket
#     async with websocket_lock:
#         if active_websocket:
#             try:
#                 if log_message.startswith("[AP]"):
#                     source = "AP"
#                     stripped_message = log_message[4:].strip()
#                 else:
#                     source = "COORDINATOR"
#                     stripped_message = log_message.strip()

#                 json_payload = json.dumps({
#                     "type": "log",
#                     "source": source,
#                     "message": stripped_message
#                 })
#                 await active_websocket.send_text(json_payload)
#             except Exception as e:
#                 print(f"[WebSocket] Error sending log: {e}")
#                 active_websocket = None

async def send_log_to_websocket(log_message: str):
    """Sends a log message to the connected GUI client if available."""
    global active_websocket
    async with websocket_lock:
        if active_websocket:
            try:
                # Tag source based on log content
                if log_message.startswith("AP"):
                    source = "AP"
                elif log_message.startswith("CO"):
                    source = "COORDINATOR"
                else:
                    source = "UNKNOWN"

                json_payload = json.dumps({
                    "type": "log",
                    "source": source,
                    "message": log_message
                })
                await active_websocket.send_text(json_payload)
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
        await asyncio.sleep(5)

# === Main startup ===
async def main():
    print("[System] Starting Coordinator Log Server...")
    asyncio.create_task(start_tcp_server())
    asyncio.create_task(periodic_db_fetch())
    asyncio.create_task(fetch_and_broadcast_data())
    config = uvicorn.Config(app, host="0.0.0.0", port=HTTP_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()




if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Shutdown] Coordinator log server stopped.")
