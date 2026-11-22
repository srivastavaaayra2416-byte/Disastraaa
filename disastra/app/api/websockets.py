import json
import logging
from typing import List, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSockets"])

class ConnectionManager:
    def __init__(self):
        self.dashboard_connections: Set[WebSocket] = set()
        self.volunteer_connections: Set[WebSocket] = set()

    async def connect_dashboard(self, websocket: WebSocket):
        await websocket.accept()
        self.dashboard_connections.add(websocket)

    def disconnect_dashboard(self, websocket: WebSocket):
        self.dashboard_connections.discard(websocket)

    async def broadcast_dashboard(self, message: dict):
        dead_connections = set()
        for conn in self.dashboard_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead_connections.add(conn)
        for dead in dead_connections:
            self.dashboard_connections.discard(dead)

    async def connect_volunteers(self, websocket: WebSocket):
        await websocket.accept()
        self.volunteer_connections.add(websocket)

    def disconnect_volunteers(self, websocket: WebSocket):
        self.volunteer_connections.discard(websocket)

    async def broadcast_volunteers(self, message: dict):
        dead_connections = set()
        for conn in self.volunteer_connections:
            try:
                await conn.send_json(message)
            except Exception:
                dead_connections.add(conn)
        for dead in dead_connections:
            self.volunteer_connections.discard(dead)

ws_manager = ConnectionManager()

@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await ws_manager.connect_dashboard(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo ping/pong or process control room commands
            await websocket.send_text(json.dumps({"status": "received", "data": data}))
    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)

@router.websocket("/ws/volunteers")
async def websocket_volunteers(websocket: WebSocket):
    await ws_manager.connect_volunteers(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(json.dumps({"status": "received", "data": data}))
    except WebSocketDisconnect:
        ws_manager.disconnect_volunteers(websocket)
