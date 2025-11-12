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

# from argparse import ArgumentParser
# parser = ArgumentParser()
# parser.add_argument("-l", "--log-level", type=int, default=50,
#                     help="set logging level [10, 20, 30, 40, 50]")
# args = parser.parse_args()

# PROGRAM_LOG_FILE_NAME = './logs/program.log'
# os.makedirs(os.path.dirname(PROGRAM_LOG_FILE_NAME), exist_ok=True)

logger = logging.getLogger(__name__)

# log_formatter = logging.Formatter(
#     "Line:%(lineno)d at %(asctime)s [%(levelname)s] Thread: %(threadName)s File: %(filename)s :\n%(message)s\n")
# log_console_handler = logging.StreamHandler(sys.stdout)
# log_console_handler.setFormatter(log_formatter)
# logger.setLevel(args.log_level)
# logger.addHandler(log_console_handler)

DEFAULT_IFNAME = utils.get_interfaces()["wifi"]
NODE_TYPE = 'SN'
SELF_UUID = "null"



ACCESS_POINT_IP = ''
q_to_coordinator = queue.Queue()
q_to_mgr = queue.Queue()

gb_swarmNode_config = {}

last_request_id = 0

# --- Heartbeat service management ---
hb_process = None

import os

def start_heartbeat_service(client_id: str, coord_ip: str,
                            pubkey_port: int = 5007,
                            hb_port: int = 5008,
                            interval: float = 1.0):
    """
    Launch the heartbeat_client.py process with proper arguments.
    """
    global hb_process
    if hb_process and hb_process.poll() is None:
        logger.debug("[HB] Heartbeat already running.")
        return
    try:
        # ✅ Resolve path relative to project root (cwd = smartedge/)
        hb_client_path = os.path.join(os.getcwd(), "node_manager", "heartbeat", "heartbeat_client.py")

        if not os.path.exists(hb_client_path):
            logger.error(f"[HB] heartbeat_client.py not found at {hb_client_path}")
            return

        cmd = [
            "python3", hb_client_path,
            "--client-id", client_id,
            "--receiver-ip", coord_ip,
            "--receiver-port", str(hb_port),
            "--pubkey-port", str(pubkey_port),
            "--interval", str(interval),
        ]
        hb_process = subprocess.Popen(cmd)
        logger.info(f"[HB] Heartbeat service started with command: {' '.join(cmd)}")
    except Exception as e:
        logger.error(f"[HB] Failed to start heartbeat: {e}")




def stop_heartbeat_service_if_running():
    global hb_process
    if hb_process and hb_process.poll() is None:
        try:
            hb_process.terminate()
            hb_process.wait(timeout=5)
            logger.info("[HB] Heartbeat service stopped.")
        except Exception as e:
            logger.error(f"[HB] Failed to stop heartbeat: {e}")
    hb_process = None


def handle_successful_join(config_data: dict, ap_address: tuple, client_id: str = None):
    if client_id is None:
        client_id = SELF_UUID

    veth1_ip = config_data.get(STRs.VETH1_VIP.name) or config_data.get("VETH1_VIP")
    if not veth1_ip:
        logger.warning("[HB] SET_CONFIG missing VETH1_VIP; aborting join.")
        return

    logger.info(f"[Join] Node {client_id} successfully joined swarm via {ap_address[0]} "
                f"with VETH1_VIP {veth1_ip}")

def get_ip_from_arp_by_physical_mac(physical_mac):
    shell_command = "arp -en"
    proc = subprocess.run(shell_command.split(), text=True, stdout=subprocess.PIPE)
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

def set_keepalive_linux(sock, after_idle_sec=1, interval_sec=3, max_fails=5):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, after_idle_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, max_fails)

PING_IN_PROGRESS = False

def handle_communication():
    global last_request_id, gb_swarmNode_config, ACCESS_POINT_IP
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as node_manager_socket:
        try:
            set_keepalive_linux(sock=node_manager_socket,
                                after_idle_sec=1, interval_sec=3, max_fails=5)
            node_manager_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            node_manager_socket.bind(('0.0.0.0', cfg.node_manager_tcp_port))
            logger.debug(f'Node Manager Listening on port {cfg.node_manager_tcp_port} ...')
        except Exception as e:
            logger.error(f'Exception in Node Manager Socket: {e}')
        iter = 0
        while True:
            iter += 1
            print(f'Node Manager waiting for instruction, iteration {iter}')
            node_manager_socket.listen()
            remote_socket, ap_address = node_manager_socket.accept()
            ACCESS_POINT_IP = ap_address[0]
            if not PING_IN_PROGRESS:
                ping_command = f'ping {ACCESS_POINT_IP}'
                subprocess.Popen(ping_command.split(), stdout=subprocess.PIPE)
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

                    # ✅ Heartbeat handling directly here
                    hb_enabled = bool(config_data.get("heartbeat", False))
                    if hb_enabled:
                        ap_ip = config_data.get("AP_SWARM_IP") or config_data.get("HB_DST_IP") or ap_address[0]
                        coord_ip = ap_ip.replace("10.0.", "10.1.") if ap_ip.startswith("10.0.") else ap_ip
                        logger.info(f"[HB] Heartbeat ENABLED by Coordinator. Using coord_ip={coord_ip}")
                        start_heartbeat_service(
                            client_id=SELF_UUID,
                            coord_ip=coord_ip,
                            pubkey_port=5007,
                            hb_port=5008,
                            interval=1.0
                        )
                    else:
                        logger.info("[HB] Heartbeat DISABLED by Coordinator.")
                        stop_heartbeat_service_if_running()

                    handle_successful_join(config_data, ap_address, client_id=SELF_UUID)
                except Exception as e:
                    logger.error(repr(e))
                    return

            elif config_data[STRs.TYPE.name] == 'go_away':
                print('Leaving Swarm')
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

                # ✅ Stop heartbeat when leaving
                stop_heartbeat_service_if_running()
                pass

            remote_socket.sendall(bytes("OK!".encode()))
            remote_socket.close()


def install_config_no_update_vxlan(config_data):
    swarm_veth1_vip = config_data[STRs.VETH1_VIP.name]
    swarm_veth1_vmac = config_data[STRs.VETH1_VMAC.name]

    logger.info(f"[VXLAN-CONFIG] Installing config without VXLAN update")
    logger.info(f"[VXLAN-CONFIG] Using existing se_vxlan interface to AP={ACCESS_POINT_IP}")

    commands = [
        f'ip link set veth1 address {swarm_veth1_vmac}',
        f'ifconfig veth1 {swarm_veth1_vip} netmask 255.255.0.0 up',
        f'ip link set veth0 up',
        f'ip link set dev veth1 mtu 1400',
        f'ethtool --offload veth1 rx off tx off'
    ]
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command, text=True, shell=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process_ret.stderr:
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")

    logger.info(f"[VXLAN-CONFIG] VETH1 configured: IP={swarm_veth1_vip}, MAC={swarm_veth1_vmac}, "
                f"MTU=1400, default route via veth1")


def install_swarmNode_config(swarmNode_config):
    global last_request_id, gb_swarmNode_config, ACCESS_POINT_IP

    vxlan_id = swarmNode_config[STRs.VXLAN_ID.name]
    swarm_veth1_vip = swarmNode_config[STRs.VETH1_VIP.name]
    swarm_veth1_vmac = swarmNode_config[STRs.VETH1_VMAC.name]

    logger.info(f"[VXLAN-CONFIG] Creating new VXLAN tunnel")
    logger.info(f"[VXLAN-CONFIG] VXLAN-ID={vxlan_id}, LocalDev={DEFAULT_IFNAME}, "
                f"RemoteAP={ACCESS_POINT_IP}, UDP-DstPort=4789")

    commands = [
        'ip link del se_vxlan',
        'ip link del veth1',
        f'ip link add se_vxlan type vxlan id {vxlan_id} dev {DEFAULT_IFNAME} remote {ACCESS_POINT_IP} dstport 4789',
        'ip link set dev se_vxlan up',
        'ip link add veth0 type veth peer name veth1',
        f'ip link set veth1 address {swarm_veth1_vmac}',
        f'ifconfig veth1 {swarm_veth1_vip} netmask 255.255.0.0 up',
        f'ip link set veth0 up',
        f'ip link set dev veth1 mtu 1400',
        f'ethtool --offload veth1 rx off tx off'
    ]
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command, text=True, shell=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process_ret.stderr:
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")

    # Retrieve link indices for P4 pipeline
    get_if1_index_command = 'cat /sys/class/net/veth0/ifindex'
    get_if2_index_command = 'cat /sys/class/net/se_vxlan/ifindex'
    if1_index = subprocess.run(get_if1_index_command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if2_index = subprocess.run(get_if2_index_command.split(), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    logger.info(f"[VXLAN-CONFIG] Interface indices: veth0={if1_index.stdout.strip()}, se_vxlan={if2_index.stdout.strip()}")
    logger.info(f"[VXLAN-CONFIG] Packets will traverse: veth0 <-> se_vxlan tunnel <-> AP {ACCESS_POINT_IP}")

    commands = [
        'nikss-ctl pipeline unload id 0',
        'nikss-ctl pipeline load id 0 ./node_manager/utils/nikss.o',
        'nikss-ctl add-port pipe 0 dev veth0',
        'nikss-ctl add-port pipe 0 dev se_vxlan',
        f'nikss-ctl table add pipe 0 ingress_route action id 2 key {if1_index.stdout.strip()} data {if2_index.stdout.strip()}',
        f'nikss-ctl table add pipe 0 ingress_route action id 2 key {if2_index.stdout.strip()} data {if1_index.stdout.strip()}'
    ]
    for command in commands:
        logger.debug('executing: ' + command)
        process_ret = subprocess.run(command.split(), text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process_ret.stderr:
            logger.error(f"Error executing command {command}: \n{process_ret.stderr}")
        else:
            logger.debug(f'executed command {command} and got output: {process_ret.stdout}')

    logger.info(f"[VXLAN-CONFIG] Swarm Node config complete: "
                f"VETH1={swarm_veth1_vip}/{swarm_veth1_vmac}, "
                f"VXLAN Tunnel remote {ACCESS_POINT_IP} (id={vxlan_id})")



def exit_handler():
    logger.info('Handling exit')
    try:
        # ✅ Ensure heartbeat stopped on exit
        stop_heartbeat_service_if_running()
    except Exception as e:
        logger.error(f"Failed to stop heartbeat in exit_handler: {e}")

    try:
        handle_disconnection()
    except Exception as e:
        logger.error(f"Error during disconnection cleanup: {e}")

def handle_disconnection():
    global gb_swarmNode_config
    logger.debug('\nHandling Disconnection:\n')
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
            res = subprocess.run(command.split(), text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.stderr:
                logger.error(f'Error running command: {command}\n\tError Message:{res.stderr}')
        logger.debug('\nDone Handling Disconnection:\n')
    except Exception as e:
        print(e)

def monitor_wifi_status():
    last_bssid = ''
    current_bssid = ''
    last_connection_timestamp = 0
    wait_time_before_requesting_new_config = 5
    monitoring_command = f"nmcli device monitor {DEFAULT_IFNAME}"
    process = subprocess.Popen(monitoring_command.split(), stdout=subprocess.PIPE, text=True)
    previous_line = ''
    for output_line in iter(lambda: process.stdout.readlines(), ""):
        if (output_line.strip() == previous_line.strip()):
            continue
        previous_line = output_line
        output_line_as_word_array = output_line.split()
        if output_line_as_word_array[1] == 'disconnected':
            logger.debug('Disconnected from WiFi')
            stop_heartbeat_service_if_running()
        elif (output_line_as_word_array[1] == 'connected'):
            current_connection_timestamp = time.time()
            connection_time_delta = current_connection_timestamp - last_connection_timestamp
            shell_command = 'iwgetid -r -a'
            process = subprocess.run(shell_command.split(), text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            current_bssid = process.stdout
            if (connection_time_delta < wait_time_before_requesting_new_config) and (current_bssid == last_bssid):
                continue
            last_bssid = current_bssid
            shell_command = 'iwgetid -r'
            process = subprocess.run(shell_command.split(), text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logger.debug(f'Connected to {process.stdout}')

def main():
    print('program started')
    t1 = threading.Thread(target=handle_communication, args=())
    t2 = threading.Thread(target=monitor_wifi_status, args=())
    t1.start()
    t2.start()
    
def run(uuid):
    global SELF_UUID
    
    SELF_UUID = uuid
    
    logger.info(f"--- {SELF_UUID} Starting ...")
    t1 = threading.Thread(target=handle_communication, args=())
    t2 = threading.Thread(target=monitor_wifi_status, args=())
    t1.start()
    t2.start()


if __name__ == '__main__':
    atexit.register(exit_handler)
    main()
