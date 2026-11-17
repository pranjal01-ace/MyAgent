import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List

logger = logging.getLogger("ace.ws")

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_event(self, event_type: str, data: dict):
        payload = json.dumps({"type": event_type, "data": data})
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                pass

ws_manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data_text = await websocket.receive_text()
            try:
                msg = json.loads(data_text)
                # Echo or handle incoming client state
                await ws_manager.broadcast_event("ack", msg)
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
