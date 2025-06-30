from cassandra.cluster import Cluster
import json

cluster = Cluster(["127.0.0.1"])
session = cluster.connect()
session.set_keyspace("ks_swarm")

tables = ["art", "swarm_table"]

for table in tables:
    rows = session.execute(f"SELECT * FROM {table}")
    data = [dict(row._asdict()) for row in rows]
    print(f"{table}:", json.dumps(data, indent=2, default=str))
