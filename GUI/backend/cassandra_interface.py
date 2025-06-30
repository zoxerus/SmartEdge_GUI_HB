# smartedge_gui/backend/cassandra_interface.py
from cassandra.cluster import Cluster
import asyncio
from websocket_handler import broadcast_message
from cassandra.cluster import Session
#from db_connection import get_session
import json
import datetime
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from lib import database_comms as db

CASSANDRA_HOST = "127.0.0.1"
KEYSPACE = "ks_swarm"
TABLES = ["art", "swarm_table"]

def clean_data(obj):
    if isinstance(obj, dict):
        return {k: clean_data(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_data(i) for i in obj]
    elif isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    return obj

async def fetch_and_broadcast_data():
    cluster = Cluster([CASSANDRA_HOST])
    session = cluster.connect()
    session.set_keyspace(KEYSPACE)

    for table in TABLES:
        try:
            rows = session.execute(f"SELECT * FROM {table}")
            data = [dict(row._asdict()) for row in rows]
            cleaned_data = clean_data(data)
            await broadcast_message(json.dumps({
                "type": "db",
                "table": table,
                "data": cleaned_data
            }))
        except Exception as e:
            print(f"[Cassandra Error] {e}")


def query_art_nodes():
    #session = get_session()
    rows = db.DATABASE_SESSION.execute("SELECT uuid, current_swarm, last_update FROM ks_swarm.art")
    result = []
    for row in rows:
        result.append({
            "uuid": row.uuid,
            "swarm_id": row.current_swarm,
            "status": "online"  # You can replace this with real logic later
        })
    return result