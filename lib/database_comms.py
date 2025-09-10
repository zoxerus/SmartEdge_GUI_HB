import lib.db.cassandra_db as cassandra_db
# import lib.db.redis_db as redis_db
import lib.db.defines as db_defines
from lib.performance_monitor import measure_performance
from lib.logger_utils import get_logger

db_logger = get_logger("coordinator", "Console")
db_logger_metric = get_logger("Coordinator", "Metric")

#logger = None

STR_DATABASE_TYPE_REDIS = 'redis'
STR_DATABASE_TYPE_CASSANDRA = 'cassandra'

DATABASE_IN_USE = None
DATABASE_SESSION = None
@measure_performance("Coordinator", db_logger_metric)
def init_database(host, port):
    
    if DATABASE_IN_USE == STR_DATABASE_TYPE_REDIS:
        return # redis_db.redis.Redis(host=host, port=port, decode_responses=True)

    elif DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:        
        # CONNECT TO THE DATABASE
        cluster = cassandra_db.Cluster(
            contact_points=[host], 
                        port=port, 
                        load_balancing_policy=cassandra_db.DCAwareRoundRobinPolicy(local_dc='datacenter1'),
                        protocol_version=5
        )
        session = cluster.connect()
        session.execute(f'DROP TABLE IF EXISTS {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE}')


        # CREATE A NAME SPACE IN THE DATABSE FOR STORING SWARM INFO
        query = cassandra_db.QUERY_DATABASE_CREATE_KEYSPACE
        result = session.execute( query )
        db_logger.debug(f"Executed database query:\n\t {query}\n\tgot result:\n\t\t{result.one()}")
        
        # CREATE A TABLE TO MANAGE ACTIVE SWARM NODES
        # query = cassandra_db.QUERY_DATABASE_CREATE_TABLE_ACTIVE_NODES
        
        
        result = session.execute(cassandra_db.QUERY_DATABASE_CREATE_TABLE_ACTIVE_NODES)
        db_logger.debug(f"Executed database query:\n\t {query}\n\tgot result:\n\t\t{result.one()}")
        
        # query = cassandra_db.QUERY_DATABASE_CREATE_TABLE_DEFAULT_SWARM
        
        result = session.execute(cassandra_db.QUERY_DATABASE_CREATE_TABLE_DEFAULT_SWARM)
        db_logger.debug(f"Executed database query:\n\t {query}\n\tgot result:\n\t\t{result.one()}")
        return session
@measure_performance("Coordinator", db_logger_metric)  
def connect_to_database(host, port):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_REDIS:
        return # redis_db.redis.Redis(host=host, port=port, decode_responses=True)

    elif DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:        
        # CONNECT TO THE DATABASE
        cluster = cassandra_db.Cluster(
            contact_points=[host], 
                        port=port, 
                        load_balancing_policy=cassandra_db.DCAwareRoundRobinPolicy(local_dc='datacenter1'),
                        protocol_version=5
        )
        session = cluster.connect()
        return session
@measure_performance("Coordinator", db_logger_metric)
def execute_query(query):
    try:
        result =  DATABASE_SESSION.execute(query)
        db_logger.debug(f"Executed database query:\n{query}")
        return result
    except Exception as e:
        db_logger.debug(f"Error in query:\n{query}, Error message {repr(e)}")
        return -1
@measure_performance("Coordinator", db_logger_metric)
def get_node_swarm_mac_by_swarm_ip(node_swarm_ip):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""SELECT {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_MAC} from 
        {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE}
        WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_IP} = '{node_swarm_ip}' ALLOW FILTERING; """
        result = execute_query(query)
        if (result == None or len(result) > 1 ):
            db_logger.error(f'Node {node_swarm_ip} not found in database or is duplicate, Node rejected')
        return result.one()[0]


# def update_db_with_joined_node(node_uuid, node_swarm_id):
#     if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
#         query = f"""UPDATE {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE}
#         SET {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{node_uuid}', 
#         {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_STATUS} = '{db_defines.SWARM_STATUS.JOINED.value}'
#         WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID} = {node_swarm_id};
#         """
#         result = execute_query(query)
#         return result
    
@measure_performance("Coordinator", db_logger_metric)    
def update_db_with_node_status(uuid, status):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""UPDATE {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE}
        SET {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_STATUS} = '{status}'
        WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID} = {uuid} IF EXISTS ;
        """
        result = execute_query(query)
        return result

@measure_performance("Coordinator", db_logger_metric)
def insert_node_into_swarm_database(host_id='', this_ap_id='', node_vip='', node_vmac='', node_phy_mac='', node_uuid='', status=''):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""
        INSERT INTO {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE} (
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID}, {db_defines.NAMEOF_DATABASE_FIELD_NODE_CURRENT_AP},
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_STATUS}, {db_defines.NAMEOF_DATABASE_FIELD_LAST_UPDATE_TIMESTAMP}, 
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_IP}, {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_MAC},
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_PHYSICAL_MAC}, {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID}
        )
        VALUES ({host_id}, '{this_ap_id}', '{status}', toTimeStamp(now() ),
        '{node_vip}', '{node_vmac}', '{node_phy_mac}', '{node_uuid}') ;
        """
        result = execute_query(query)
        return result
@measure_performance("Coordinator", db_logger_metric)
def reuse_node_swarm_id(uuid):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f""" 
        SELECT {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID} from 
        {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE}
        WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{uuid}' ALLOW FILTERING;
        """
        result = execute_query(query)
        return result

# GET NEXT AVAILABLE HOST ID FROM SWARM TABLE
@measure_performance("Coordinator", db_logger_metric)
def get_next_available_host_id_from_swarm_table(first_host_id, max_host_id, uuid):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        first_result = reuse_node_swarm_id(uuid)
        if first_result.one() == None:   
            query = f""" SELECT {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID} FROM 
                {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE} ALLOW FILTERING; 
                """
            result = execute_query(query)
            id_list = []
            for row in result:
                db_logger.debug(f"received Row from DB: {row}")
                id_list.append(row[0])
            if (id_list == []):
                db_logger.debug(f"getting next host id: id_list is empty: {id_list} returning {first_host_id}")
                return first_host_id
            result = min(set(range(first_host_id, max_host_id + 1 )) - set(id_list)) 
            db_logger.debug(f"getting next host id: {result}")
            return result 
        else: return first_result.one()[0]



# GET NEXT AVAILABLE HOST ID FROM SWARM TABLE
@measure_performance("Coordinator", db_logger_metric)
def batch_get_available_host_id_from_swarm_table(first_host_id, max_host_id):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f""" SELECT {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_ID} FROM 
            {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE} ALLOW FILTERING; 
            """
        result = execute_query(query)
        id_list = []
        for row in result:
            db_logger.debug(f"received Row from DB: {row}")
            id_list.append(row[0])
        if (id_list == []):
            db_logger.debug(f"getting next host id: id_list is empty: {id_list} returning {[first_host_id]}")
            return [host_id for host_id in range(first_host_id, max_host_id)]
        availalbe_ids = list( set(range(first_host_id, max_host_id + 1 )) - set(id_list) )
        availalbe_ids.sort()
        db_logger.debug(f"available host ids: {availalbe_ids}")
        return availalbe_ids

        
        
        
# GET NODE INFO FROM TDD
@measure_performance("Coordinator", db_logger_metric)
def get_node_info_from_art(node_uuid):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:    
        query = f""" 
        SELECT * FROM 
            {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_ADDRESS_RESOLUTION_TABLE}
        WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{node_uuid}';
        """
        return  execute_query(query)
  

# INSERT INTO TDD
@measure_performance("Coordinator", db_logger_metric)
def insert_into_art(node_uuid, current_ap, swarm_id, ap_port, node_ip):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:    
        query = f"""
        INSERT INTO {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_ADDRESS_RESOLUTION_TABLE} (
            {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID}, 
            {db_defines.NAMEOF_DATABASE_FIELD_NODE_CURRENT_AP}, 
            {db_defines.NAMEOF_DATABASE_FIELD_NODE_CURRENT_SWARM},
            {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_IP},
            {db_defines.NAMEOF_DATABASE_FIELD_AP_PORT},
            {db_defines.NAMEOF_DATABASE_FIELD_LAST_UPDATE_TIMESTAMP}
        ) VALUES 
        (
            '{node_uuid}', 
            '{current_ap}', 
            {swarm_id},
            '{node_ip}',
            {ap_port},
            toTimeStamp(now()) 
        ) ;
            """
        result = execute_query(query)
        return result
@measure_performance("Coordinator", db_logger_metric)
def delete_node_from_art(uuid):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""
            DELETE FROM {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_ADDRESS_RESOLUTION_TABLE} 
            WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{uuid}' ;
            """
        execute_query(query)
        delete_node_from_swarm_database(uuid)
        
@measure_performance("Coordinator", db_logger_metric)    
def delete_node_from_swarm_database(uuid):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""
            DELETE FROM {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_SWARM_TABLE} 
            WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{uuid}';
            """
        result = execute_query(query)
        return result
        
        
@measure_performance("Coordinator", db_logger_metric)        
def update_art_with_node_info(node_uuid, node_current_ap, node_current_swarm, node_current_ip):
    if DATABASE_IN_USE == STR_DATABASE_TYPE_CASSANDRA:
        query = f"""
        UPDATE 
        {db_defines.NAMEOF_DATABASE_SWARM_KEYSPACE}.{db_defines.NAMEOF_DATABASE_ADDRESS_RESOLUTION_TABLE}
        SET 
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_CURRENT_AP} = '{node_current_ap}', 
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_CURRENT_SWARM} = {node_current_swarm},
        {db_defines.NAMEOF_DATABASE_FIELD_NODE_SWARM_IP} = '{node_current_ip}'
        WHERE {db_defines.NAMEOF_DATABASE_FIELD_NODE_UUID} = '{node_uuid}';
        """
        result = execute_query(query)
        return result