#!.venv/bin/python
import os, sys
import lib.helper_functions as utils
import lib.global_config as cfg
from argparse import ArgumentParser
import logging
import psutil
import subprocess
import ipaddress
import time

SELF_UUID_NUM = cfg.SELF_UUID
SELF_TYPE = None
SELF_UUID_STR = None

WLAN_IF = utils.get_interfaces()["wifi"]
ETH_IF = utils.get_interfaces()["ethernet"]

logger = None

def is_venv():
    return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

def interface_exists(if_name):
    return if_name in psutil.net_if_addrs()

def running_in_screen():
    try:
        p = psutil.Process()
        while p:
            if "screen" in p.name().lower():
                return True
            p = p.parent()
        return False
    except Exception:
        return False

def init_hotspot():
    # wifi_mac = utils.int_to_mac( SELF_UUID_NUM )
    # subprocess.run( f"sudo ip link set dev {WLAN_IF} address {wifi_mac}".split())
    ret = subprocess.run("nmcli connection show SmartEdgeHotspot".split(), capture_output=True, text=True)
    if ret.returncode != 0:
        print("SmartEdgeHotspot Not found, Creating it")
        commands = [
                f"nmcli con add type wifi ifname {WLAN_IF} con-name SmartEdgeHotspot autoconnect yes ssid SE_NETWORK",
                "nmcli con modify SmartEdgeHotspot 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared",
                "nmcli con modify SmartEdgeHotspot wifi-sec.key-mgmt wpa-psk",
                "nmcli con modify SmartEdgeHotspot wifi-sec.psk 123456123",
                "nmcli con up SmartEdgeHotspot"
                ]
        for command in commands:
            subprocess.run(command.split())
    else:
        subprocess.run("nmcli con up SmartEdgeHotspot".split())

def init_colocated(co_uuid):
    co_vip_s0 = "10.0.255.254"
    co_vip_s1 = "10.1.255.254"
    ap_vip_s1 = "10.1.255.240"
    ap_ip_p2p = "192.168.254.253/30"
    ap_mac = utils.int_to_mac(int(ipaddress.ip_address(ap_vip_s1)) )
    co_mac = utils.int_to_mac(int(ipaddress.ip_address(co_vip_s1)) )
    commands = ["ip link add vet2ap type veth peer name vet2co",
                "ip netns add sens",
                # f"ip link set {WLAN_IF} netns sens",
                # f"ip netns exec sens ip link set {WLAN_IF} up",
                "ip link set vet2ap netns sens",
                "ip netns exec sens ip addr flush vet2ap",
                f"ip netns exec sens ip addr add {co_vip_s0}/16 dev vet2ap",
                f"ip netns exec sens ip addr add {co_vip_s1}/16 dev vet2ap",
                f"ip netns exec sens ip link set vet2ap address {co_mac}",
                "ip netns exec sens ip link set vet2ap up",
                "ip netns exec sens ethtool --offload vet2ap rx off tx off",
                "ip addr flush vet2co",
                f"ip link set vet2co address {ap_mac}",
                f"ip addr add {ap_vip_s1}/16 dev vet2co",
                "ip link set vet2co up",
                "ethtool --offload vet2co rx off tx off",
                # "ip netns exec sens ip route add default dev vet2ap",
                "ip netns exec sens screen -X -S SE_CO quit",
                f"ip netns exec sens screen -dmS SE_CO ./run.py -t CO --uuid-self {co_uuid} --no-discovery "]
    for command in commands:
        subprocess.run(command.split())        

def init_backbone():       
    if not interface_exists(cfg.default_backbone_device):
        print(f"Interface {cfg.default_backbone_device} does not exists, trying to create it")
        backbone_ip = ipaddress.ip_address(cfg.backbone_subnet) + SELF_UUID_NUM
        backbone_mac = utils.int_to_mac( int( ipaddress.ip_address(backbone_ip)) )
        commands = [
            f"ip link add smartedge-bb type vxlan id 1000 group 239.1.1.1 dstport 0 dev {ETH_IF}",
            f"sudo ip link set dev smartedge-bb address {backbone_mac}",
            f"sudo ip address add {backbone_ip}{cfg.backbone_subnetmask} dev smartedge-bb",
            "ip link set dev smartedge-bb up"
            ]
        for command in commands:
            subprocess.run(command.split())
            
            
def init_wlan():
    ret = subprocess.run(f"cat /sys/class/net/{WLAN_IF}/address".split(), capture_output=True, text=True)
    if ret.returncode !=0:
        print("Error Reading MAC form WLAN interface")
        exit()
    else: 
        current_wlan_mac = ret.stdout
        calculated_wlan_mac = utils.int_to_mac( SELF_UUID_NUM )
        if calculated_wlan_mac != current_wlan_mac:
            commands = [f"ip link set {WLAN_IF} down", 
                        f"ip link set {WLAN_IF} address {calculated_wlan_mac}",
                        f"ip link set {WLAN_IF} up"]
            for command in commands:
                subprocess.run(command.split())
                

def init_logger(level):
    global logger
    logger = logging.getLogger()
    formatter = logging.Formatter(
        fmt=f"[{SELF_UUID_STR}] %(asctime)s [%(levelname)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)
    logger.setLevel(level)


def get_arguments():
    parser = ArgumentParser()
    parser.add_argument(
        "-t", 
        "--type",
        type=str.upper, 
        required=True,
        choices=['AP', 'SN', 'CO', 'AC'],
        help=""""type of the current node; must be one of:
        AP, SN, CO, AC (case-insensitive)""")
    parser.add_argument(
        "-l", 
        "--log-level",
        type=int, 
        required=False,
        default=10,
        choices=[10, 20, 30, 40, 50],
        help=""""Logging Level""")
    
    parser.add_argument( 
        "--uuid-self",
        type=int, 
        required=False,
        default=None,
        help=""""Node UUID""")

    parser.add_argument( 
        "--uuid-ap",
        type=int, 
        required=False,
        default=None,
        help=""""AP UUID""")
    
    parser.add_argument( 
        "--uuid-co",
        type=int, 
        required=False,
        default=None,
        help=""""CO UUID""")
    
    parser.add_argument(
        "-f", 
        "--force-run",
        action="store_true",
        required=False,
        help=""""Force script to run ignoring minor checks""")

    parser.add_argument( 
        "--no-discovery",
        action="store_true",
        required=False,
        help=""""Do not use auto discovery""")

    
    args = parser.parse_args()
    return args

def main():
    global SELF_UUID_STR, SELF_UUID_NUM
    # Check if script is running with root privilige
    if os.geteuid() != 0:
        print("\n ***ERROR: This script must be run with sudo or as root.")
        sys.exit(1)
    if is_venv():
        print("Running Inside virtual environment")
    else:
        print("\n ***ERROR: script must be using python from virtual environment .venv")
        exit()
    
    args = get_arguments()
    if not args.force_run:
        if running_in_screen():
            print("Running inside a screen session")
        else:
            print("\n ***ERROR: Script must running inside a screen session, to override this check supply argument -f on next run of the script")
            exit()

    if args.uuid_self:
        SELF_UUID_NUM = args.uuid_self
        
    SELF_UUID_STR = f"{args.type.upper()}{SELF_UUID_NUM:02d}"
    init_logger(args.log_level)
    logger.info(f"-- Starting as: {args.type.upper()}")
    match args.type.upper():
        case 'AP':
            # init_backbone()
            init_hotspot()
            import ap_manager.ap_manager as AP
            AP.run(SELF_UUID_STR, args.no_discovery)
            pass
        case 'SN':
            import node_manager.node_manager as SN
            init_wlan()
            SN.run(SELF_UUID_STR)
            pass
        case 'CO':
            # init_backbone()
            import coordinator.coordinator as CO
            CO.run(SELF_UUID_STR, args.no_discovery)
            pass
        case 'AC':
            if not ( args.uuid_ap and args.uuid_co):
                print("must supply args: --uuid-ap and --uuid-co")
                exit()
            AP_UUID_STR = f"AP{args.uuid_ap:02d}"
            init_colocated(co_uuid = args.uuid_ap)
            init_hotspot()
            import ap_manager.ap_manager as AP
            AP.run(AP_UUID_STR, no_discovery = True )
        
    exit()

if __name__ == '__main__':
    main()
    


