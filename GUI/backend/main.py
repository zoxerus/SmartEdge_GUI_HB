# smartedge_gui/backend/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from cassandra_interface import fetch_and_broadcast_data
from websocket_handler import connect_client, disconnect_client
from tcp_log_receiver import start_tcp_server
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import FastAPI
from cassandra_interface import query_art_nodes
import uvicorn
import asyncio
import os
from fastapi import Request
import subprocess

from websocket_handler import connect_client, disconnect_client
from tcp_log_receiver import start_tcp_server
from cassandra_interface import fetch_and_broadcast_data


app = FastAPI()

# Define absolute paths to static subfolders
BASE_DIR = os.path.dirname(__file__)
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
#STATIC_JS = os.path.abspath(os.path.join(BASE_DIR, "../frontend/js"))
#STATIC_CSS = os.path.abspath(os.path.join(BASE_DIR, "../frontend/css"))

# Mount JS and CSS folders separately
#app.mount("/static/js", StaticFiles(directory=STATIC_JS), name="js")
#app.mount("/static/css", StaticFiles(directory=STATIC_CSS), name="css")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

#@app.get("/")
#def get_index():
#    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await connect_client(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        disconnect_client(websocket)

@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(start_tcp_server())
    asyncio.create_task(fetch_and_broadcast_data())

@app.get("/fetch-db")
async def fetch_db_trigger():
    await fetch_and_broadcast_data()
    return {"status": "ok"}

@app.get("/art-nodes")
def get_art_nodes():
    try:
        return query_art_nodes()
    except Exception as e:
        return {"error": str(e)}


@app.post("/request-join")
async def request_join(request: Request):
    data = await request.json()
    uuid = data.get("uuid")

    if not uuid:
        return {"success": False, "error": "No UUID provided"}

    try:
        result = subprocess.run(
            ["python3", "/home/Coordinator/smartedge_GUI/tests/ac_request_nodes_to_join.py", uuid],
            capture_output=True,
            text=True,
            timeout=5  # Optional: timeout in seconds
        )
        print("[SCRIPT STDOUT]:", result.stdout)
        print("[SCRIPT STDERR]:", result.stderr)
        print("[SCRIPT RETURN CODE]:", result.returncode)


        if result.returncode != 0:
            return {"success": False, "error": result.stderr or "Script failed"}

        return {"success": True, "output": result.stdout.strip()}

    except Exception as e:
        return {"success": False, "error": str(e)}

# Entry point
if __name__ == "__main__":
    #loop = asyncio.get_event_loop()
    #loop.create_task(start_tcp_server())
    #loop.create_task(fetch_and_broadcast_data())
    uvicorn.run(app, host="0.0.0.0", port=8000)
