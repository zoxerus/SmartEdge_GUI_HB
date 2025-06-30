# smartedge_gui/backend/websocket_handler.py
from fastapi import WebSocket
from typing import List

# Connected clients
active_connections: List[WebSocket] = []

async def connect_client(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)

def disconnect_client(websocket: WebSocket):
    if websocket in active_connections:
        active_connections.remove(websocket)

async def broadcast_message(message: str):
    print("[Broadcasting]:", message)
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except:
            pass  # We'll improve this later
