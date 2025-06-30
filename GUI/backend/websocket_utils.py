# backend/websocket_utils.py

import asyncio
from websocket_handler import get_websocket_clients

async def send_json_to_websocket(message: dict):
    data = message
    for websocket in get_websocket_clients():
        try:
            await websocket.send_json(data)
        except Exception as e:
            print(f"[WebSocket] Error sending message: {e}")
