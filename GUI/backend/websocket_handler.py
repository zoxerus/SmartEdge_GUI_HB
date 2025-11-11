# smartedge_gui/backend/websocket_handler.py
from fastapi import WebSocket
from typing import List
import asyncio
import datetime
from fastapi.encoders import jsonable_encoder

# === Connected clients list ===
active_connections: List[WebSocket] = []
client_lock = asyncio.Lock()

# === Connection management ===
async def connect_client(websocket: WebSocket):
    """Accept and register a new WebSocket client."""
    await websocket.accept()
    async with client_lock:
        active_connections.append(websocket)
    print(f"[WebSocketHandler] Client connected. Total: {len(active_connections)}")

async def disconnect_client(websocket: WebSocket):
    """Unregister a disconnected WebSocket client."""
    async with client_lock:
        if websocket in active_connections:
            active_connections.remove(websocket)
    print(f"[WebSocketHandler] Client disconnected. Total: {len(active_connections)}")

def get_websocket_clients() -> List[WebSocket]:
    """Optional helper for debugging/legacy utils."""
    return list(active_connections)

# === Simple string message broadcast (legacy use) ===
async def broadcast_message(message: str):
    """Broadcast plain string messages to all connected clients."""
    async with client_lock:
        disconnected = []
        for ws in active_connections:
            try:
                await ws.send_text(message)
            except Exception as e:
                print(f"[WebSocketHandler] Error sending text to client: {e}")
                disconnected.append(ws)

        for ws in disconnected:
            try:
                active_connections.remove(ws)
            except ValueError:
                pass

    print(f"[WebSocketHandler] Broadcasted message to {len(active_connections)} client(s)")

# === JSON broadcast for DB snapshots ===
async def broadcast_to_db_clients(message: dict):
    """
    Broadcast a JSON message (like a DB snapshot) to all connected WebSocket clients.
    Expected message format: { "type": "db_snapshot", "table": "art", "data": [...] }
    """
    try:
        payload = jsonable_encoder(
            message,
            custom_encoder={
                datetime.datetime: lambda v: v.isoformat(),
                datetime.date: lambda v: v.isoformat(),
            },
        )
    except Exception as e:
        print(f"[WebSocketHandler] Failed to encode message: {e}")
        return

    async with client_lock:
        disconnected = []

        for ws in list(active_connections):
            try:
                # Skip closed or closing websockets
                if ws.client_state.name != "CONNECTED":
                    print("[WebSocketHandler] Skipping closed websocket client")
                    disconnected.append(ws)
                    continue

                await ws.send_json(payload)

            except Exception as e:
                print(f"[WebSocketHandler] Error sending to client: {e}")
                disconnected.append(ws)

        # Cleanup disconnected clients
        for ws in disconnected:
            try:
                active_connections.remove(ws)
            except KeyError:
                pass

    if active_connections:
        print(f"[WebSocketHandler] Broadcasted DB snapshot to {len(active_connections)} client(s)")
    else:
        print("[WebSocketHandler] No active WebSocket clients to broadcast to.")

