# This tells python to look for files in parent folders
import sys
# setting path
sys.path.append('.')
sys.path.append('..')
sys.path.append('../..')


import subprocess
import psutil
import logging
import threading
import atexit
import queue
import time
import socket
import ipaddress
import os
import json
import lib.global_config as cfg
from lib.helper_functions import *
import lib.global_constants as cts
import lib.helper_functions as utils
from pathlib import Path

STRs = cts.String_Constants 


from argparse import ArgumentParser
parser = ArgumentParser()
parser.add_argument("-l", "--log-level",type=int, default=50, help="set logging level [10, 20, 30, 40, 50]")
args = parser.parse_args()


PROGRAM_LOG_FILE_NAME = './logs/program.log'
os.makedirs(os.path.dirname(PROGRAM_LOG_FILE_NAME), exist_ok=True)
logger = logging.getLogger('SN_Logger')
# this part handles logging to console and to a file for debugging purposes
log_formatter =  logging.Formatter("Line:%(lineno)d at %(asctime)s [%(levelname)s] Thread: %(threadName)s File: %(filename)s :\n%(message)s\n")
log_console_handler = logging.StreamHandler(sys.stdout)  # (sys.stdout)
# log_console_handler.setLevel(args.log_level)
log_console_handler.setFormatter(log_formatter)
logger.setLevel(args.log_level)
# logger.addHandler(log_file_handler)
logger.addHandler(log_console_handler)



DEFAULT_IFNAME = 'wlan0'
loopback_if = 'lo:0'
NODE_TYPE = 'SN'
THIS_NODE_UUID = utils.generate_uuid_from_lo(loopback_if, NODE_TYPE)
print('Assigned Node UUID:', THIS_NODE_UUID)
ACCESS_POINT_IP = ''
q_to_coordinator = queue.Queue()
q_to_mgr = queue.Queue()


gb_swarmNode_config = {
    # STRs.VXLAN_ID : None,
    # STRs.VETH1_VIP: '',
    # STRs.SWARM_ID: '',
    # STRs.VETH1_VMAC: '',
    # STRs.COORDINATOR_VIP: '',
    # STRs.COORDINATOR_TCP_PORT: '',
    # STRs.AP_ID: '',
    # STRs.AP_IP: '',
    # STRs.AP_MAC: ''
}

last_request_id = 0

# --- Heartbeat Monitor status file config + helpers ---
def resolve_state_base_dir():
    # Allow override for testing or special setups
    override = os.environ.get("SE_SWARM_STATE_FILE")
    if override:
        p = Path(override)
        return p.parent, p

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        base = Path("/home") / sudo_user
    else:
        # Fallbacks if not running under sudo
        env_user = os.environ.get("LOGNAME") or os.environ.get("USER")
        if env_user and env_user != "root" and (Path("/home") / env_user).exists():
            base = Path("/home") / env_user
        else:
            base = Path.home()  # last resort

    dir_ = base / "smartedge" / "node_manager" / "heartbeat"
    file_ = dir_ / "swarm_status.json"
    return dir_, file_

SWARM_STATE_DIR, SWARM_STATE_FILE = resolve_state_base_dir()

DEFAULT_PUBKEY_PORT = 5007
DEFAULT_HB_PORT = 5008
DEFAULT_HB_INTERVAL = 1.0
SWARM_CIDR = os.environ.get("SE_SWARM_CIDR", "10.1.0.0/24")

def atomic_write_json(path, data: dict):
    path = Path(path)
    os.makedirs(path.parent, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

logger.info(f"[HB] Using swarm status file at: {SWARM_STATE_FILE}")

def handle_successful_join(config_data: dict, ap_address: tuple, client_id: str = None):
    if client_id is None:
        client_id = THIS_NODE_UUID

    # pull VETH1_VIP
    veth1_ip = (config_data.get(STRs.VETH1_VIP.name)
                if hasattr(STRs, "VETH1_VIP") else config_data.get("VETH1_VIP"))
    if not veth1_ip:
        logger.warning("[HB] SET_CONFIG missing VETH1_VIP; marking joined:false.")
        handle_leave_event()
        return

    try:
        ip_obj = ipaddress.ip_address(veth1_ip)
        swarm_net = ipaddress.ip_network(SWARM_CIDR, strict=False)   # e.g. "10.1.0.0/24"
    except Exception as e:
        logger.error(f"[HB] Invalid IP or CIDR (VETH1_VIP={veth1_ip}, SWARM_CIDR={SWARM_CIDR}): {e}. Marking joined:false.")
        handle_leave_event()
        return

    if ip_obj not in swarm_net:
        logger.info(f"[HB] VETH1_VIP {veth1_ip} NOT in swarm {SWARM_CIDR}. Marking joined:false.")
        handle_leave_event()
        return

    # In swarm → joined:true
    ap_swarm_ip = None
    for key in ("AP_SWARM_IP", "HB_DST_IP", "AP_VIP"):
        if key in config_data and config_data[key]:
            ap_swarm_ip = config_data[key]
            break

    if not ap_swarm_ip:
        ap_swarm_ip = ap_address[0]
        logger.warning("[HB] AP swarm IP not provided; TEMP fallback to physical AP IP. "
                       "Please include 'AP_SWARM_IP' or 'HB_DST_IP' in SET_CONFIG.")

    write_swarm_status_join(
        ap_swarm_ip=ap_swarm_ip,
        client_id=client_id,
        pubkey_tcp_port=DEFAULT_PUBKEY_PORT,
        hb_udp_port=DEFAULT_HB_PORT,
        hb_interval=DEFAULT_HB_INTERVAL
    )



def handle_leave_event():
    """Called on go_away or Wi-Fi disconnect. Writes joined=false status."""
    state = {"joined": False}
    atomic_write_json(SWARM_STATE_FILE, state)
    logger.debug("[HB] Wrote swarm leave status.")


def write_swarm_status_join(ap_swarm_ip, client_id, pubkey_tcp_port, hb_udp_port, hb_interval):
    state = {
        "joined": True,
        "client_id": client_id,
        "ap_swarm_ip": ap_swarm_ip,
        "pubkey_tcp_port": pubkey_tcp_port,
        "hb_udp_port": hb_udp_port,
        "hb_interval": hb_interval
    }
    atomic_write_json(SWARM_STATE_FILE, state)
    logger.debug(f"[HB] Wrote swarm join status: {state}")

# ------------------------------------------------------




def get_ip_from_arp_by_physical_mac(physical_mac):
    shell_command = "arp -en"
    proc = subprocess.run( shell_command.split(), text=True, stdout=subprocess.PIPE)
    for line in proc.stdout.strip().splitlines():
        if physical_mac in line:
            return line.split()[0]



def get_ap_physical_ip_by_ifname(ifname):
    cli_command = f"iwconfig {ifname}"
    command_as_word_array = cli_command.split()
    proc = subprocess.run(command_as_word_array, text=True, stdout=subprocess.PIPE)
    res_lines = proc.stdout.strip().splitlines()
    for line in res_lines:
      if 'Access Point' in line:
            mac = line.split()[5]
            print(f'AP MAC {mac}')
            return get_ip_from_arp_by_physical_mac(mac)
        
        
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


PING_IN_PROGRESS = False

def handle_communication():
    global last_request_id, gb_swarmNode_config, ACCESS_POINT_IP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as node_manager_socket:
        try:
            set_keepalive_linux(sock= node_manager_socket, after_idle_sec=1, interval_sec=3, max_fails= 5)
            node_manager_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            node_manager_socket.bind( ('0.0.0.0', cfg.node_manager_tcp_port) )

            logger.debug(f'Node Manager Listening on port {cfg.node_manager_tcp_port} ...')
        except Exception as e:
            logger.error(f'Exception in Node Manager Socket: {e}')
        iter = 0
        while True:
            iter = iter + 1 
            print(f'Node Manager waiting for instruction, iteration {iter}')
            node_manager_socket.listen()
            remote_socket, ap_address = node_manager_socket.accept()
            ACCESS_POINT_IP = ap_address[0]
            if not PING_IN_PROGRESS:
                ping_command = f'ping {ACCESS_POINT_IP}'
                subprocess.Popen(ping_command.split(), stdout=subprocess.PIPE )
            comm_buffer = remote_socket.recv(1024).decode()
            logger.debug(f'received: {comm_buffer}')
            config_data = json.loads(comm_buffer)
            logger.debug(f'config_data: {config_data}')                                         
            if config_data[STRs.TYPE.name] == STRs.SET_CONFIG.name:
                logger.debug(f'Handling Join Type {STRs.SET_CONFIG.name}')
                try:    
                    if STRs.VXLAN_ID.name in config_data.keys():
                        install_swarmNode_config(config_data)
                    else:
                        install_config_no_update_vxlan(config_data)
                    handle_successful_join(config_data, ap_address, client_id=THIS_NODE_UUID)
                except Exception as e:
                    logger.error(repr(e))
                    return
            elif config_data[STRs.TYPE.name] == 'go_away':
                print('Leaving Swarm' )
                cli_command = f'nmcli connection show --active'
                res = subprocess.run(cli_command.split(), text=True, stdout=subprocess.PIPE)
                ap_ssid = ''
                for line in res.stdout.strip().splitlines():
                    if DEFAULT_IFNAME in line:
                        ap_ssid = line.split()[0]
                cli_command = f'nmcli connection down id {ap_ssid}'
                subprocess.run(cli_command.split(), text=True)
                time.sleep(1)
                cli_command = f'nmcli connection up id {ap_ssid}'
                subprocess.run(cli_command.split(), text=True)
                handle_leave_event()
                pass
            remote_socket.sendall(bytes( "OK!".encode() ))
            remote_socket.close()


def install_config_no_update_vxlan(config_data):
    swarm_veth1_vip = config_data[STRs.VETH1_VIP.name]
    swarm_veth1_vmac = config_data[STRs.VETH1_VMAC.name]

    commands = [
                # add the vmac and vip (received from the AP manager) to the veth1 interface,
                f'ip link set veth1 address {swarm_veth1_vmac} ',
                f'ifconfig veth1 {swarm_veth1_vip} netmask 255.255.0.0 up',
                f'ip link set veth0 up',
                f'ip route replace default dev veth1',
                f'ip link set dev veth1 mtu 1400',
                # disable HW offloads of checksum calculation, (as this is a virtual interface)
                    f'ethtool --offload veth1 rx off tx off'
                ]
    
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        if (process_ret.stderr):
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")

def install_swarmNode_config(swarmNode_config):
    global last_request_id, join_queue, ACCESS_POINT_IP

    vxlan_id = swarmNode_config[STRs.VXLAN_ID.name]
    swarm_veth1_vip = swarmNode_config[STRs.VETH1_VIP.name]
    swarm_veth1_vmac = swarmNode_config[STRs.VETH1_VMAC.name]

    commands = [ 
                'ip link del se_vxlan',
                'ip link del veth1',
                # add the vxlan interface to the AP
                f'ip link add se_vxlan type vxlan id {vxlan_id} dev {DEFAULT_IFNAME} remote {ACCESS_POINT_IP} dstport 4789',
                # bring the vxlan up
                'ip link set dev se_vxlan up',    
                # add the veth interface pair, will be ignored if name is duplicate
                'ip link add veth0 type veth peer name veth1',
                # add the vmac and vip (received from the AP manager) to the veth1 interface,
                f'ip link set veth1 address {swarm_veth1_vmac} ',
                f'ifconfig veth1 {swarm_veth1_vip} netmask 255.255.0.0 up',
                f'ip link set veth0 up',
                f'ip route replace default dev veth1',
                f'ip link set dev veth1 mtu 1400',
                # disable HW offloads of checksum calculation, (as this is a virtual interface)
                    f'ethtool --offload veth1 rx off tx off'
                ]
    
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command, text=True, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        if (process_ret.stderr):
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")
        
    get_if1_index_command = 'cat /sys/class/net/veth0/ifindex'
    get_if2_index_command = 'cat /sys/class/net/se_vxlan/ifindex'
    if1_index = subprocess.run(get_if1_index_command.split(), text=True , stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if2_index = subprocess.run(get_if2_index_command.split(), text=True , stdout=subprocess.PIPE, stderr=subprocess.PIPE)   
    
    commands = [
        'nikss-ctl pipeline unload id 0',        
        'nikss-ctl pipeline load id 0 ./node_manager/utils/nikss.o',
        'nikss-ctl add-port pipe 0 dev veth0',
        'nikss-ctl add-port pipe 0 dev se_vxlan',
        f'nikss-ctl table add pipe 0 ingress_route action id 2 key {if1_index.stdout} data {if2_index.stdout}',
        f'nikss-ctl table add pipe 0 ingress_route action id 2 key {if2_index.stdout} data {if1_index.stdout}'
    ]
    
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE )
        if (process_ret.stderr):
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")
        else: 
            logger.debug(f'executed command {command} and got output: {process_ret.stdout}')
    
def exit_handler():
    logger.info('Handling exit')
    try:
        # Notify heartbeat monitor to stop
        handle_leave_event()
    except Exception as e:
        logger.error(f"Failed to write leave status in exit_handler: {e}")

    try:
        # Existing disconnection cleanup (currently stubbed)
        handle_disconnection()
    except Exception as e:
        logger.error(f"Error during disconnection cleanup: {e}")

        
        
def handle_disconnection():
    global gb_swarmNode_config
    logger.debug( '\nHandling Disconnection:\n'  )
    return
    try:
        exit_commands = [
            'ifconfig veth1 0.0.0.0',
            'nikss-ctl del-port pipe 0 dev veth0',
            f"nikss-ctl del-port pipe 0 dev vxlan{gb_swarmNode_config[STRs.VXLAN_ID]}",
            'nikss-ctl table delete pipe 0 ingress_route',
            'nikss-ctl pipeline unload id 0 ',
            f"ip link delete vxlan{gb_swarmNode_config[STRs.VXLAN_ID]}"
        ]
        for command in exit_commands:
            res = subprocess.run( command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if (res.stderr):
                logger.error(f'Error running command: {command}\n\tError Message:{res.stderr}')
        logger.debug( '\nDone Handling Disconnection:\n'  )
    except Exception as e:
        print(e)    

def monitor_wifi_status(): 
    last_bssid = ''
    current_bssid = ''
    last_connection_timestamp = 0
    wait_time_before_requesting_new_config = 5
    # this command is run in the shell to monitor wireless events using the iw tool
    monitoring_command = f"nmcli device monitor {DEFAULT_IFNAME}"
    # python runs the shell command and monitors the output in the terminal
    process = subprocess.Popen( monitoring_command.split() , stdout=subprocess.PIPE, text = True)
    previous_line = ''
    # we iterate over the output lines to read the event and react accordingly
    for output_line in iter(lambda: process.stdout.readlines(), ""):
        if (output_line.strip() == previous_line.strip()):
            continue
        previous_line = output_line
        output_line_as_word_array = output_line.split()
        # logger.debug( '\noutput_line: ' + output_line )
        if output_line_as_word_array[1] == 'disconnected':
            logger.debug('Disconnected from WiFi')
            handle_leave_event()
            # handle_disconnection()
        elif (output_line_as_word_array[1] == 'connected'):
            current_connection_timestamp = time.time()
            connection_time_delta = current_connection_timestamp - last_connection_timestamp
            shell_command = 'iwgetid -r -a'
            # python runs the shell command and monitors the output in the terminal
            process = subprocess.run( shell_command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            current_bssid = process.stdout
            if (connection_time_delta < wait_time_before_requesting_new_config) and (current_bssid == last_bssid):
                continue
            last_bssid = current_bssid
            shell_command = 'iwgetid -r'
            # python runs the shell command and monitors the output in the terminal
            process = subprocess.run( shell_command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.debug(f'Connected to {process.stdout}')

            


def main():
    print('program started')
    t1 = threading.Thread(target=handle_communication, args=() )
    t2 = threading.Thread(target= monitor_wifi_status, args=())
    # t3 = threading.Thread(target= handle_user_input, args=())
    t1.start()
    t2.start()
    # t3.start()




if __name__ == '__main__':
    atexit.register(exit_handler)
    main()
