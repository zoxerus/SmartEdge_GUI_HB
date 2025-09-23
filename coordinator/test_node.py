from cassandra.cluster import Cluster
from datetime import datetime

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
            "last_ts": hb_row.last_ts.isoformat() if hb_row.last_ts else None,
        })

    # node keys
    key_row = session.execute(
        "SELECT public_key FROM node_keys WHERE node_uuid=%s", [uuid]
    ).one()
    if key_row:
        result.update({
            "public_key": key_row.public_key if key_row.public_key else "-",
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


if __name__ == "__main__":
    uuid = "SN010002"
    details = get_node_details(uuid)
    print("Node details:")
    for k, v in details.items():
        print(f"{k}: {v}")
