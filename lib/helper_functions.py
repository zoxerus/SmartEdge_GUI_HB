import json
import re
import psutil
import socket 
import ipaddress
import netifaces
import logging

logger = logging.getLogger(__name__)

def get_interfaces():
    """
    Detects the default ethernet and Wi-Fi interfaces.

    Returns:
        dict: A dictionary with 'ethernet' and 'wifi' keys.
              Values are the interface names (str) or None if not found.
    """
    interfaces = {'ethernet': None, 'wifi': None}
    
    try:
        # Find default ethernet interface via the default gateway
        interfaces['ethernet'] = netifaces.gateways()['default'][netifaces.AF_INET][1]
        logger.debug(f"Found default interface {interfaces['ethernet']}")
    except (KeyError, IndexError):
        logger.warning("Could not determine default ethernet interface.")
    except Exception as e:
        logger.warning(f"An unexpected error occurred while detecting ethernet interface: {e}")

    try:
        # Find a Wi-Fi interface by checking for common prefixes
        all_interfaces = psutil.net_if_addrs().keys()
        # Note: This detection is not foolproof and might not work on all systems.
        # Common prefixes for Wi-Fi interfaces are 'wl', 'wlp'.
        wifi_interfaces = [iface for iface in all_interfaces if iface.startswith(('wl'))]
        if wifi_interfaces:
            interfaces['wifi'] = wifi_interfaces[0] # Return the first one found
            logger.debug(f"Found wifi interface {interfaces['wifi']}")
    except Exception as e:
        logger.warning(f"An error occurred while detecting Wi-Fi interface: {e}")
        
    return interfaces



def get_default_iface_name_linux():
    route = "/proc/net/route"
    with open(route) as f:
        for line in f.readlines():
            try:
                iface, dest, _, flags, _, _, _, _, _, _, _, = line.strip().split()
                if dest != '00000000' or not int(flags, 16) & 2:
                    continue
                return iface  # This is the default interface name (e.g., 'eth0', 'enp3s0')
            except:
                continue

def get_interface_ip(interface_name):
    """
    Gets the IPv4 address of a specified network interface.

    Args:
        interface_name (str): The name of the network interface (e.g., 'eth0', 'en0', 'Wi-Fi').

    Returns:
        str: The IPv4 address of the interface, or None if not found.
    """
    try:
        # Get all addresses for the specified interface
        addresses = netifaces.ifaddresses(interface_name)
        # Check if AF_INET (IPv4) addresses exist for this interface
        if netifaces.AF_INET in addresses:
            # Return the first IPv4 address found
            # addresses[netifaces.AF_INET] is a list of dicts, each dict has an 'addr' key
            return addresses[netifaces.AF_INET][0]['addr']
        else:
            print(f"No IPv4 address found for interface {interface_name}.")
            return None
    except ValueError:
        print(f"Interface {interface_name} not found or is invalid.")
        return None
    except KeyError:
        print(f"No 'addr' key found for IPv4 address on interface {interface_name}.")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def auto_gen_uuid(node_type):
    iface = get_default_iface_name_linux()
    ip = get_interface_ip(iface)
    octect4 = int(ip.split('.')[3])
    formatted_number = "{:03d}".format(octect4)
    return f"{node_type}{formatted_number}"

def generate_uuid_from_lo(loopback_if, node_type):
    THIS_UUID = None
    lo0_ip = get_interface_ip(loopback_if)
    if lo0_ip == None:
        raise ValueError("Error Generating UUID, lo:0 IP problem")
    lo0_ip = ipaddress.ip_address(lo0_ip)
    temp_mac = int_to_mac(int(lo0_ip))
    THIS_UUID = f'{node_type}:{temp_mac[9:]}'.replace(':','')
    return THIS_UUID

def enum_dictionary_to_json_string(dic_obj):
    return json.dumps({key.value: value for key, value in dic_obj.items()})


def int_to_mac(macint):
    if type(macint) != int:
        raise ValueError('invalid integer')
    return ':'.join(['{}{}'.format(a, b)
                     for a, b
                     in zip(*[iter('{:012x}'.format(macint ))]*2)])  # + 2199023255552
    
    

def assign_virtual_mac_and_ip_by_host_id( subnet, host_id):
    station_virtual_ip_address = str( subnet + host_id )
    station_virtual_mac_address = int_to_mac(int( subnet + host_id ))
       
    return station_virtual_mac_address, station_virtual_ip_address


def extract_numbers(lst):
    """
    Extracts numbers from a list of strings using regular expressions.
    """
    # Compile a regular expression pattern to match digits
    pattern = re.compile(r'\d+')
     
    # Use the pattern to extract all digits from each string in the list
    extracted_numbers = [pattern.findall(s) for s in lst]
     
    # Convert the extracted numbers from strings to integers
    return [int(x) for sublist in extracted_numbers for x in sublist]