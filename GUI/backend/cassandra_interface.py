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
from cassandra.cluster import Cluster
from cassandra.query import dict_factory
from websocket_handler import broadcast_to_db_clients

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



async def fetch_and_broadcast_data(target_table: str | None = None):
    """
    Fetch data from Cassandra and broadcast via WebSocket.
    Always broadcasts both 'art' and 'swarm_table' to ensure GUI stays in sync.
    If Cassandra ever has multiple swarm tables, it will include them automatically.
    """
    try:
        cluster = Cluster([CASSANDRA_HOST])
        session = cluster.connect(KEYSPACE)
        session.row_factory = dict_factory

        # Always include both main tables; dynamically add other swarm tables if any
        tables = ["art", "swarm_table"]

        # Also include any dynamically created swarm tables, if they exist
        try:
            extra_tables = [
                row["table_name"]
                for row in session.execute(
                    "SELECT table_name FROM system_schema.tables WHERE keyspace_name = %s",
                    (KEYSPACE,),
                )
                if row["table_name"].startswith("swarm_table") and row["table_name"] not in tables
            ]
            tables.extend(extra_tables)
        except Exception as e:
            print(f"[DB Broadcast] Warning: couldn't enumerate system tables: {e}")

        print(f"[DB Broadcast] Triggered for target_table={target_table}, fetching {tables}")

        for table in tables:
            try:
                rows = session.execute(f"SELECT * FROM {table}")
                data = [dict(row) for row in rows]

                await broadcast_to_db_clients({
                    "type": "db_snapshot",
                    "table": table,
                    "data": data
                })

                print(f"[DB Broadcast] Sent snapshot for {table} ({len(data)} rows)")

            except Exception as e:
                print(f"[DB Broadcast] Error fetching table {table}: {e}")

        print(f"[DB Broadcast] Successfully broadcast {len(tables)} table(s): {tables}")

    except Exception as e:
        print(f"[DB Broadcast] Fatal error fetching data: {e}")




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