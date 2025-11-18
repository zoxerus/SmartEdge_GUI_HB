import sys
# setting path
sys.path.append('.')
sys.path.append('..')
sys.path.append('../..')
sys.path.append('./lib/bmv2_pylibs')

import subprocess
import re
import os
import lib.global_config as cfg
import io 

from lib.bmv2_pylibs import *
from lib.bmv2_pylibs.sswitch_CLI import runtime_CLI, SimpleSwitchAPI
from contextlib import redirect_stdout 
from thrift.transport.TTransport import TTransportException
from lib.performance_monitor import measure_performance
from lib.logger_utils import get_logger
import logging

logger_console = logging.getLogger() #get_logger("coordinator", "Console")
logger_metric = logging.getLogger() #get_logger("Coordinator", "Metric")

#logger = None
SWITCH_RESPONSE_ERROR = -1
SWITCH_RESPONSE_INVALID = -2
SWITCH_RESPONSE_LAST_LINE_INDEX = -2
P4_CONTROL_METHOD_THRIFT_CLI = 'THRIFT_CLI'
P4_CONTROL_METHOD_P4RT_GRPC = 'P4RT_GRPC'

BMV2_DOCKER_CONTAINER_NAME = 'bmv2smartedge'



DEFAULT_THRIFT_PORT = 9090


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


def connect_to_switch(address):
    switch_cli_instance = None
    try:                
        # args = runtime_CLI.get_parser().parse_args()
        pre = runtime_CLI.PreType.SimplePreLAG
        services = runtime_CLI.RuntimeAPI.get_thrift_services(pre)
        services.extend(SimpleSwitchAPI.get_thrift_services())
        
        standard_client, mc_client, sswitch_client = runtime_CLI.thrift_connect(
        address, 9090, services)
        
        runtime_CLI.load_json_config(standard_client) #   , args.json)
        
        cli_instance = SimpleSwitchAPI(pre, standard_client, mc_client, sswitch_client)
        
        switch_cli_instance = cli_instance
        
        logger_console.debug(f"thrift connected to  {address}")
        
    except Exception as e:
        logger_console.warning(e)
        
    return switch_cli_instance


output_capture = io.StringIO()
@measure_performance("Coordinator", logger_metric) 
def run_cli_command(command, instance):
    logger_console.debug(f'sending command to bmv2: \n{command}')
    command_output = ""
    with redirect_stdout(output_capture):
        try:
            instance.onecmd(command)
        except:
            logger_console.warning(f'Error running command: {command}')
            return ''
    command_output = output_capture.getvalue()
    output_capture.truncate(0)
    logger_console.debug(f"response from switch: {command_output}")
    return command_output


@measure_performance("Coordinator", logger_metric) 
def send_cli_command_to_bmv2(cli_command, instance, thrift_ip='0.0.0.0', thrift_port=DEFAULT_THRIFT_PORT ):
    return run_cli_command(command=cli_command, instance=instance)
    command_as_word_array = ['docker','exec',BMV2_DOCKER_CONTAINER_NAME,'sh', '-c',
                             f"echo \'{cli_command}\' | simple_switch_CLI --thrift-ip {args.thrift_ip} --thrift-port {args.thrift_port}"  ]

    proc = subprocess.run(command_as_word_array, text=True, stdout=subprocess.PIPE , stderr=subprocess.PIPE)
    if (proc.stderr):
        logger_console.error(f'\nBMV2ERROR:\nsending command:\n{cli_command}\nERROR MESSAGE:\n{proc.stderr}')
    response = proc.stdout.strip()

    logger_console.debug(f'Sent command "{cli_command}" to bmv2\nResponse Received:\n{response}')
    return response
    

# this updates the list of broadcast ports in bmv2
@measure_performance("Coordinator", logger_metric) 
def add_bmv2_swarm_broadcast_port(switch_port, instance, thrift_ip='0.0.0.0', thrift_port=DEFAULT_THRIFT_PORT):
        res = send_cli_command_to_bmv2(cli_command='mc_dump', instance=instance, thrift_ip=thrift_ip, thrift_port=thrift_port)
        res_lines = res.splitlines()
        i = 0        
        for line in res_lines:
            if 'mgrp(' in line:
                port_list = set(extract_numbers([ res_lines[i+1].split('ports=[')[1].split(']')[0] ]))
                port_list.add(switch_port)
                broadcast_ports =  ' '.join( str(port) for port in port_list)
                send_cli_command_to_bmv2(cli_command=f"mc_node_update 0 {broadcast_ports} ", thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance )  
            i = i + 1

@measure_performance("Coordinator", logger_metric) 
def remove_bmv2_swarm_broadcast_port(switch_port, instance, thrift_ip='0.0.0.0', thrift_port=DEFAULT_THRIFT_PORT):
        res = send_cli_command_to_bmv2(cli_command='mc_dump', thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
        res_lines = res.splitlines()
        i = 0
        for line in res_lines:
            if 'mgrp(' in line:
                port_list = set(extract_numbers([ res_lines[i+1].split('ports=[')[1].split(']')[0] ]))
                if (switch_port in port_list):
                    port_list.remove(switch_port)
                    broadcast_ports =  ' '.join( str(port) for port in port_list)
                    send_cli_command_to_bmv2(cli_command=f"mc_node_update 0 {broadcast_ports} ", thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance )  
            else:
                logger_console.debug(f'Port {switch_port} is not in swarm boradcast ports')
            i = i + 1

@measure_performance("Coordinator", logger_metric) 
def add_entry_to_bmv2(communication_protocol, instance, table_name, action_name, match_keys, action_params, thrift_ip = '0.0.0.0', thrift_port = DEFAULT_THRIFT_PORT):
    if communication_protocol == P4_CONTROL_METHOD_THRIFT_CLI:
        cli_command = f'table_dump_entry_from_key {table_name} {match_keys}'
        response = send_cli_command_to_bmv2(cli_command=cli_command, thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
        # print(f'Sent command: {cli_command} \nresponse: {response}')
        if 'Invalid table operation (BAD_MATCH_KEY)' in response: # entry doesn't exist
            cli_command = "table_add " + table_name + ' ' + action_name + ' ' + match_keys + ' => ' + action_params
            response = send_cli_command_to_bmv2(cli_command=cli_command, thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
            # bmv2_logger.debug('\nresponse received: ' + response )
            response_as_lines = response.splitlines()
            for line in response_as_lines:
                if ( 'Error' in line ):
                    logger_console.error( f'P4 Command Error:\n {cli_command} \nResponse Obtained: {response} ')
                    return SWITCH_RESPONSE_ERROR
                elif 'Invalid' in line:
                    logger_console.error( f'P4 Command Invalid:\n {cli_command} \nResponse Obtained: {response} ')
                    return SWITCH_RESPONSE_INVALID
                elif line.startswith("Entry has been added with handle"):
                    handle =  re.findall(r'\b\d+\b', line, re.I)[0]
                    logger_console.debug(f"Added entry with handle {handle} detected from line: {line} ")
                    return handle
        else:
            for line in response.splitlines():
                if 'Dumping entry' in line:
                    entry_handle = int( re.findall(r'0x[0-9A-F]+', line, re.I)[0] , 16  )
                    logger_console.debug(f'entry_handle exists: {entry_handle}')
                    cli_command = f'table_modify {table_name} {action_name} {entry_handle} {action_params}'
                    send_cli_command_to_bmv2(cli_command=cli_command,  thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
                    break
            
             

@measure_performance("Coordinator", logger_metric) 
def get_entry_handle(table_name, instance, key, thrift_ip = '0.0.0.0', thrift_port = DEFAULT_THRIFT_PORT):
    command = f'table_dump_entry_from_key {table_name} {key}'
    response = send_cli_command_to_bmv2(cli_command=command, thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
    logger_console.debug(f'Getting entry handle from bmv2 for: {key}\n {response}')
    for line in response.splitlines():
        if 'Dumping entry' in line:
            handle = int( re.findall(r'0x[0-9A-F]+', line, re.I)[0] , 16 )
            logger_console.debug(f'Found handle for key: {key} is: {handle}')
            return handle
    logger_console.debug(f'Could not find entry handle for key: {key}')
    return None

@measure_performance("Coordinator", logger_metric) 
def delete_forwarding_entry_from_bmv2(
    communication_protocol, instance, table_name, key, thrift_ip = '0.0.0.0', thrift_port = DEFAULT_THRIFT_PORT):
    if communication_protocol == P4_CONTROL_METHOD_THRIFT_CLI:
        handle = get_entry_handle(table_name=table_name, key=key, thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
        if handle != None:
            cli_command = f'table_delete {table_name} {handle}'
            send_cli_command_to_bmv2(cli_command=cli_command, thrift_ip=thrift_ip, thrift_port=thrift_port, instance=instance)
            return
        logger_console.debug(f'Entry Handle is None for table: {table_name}, and key: {key}')
