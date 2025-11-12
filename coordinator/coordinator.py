#!/usr/bin/python3
# This tells python to look for files in parent directory
import sys
import subprocess
import queue


# setting path
sys.path.append('..')
sys.path.append('.')

import asyncio
import psutil
import atexit
import lib.global_config as cfg
import ipaddress
import socket
import re
import os
import logging
import logging.handlers
import ipaddress
import json
import threading
import lib.bmv2_thrift_lib as bmv2
import lib.database_comms as db
import lib.global_constants as cts
import lib.helper_functions as utils
import lib.node_discovery as se_net

from argparse import ArgumentParser

STRs = cts.String_Constants

# parser = ArgumentParser()
# parser.add_argument("-l", "--log-level",type=int, default=50, help="set logging level [10, 20, 30, 40, 50]")
# parser.add_argument("-n", "--num-id",type=int, default=50, help="sequential uniq numeric id for node identification")
# args = parser.parse_args()




class SocketStreamHandler(logging.StreamHandler):
    """Custom StreamHandler to send logs over TCP."""
    def __init__(self, host, port):
        super().__init__(sys.stdout)  # StreamHandler needs an output stream
        self.host = host
        self.port = port
        self.sock = None
        self._connect()

    def _connect(self):
        """Establish connection to log server."""
        try:
            self.sock = socket.create_connection((self.host, self.port))
        except Exception as e:
            print(f"Failed to connect to log server: {e}")
            self.sock = None

    def emit(self, record):
        """Send log message to log server."""
        if not self.sock:
            self._connect()  # Try to reconnect if needed
            if not self.sock:
                return  # Drop log if connection fails

        try:
            msg = self.format(record) + "\n"
            self.sock.sendall(msg.encode('utf-8'))  # Send log as bytes
        except Exception as e:
            print(f"Error sending log: {e}")
            self.sock = None  # Reset socket on failure

    def close(self):
        """Close the socket when done."""
        if self.sock:
            self.sock.close()
        super().close()

SELF_TYPE='CO'
SELF_UUID = "null"

# dir_path = os.path.dirname(os.path.realpath(__file__))


# where to store program logs
# PROGRAM_LOG_FILE_NAME = './logs/coordinator.log'
# os.makedirs(os.path.dirname(PROGRAM_LOG_FILE_NAME), exist_ok=True)

logger = logging.getLogger(__name__)

# log_socket_handler = SocketStreamHandler( '127.0.0.1', cfg.logs_server_address[1] )
# log_info_formatter =  logging.Formatter("%(name)s %(asctime)s [%(levelname)s]:\n%(message)s\n")
# log_socket_handler.setFormatter(log_info_formatter)
# log_socket_handler.setLevel(logging.INFO)

# log_console_handler = logging.StreamHandler(sys.stdout)
# log_console_handler.setLevel(args.log_level)
# log_formatter = logging.Formatter("Line:%(lineno)d at %(asctime)s [%(levelname)s] Thread: %(threadName)s File: %(filename)s :\n%(message)s\n")
# log_console_handler.setFormatter(log_formatter)
# logger.setLevel(args.log_level)    
# logger.addHandler(log_console_handler)

# logger.debug(f'Running in: {dir_path}')

db.db_logger = logger
bmv2.bmv2_logger = logger

# thread_q = queue.Queue()

# TCP related
COORDINATOR_MAX_TCP_CONNNECTIONS = 5

# TODO: delete this
SWARM_NODE_TCP_SERVER = ('', 29997) 


DEFAULT_THRIFT_PORT = bmv2.DEFAULT_THRIFT_PORT

THIS_SWARM_SUBNET=ipaddress.ip_address( cfg.this_swarm_subnet )

db.DATABASE_IN_USE = db.STR_DATABASE_TYPE_CASSANDRA

database_session = db.init_database('0.0.0.0', cfg.database_port)
db.DATABASE_SESSION = database_session

## Group ID is for discovery
group_id = cfg.group_id
## interface is the network interface on which the discovery happens
interface = utils.get_default_iface_name_linux()
eth_ip = str( utils.get_interface_ip(interface) )
se_bb_ip = str( utils.get_interface_ip('smartedge-bb') )

## Here we start the discovery using the group id and the subnet of the ethernet interface
# SE_NODE = se_net.Node(node_type=SELF_TYPE, node_uuid=SELF_UUID, 
#                       node_sebackbone_ip=se_bb_ip, group_id=cfg.group_id)

SE_NODE = None

class Swarm_Node_Handler:
    def __init__(self, message, node_socket: socket.socket):
        logger.debug(f'\nNew Request: {message} ')
        self.node_request = json.loads(message)
        self.node_socket = node_socket

        
    def user_input_respond_to_node_request(self):
        while True:
            user_input = input("Enter 1 to Accept the request, 0 for Reject: ") 
            if (user_input == '1' or user_input == '0'):
                print('Accepting the node')
                return user_input
            else:
                print('Wrong Input')
                
        
    def handle_message(self):
        logger.debug(f"Handling Request with type {self.node_request[STRs.TYPE.name]}")
        match self.node_request[STRs.TYPE.name]:
            case STRs.JOIN_REQUEST.name:
                logger.debug(f"Handling Request with type {STRs.JOIN_REQUEST.name}")
                self.accept_join_request()
                    
            case 'Node_Left_AP':
                pass
            
            case STRs.LEAVE_REQUEST.name:
                ret_val = self.user_input_respond_to_node_request()
                if ret_val == 1:
                    pass
                    # self.node_socket.send( bytes( f'Accepted: {self.message}'.encode() ) )
                    # db.delete_node_from_swarm_database(self.node_swarm_id)
                else:
                    self.node_socket.send( bytes( f'Rejected: {self.message}'.encode() ) )
                    
            case _:
                logger.debug(f"Request Type Unkown {self.node_request[STRs.TYPE.name]}")
            
    def reject_join_request(self):
        pass

         
async def offboard_node(host_id, uuid, ap_id, node_vip, ap_port, available_nodes, lock):
    SN_UUID = uuid
    logger.debug(f'Kicking Node {SN_UUID} ip {node_vip} from Swarm')
    
    swarmNode_config = {
        STRs.TYPE.name: 'go_away'
    }
    
    config_message = json.dumps(swarmNode_config)
    
    logger.debug(f'Sending {config_message} to {node_vip}')
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # s.settimeout(5)
            s.connect((node_vip, cfg.node_manager_tcp_port))
            s.sendall( bytes( config_message.encode() ) )
            logger.debug(f'sent {config_message} to {SN_UUID}')
            s.close()
            async with lock:
                available_nodes.append(uuid)    
            # data = s.recv(1024) #receive up to 1024 bytes.decode()
            # logger.debug(f'response {data} from {SN_UUID}')
            # if data == 'OK!':
               
    except Exception as e:
        logger.error(f"Error Sending confing to Node {SN_UUID}: {repr(e)}")
        return
            

async def onboard_node(
    host_id, uuid, ap_id, node_s0_ip, ap_port,
    available_nodes, lock,
    heartbeat=False,
    hb_length=None,
    hb_window=None,
    hb_interval=None
):
    SN_UUID = uuid
    logger.debug(f'Accepted Node {SN_UUID} in Swarm')

    instance = SE_NODE.known_aps[ap_id]['cli_instance']
    result = utils.assign_virtual_mac_and_ip_by_host_id(subnet=THIS_SWARM_SUBNET, host_id=host_id)

    station_vmac = result[0]
    station_vip = result[1]

    logger.debug(f'assigning vIP: {station_vip} vMAC: {station_vmac} to {SN_UUID}')

    # === Build the configuration message ===
    swarmNode_config = {
        STRs.TYPE.name: STRs.SET_CONFIG.name,
        STRs.VETH1_VIP.name: station_vip,
        STRs.VETH1_VMAC.name: station_vmac,
        STRs.SWARM_ID.name: 1,
        STRs.COORDINATOR_VIP.name: cfg.coordinator_vip,
        STRs.COORDINATOR_TCP_PORT.name: cfg.coordinator_tcp_port,
        "heartbeat": heartbeat,
        "COORDINATOR_PUBKEY_PORT": 5007,
        "COORDINATOR_HB_PORT": 5008,
    }

    # ✅ Include heartbeat parameters if heartbeat is enabled
    if heartbeat:
        if hb_length is not None:
            swarmNode_config["hb_length"] = hb_length
        if hb_window is not None:
            swarmNode_config["hb_window"] = hb_window
        if hb_interval is not None:
            swarmNode_config["hb_interval"] = hb_interval

        logger.info(
            f"[ONBOARD] Node {SN_UUID} heartbeat enabled | "
            f"length={hb_length}, window={hb_window}, interval={hb_interval}"
        )
    else:
        logger.info(f"[ONBOARD] Node {SN_UUID} heartbeat disabled")

    # --- Send configuration message to the node ---
    config_message = json.dumps(swarmNode_config)
    logger.debug(f"[CONFIG] Sending to node {SN_UUID}: {config_message}")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            print(f"[DEBUG] Connecting to Node {SN_UUID} at {node_s0_ip}:{cfg.node_manager_tcp_port}")
            s.connect((node_s0_ip, cfg.node_manager_tcp_port))
            s.sendall(config_message.encode())
            logger.debug(f"[CONFIG] Sent to {SN_UUID}")
            s.close()

        async with lock:
            available_nodes.append(uuid)

    except Exception as e:
        logger.error(f"Error sending config to Node {SN_UUID}: {repr(e)}")
        return

    # --- Database update and P4 entries remain unchanged ---
    db.insert_node_into_swarm_database(
        host_id=host_id,
        this_ap_id=ap_id,
        node_vip=station_vip,
        node_vmac=station_vmac,
        node_phy_mac='',
        node_uuid=SN_UUID,
        status=db.db_defines.SWARM_STATUS.JOINED.value
    )

    db.update_art_with_node_info(
        node_uuid=SN_UUID,
        node_current_ap=ap_id,
        node_current_swarm=1,
        node_current_ip=station_vip
    )

    bmv2.add_bmv2_swarm_broadcast_port(instance=instance, switch_port=ap_port)

    entry_handle = bmv2.add_entry_to_bmv2(
        communication_protocol=bmv2.P4_CONTROL_METHOD_THRIFT_CLI,
        table_name='MyIngress.tb_ipv4_lpm',
        action_name='MyIngress.ac_ipv4_forward_mac_from_dst_ip',
        match_keys=f'{station_vip}/32',
        action_params=str(ap_port),
        instance=instance
    )

    # --- replicate entry across other APs ---
    for uuid, sw_data in SE_NODE.get_aps_dict().items():
        if uuid != ap_id:
            ap_mac = utils.int_to_mac(int(ipaddress.ip_address(sw_data['sebackbone_ip'])))
            bmv2.add_entry_to_bmv2(
                communication_protocol=bmv2.P4_CONTROL_METHOD_THRIFT_CLI,
                table_name='MyIngress.tb_ipv4_lpm',
                action_name='MyIngress.ac_ipv4_forward_mac',
                match_keys=f'{station_vip}/32',
                action_params=f'{cfg.swarm_backbone_switch_port} {ap_mac}',
                instance=sw_data['cli_instance']
            )


# a function to configure the keep alive of the tcp connection
def set_keepalive_linux(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    """Set TCP keepalive on an open socket.

    It activates after 1 second (after_idle_sec) of idleness,
    then sends a keepalive ping once every 3 seconds (interval_sec),
    and closes the connection after 5 failed ping (max_fails), or 15 seconds
    """
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

            
def handle_swarm_node(node_socket, address):
    try:
        message = node_socket.recv(1024).decode()
        logger.debug(f'received: {message} from {address}')    
        
        message_handler = Swarm_Node_Handler(message= message, node_socket=node_socket)
        message_handler.handle_message()
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        print(f"Exception Type: {exc_type.__name__}")
        print(f"File: {exc_tb.tb_frame.f_code.co_filename}")
        print(f"Line Number: {exc_tb.tb_lineno}")
        logger.error(f'Error Handling swarm Node {address}: {e}')
        
 

# receives TCP connections from swarm nodes
def swarm_coordinator():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as serversocket:
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(SWARM_NODE_TCP_SERVER)
        set_keepalive_linux(sock= serversocket, after_idle_sec=1, interval_sec=3, max_fails= 5)
        serversocket.listen(COORDINATOR_MAX_TCP_CONNNECTIONS)
        print('Coordinator Script is Running')
        while True:
            logger.debug(f'Waiting for Requests ... ')
            (node_socket, address) = serversocket.accept()
            logger.debug(f'received connection request from {address}')
            handle_swarm_node(node_socket=node_socket, address=address)
            # threading.Thread(target=handle_swarm_node, args=(node_socket, address, ), daemon= True ).start()


str_TYPE = 'Type'
str_NODE_JOIN_LIST = 'njl'
str_NODE_LEAVE_LIST = 'nll'
str_AVAILABLE_NODES = 'avn'
str_NODE_IDS = 'nids'

async def handle_ac_communication(ac_socket):
    try:
        ac_message_in = ac_socket.recv(1024)
        if not ac_message_in:
            logger.error('Connection closed before sending data; ignoring')
            return

        logger.debug(f'ac_message_in: {ac_message_in}')
        ac_message_in_json = json.loads(ac_message_in.decode())

        if ac_message_in_json[str_TYPE] == str_NODE_JOIN_LIST:
            # --- Parse heartbeat parameters if provided ---
            heartbeat_enabled = ac_message_in_json.get("heartbeat", False)
            hb_length = ac_message_in_json.get("hb_length")
            hb_window = ac_message_in_json.get("hb_window")
            hb_interval = ac_message_in_json.get("hb_interval")

            logger.info(
                f"[AC] Received JOIN request | Heartbeat={heartbeat_enabled} "
                f"length={hb_length}, window={hb_window}, interval={hb_interval}"
            )

            # --- Retrieve target node(s) from DB ---
            query = f"""SELECT * FROM ks_swarm.art WHERE uuid IN (
                {', '.join(repr(item) for item in ac_message_in_json[str_NODE_IDS])});"""
            rows = db.execute_query(query)

            availalbe_nodes_ids = []
            available_nodes_ips = []
            available_nodes_aps = []
            available_nodes_ports = []

            for row in rows:
                if row.current_swarm == 0:
                    availalbe_nodes_ids.append(row.uuid)
                    available_nodes_ips.append(row.virt_ip)
                    available_nodes_aps.append(row.current_ap)
                    available_nodes_ports.append(row.ap_port)

            if not available_nodes_ips:
                logger.warning("[AC] No available nodes found for join request.")
                return

            available_host_ids = db.batch_get_available_host_id_from_swarm_table(
                first_host_id=cfg.this_swarm_dhcp_start,
                max_host_id=cfg.this_swarm_dhcp_end
            )

            available_nodes = []
            lock = asyncio.Lock()
            tasks = []

            for i in range(len(available_nodes_ips)):
                host_id = available_host_ids[i]
                node_uuid = availalbe_nodes_ids[i]
                node_s0_ip = available_nodes_ips[i]
                ap_id = available_nodes_aps[i]
                ap_port = available_nodes_ports[i]

                # ✅ Pass heartbeat params directly to onboard_node()
                task = asyncio.create_task(
                    onboard_node(
                        host_id=host_id,
                        uuid=node_uuid,
                        ap_id=ap_id,
                        node_s0_ip=node_s0_ip,
                        ap_port=ap_port,
                        available_nodes=available_nodes,
                        lock=lock,
                        heartbeat=heartbeat_enabled,
                        hb_length=hb_length,
                        hb_window=hb_window,
                        hb_interval=hb_interval
                    )
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

            message = {
                'Type': str_AVAILABLE_NODES,
                str_NODE_IDS: available_nodes
            }
            try:
                ac_socket.sendall(json.dumps(message).encode())
            except (BrokenPipeError, ConnectionResetError):
                logger.error("Error sending response back to Adaptive Coordinator")

        elif ac_message_in_json[str_TYPE] == str_NODE_LEAVE_LIST:
            # unchanged leave logic
            query = f"""SELECT * FROM ks_swarm.art WHERE uuid IN (
                {', '.join(repr(item) for item in ac_message_in_json[str_NODE_IDS])});"""
            rows = db.execute_query(query)
            availalbe_nodes_ids = []
            available_nodes_ips = []
            available_nodes_aps = []
            available_nodes_ports = []
            for row in rows:
                availalbe_nodes_ids.append(row.uuid)
                available_nodes_ips.append(row.virt_ip)
                available_nodes_aps.append(row.current_ap)
                available_nodes_ports.append(row.ap_port)
            if not available_nodes_ips:
                return
            available_host_ids = db.batch_get_available_host_id_from_swarm_table(
                first_host_id=cfg.this_swarm_dhcp_start,
                max_host_id=cfg.this_swarm_dhcp_end
            )
            available_nodes = []
            lock = asyncio.Lock()
            tasks = []
            for i in range(len(available_nodes_ips)):
                host_id = available_host_ids[i]
                node_uuid = availalbe_nodes_ids[i]
                node_s0_ip = available_nodes_ips[i]
                ap_id = available_nodes_aps[i]
                ap_port = available_nodes_ports[i]
                task = asyncio.create_task(
                    offboard_node(
                        host_id=host_id,
                        uuid=node_uuid,
                        ap_id=ap_id,
                        node_vip=node_s0_ip,
                        ap_port=ap_port,
                        available_nodes=available_nodes,
                        lock=lock
                    )
                )
                tasks.append(task)
            await asyncio.gather(*tasks)

            message = {'Type': str_AVAILABLE_NODES, str_NODE_IDS: available_nodes}
            try:
                ac_socket.sendall(json.dumps(message).encode())
            except Exception:
                logger.error("Error sending response to Adaptive Coordinator")

    except Exception as e:
        logger.exception(f"Error in handle_ac_communication: {e}")



HOST = '0.0.0.0'
NODE_PORT = 9997
AP_PORT = 9998
HIGHER_PORT = 9999

def node_handler(HOST, HIGHER_PORT):
    return

def ap_handler(HOST, HIGHER_PORT):
    return

def adaptive_coordinator_handler(HOST, HIGHER_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as serversocket:
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind((HOST, HIGHER_PORT))
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        serversocket.listen(3)
        print('AC Thread is Running: waiting for communication ..')
        iter = 0
        while True:
            iter += 1
            logger.debug(f'Listening on {HOST}:{HIGHER_PORT} iteration {iter}')
            ac_socket, address = serversocket.accept()
            try:
                set_keepalive_linux(ac_socket, after_idle_sec=30, interval_sec=10, max_fails=5)
                logger.debug(f'received connection request from {address}')
                asyncio.run(handle_ac_communication(ac_socket))
            except Exception as e:
                logger.error(f'AC handler error from {address}: {e}')
            finally:
                try:
                    ac_socket.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                ac_socket.close()



def exit_handler():
    pass

def main():
    atexit.register(exit_handler)
    logger.info('Coordinator Starting')
    SE_NODE.start()
    node_thread = threading.Thread(target=node_handler, args=(HOST, NODE_PORT))
    ap_thread = threading.Thread(target=ap_handler, args=(HOST, AP_PORT ))
    ac_thread = threading.Thread(target=adaptive_coordinator_handler, args=(HOST, HIGHER_PORT))
    node_thread.start()
    ap_thread.start()
    ac_thread.start()
    
def run(uuid):
    global SELF_UUID, SE_NODE
    SELF_UUID = uuid
    # atexit.register(exit_handler)
    logger.info('Coordinator Starting')
    SE_NODE = se_net.Node(node_type=SELF_TYPE, node_uuid=SELF_UUID, 
                      node_sebackbone_ip=se_bb_ip, group_id=cfg.group_id)
    SE_NODE.start()
    node_thread = threading.Thread(target=node_handler, args=(HOST, NODE_PORT))
    ap_thread = threading.Thread(target=ap_handler, args=(HOST, AP_PORT ))
    ac_thread = threading.Thread(target=adaptive_coordinator_handler, args=(HOST, HIGHER_PORT))
    node_thread.start()
    ap_thread.start()
    ac_thread.start()

if __name__ == "__main__":
    main()
