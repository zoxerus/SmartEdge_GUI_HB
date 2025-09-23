# backend/heartbeat_api.py
import asyncio
import subprocess
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from cassandra.cluster import Cluster
from cassandra.query import dict_factory

router = APIRouter()

# Cassandra connection (adjust contact points if needed)
cluster = Cluster(["127.0.0.1"])
session = cluster.connect()

# return rows as dicts
session.row_factory = dict_factory

# ---------------- REST API ----------------

@router.get("/api/swarm/members")
def get_swarm_members():
    session.set_keyspace("ks_swarm")
    rows = session.execute("SELECT * FROM swarm_table;")
    members = []
    for r in rows:
        members.append({
            "uuid": r["uuid"],
            "status": r["status"],
            "swarm": r["current_ap"],
            "virt_ip": r["virt_ip"],
            "virt_mac": r["virt_mac"],
        })
    return members

@router.get("/api/swarm/member/{uuid}")
def get_node_details(uuid: str):
    cluster = Cluster(["127.0.0.1"])   # adjust if Cassandra is remote
    session = cluster.connect()

    result = {"uuid": uuid}

    # heartbeat state
    session.set_keyspace("swarm")
    hb_row = session.execute(
        "SELECT status, last_ts FROM heartbeat_state WHERE node_uuid=%s", [uuid]
    ).one()
    if hb_row:
        result.update({
            "status": hb_row.status if hb_row.status else "-",
            "last_ts": hb_row.last_ts.strftime("%Y-%m-%d %H:%M:%S") if hb_row.last_ts else None,
        })

    # node keys
    key_row = session.execute(
        "SELECT public_key FROM node_keys WHERE node_uuid=%s", [uuid]
    ).one()
    if key_row:
        public_key = key_row.public_key
        if isinstance(public_key, (bytes, bytearray)):
            public_key = public_key.hex()
        result.update({
            "public_key": public_key if public_key else "-",
        })

    # node swarm table
    session.set_keyspace("ks_swarm")
    swarm_row = session.execute(
        "SELECT current_ap, virt_ip, virt_mac FROM swarm_table WHERE uuid=%s", [uuid]
    ).one()
    if swarm_row:
        result.update({
            "swarm": swarm_row.current_ap if swarm_row.current_ap else "-",
            "virt_ip": swarm_row.virt_ip if swarm_row.virt_ip else "-",
            "virt_mac": swarm_row.virt_mac if swarm_row.virt_mac else "-",
        })

    cluster.shutdown()
    return result





# ---------------- WEBSOCKET LOGS ----------------

clients = set()
process = None

async def read_logs_and_forward():
    global process
    if process is None:
        # run heartbeat_server.py as a subprocess
        process = await asyncio.create_subprocess_exec(
            "python3", "-u", "heartbeat_server.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    assert process.stdout
    while True:
        line = await process.stdout.readline()
        if not line:
            break
        message = line.decode().rstrip()
        # forward to all connected clients
        for ws in list(clients):
            try:
                await ws.send_text(message)
            except Exception:
                clients.remove(ws)


@router.websocket("/ws/heartbeat_logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)

    # Start background log reader if not already running
    if len(clients) == 1:
        asyncio.create_task(read_logs_and_forward())

    try:
        while True:
            await asyncio.sleep(10)  # keep connection open
    except WebSocketDisconnect:
        clients.remove(websocket)

