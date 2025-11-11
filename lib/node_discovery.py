import time
import threading
import json
import socket
import lib.bmv2_thrift_lib as bmv2

# Configuration
PORT = 5000  # Port to listen on
DISCOVERY_INTERVAL = 5  # Seconds between discovery messages

class Node:
    def __init__(self, node_type: str, node_uuid: str, node_sebackbone_ip: str, group_id: str):
        self.node_name = socket.gethostname()
        self.node_type = node_type
        self.uuid = node_uuid
        self.group_id = group_id
        self.node_sebackbone_ip = node_sebackbone_ip
        self.known_aps = {}
        self.known_coordinators = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('', PORT))
        self.lock = threading.Lock()  # To protect shared resources
    
    def get_aps_dict(self):
        ap_dict = {}
        with self.lock:
            ap_dict = self.known_aps
        return ap_dict

    def get_ip(self):
        """Get the IP address of the current device."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't need to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP


    def listen(self):
        """Listen for incoming messages."""
        while True:
            try:
                data, addr = self.sock.recvfrom(1024)
                message = json.loads(data.decode('utf-8'))
                if message['group_id'] == self.group_id:
                    type = message['type']
                    uuid = message['uuid']
                    node_name = message['name']
                    node_ip = message['address']
                    node_sebackbone_ip = message['sebackbone_ip']
                    if type == 'AP' and uuid not in self.known_aps:    
                        switch = {  'name': node_name, 
                                    'type': type, 
                                    'address': node_ip,
                                    'sebackbone_ip': node_sebackbone_ip
                                    }
                        cli_instance = bmv2.connect_to_switch(node_ip)
                        if cli_instance == None: 
                            continue
                        switch['cli_instance'] = cli_instance
                        with self.lock:
                            self.known_aps[uuid] =  switch
                            print(f"Discovered {type}: {uuid} at {node_ip}")
                                
                    elif type == 'CO' and uuid not in self.known_coordinators:
                        with self.lock:
                            self.known_coordinators[uuid] = { 
                                                         'name': node_name, 
                                                         'type': type, 
                                                         'address': node_ip,
                                                         'sebackbone_ip': node_sebackbone_ip
                                                    }
                            print(f"Discovered {type}: {uuid} at {node_ip}")
                        
            except Exception as e:
                print(f"Error receiving data: {e}")

    def announce(self):
        """Announce presence periodically."""
        while True:
            message = {
                'group_id': self.group_id,
                'type': self.node_type,
                'uuid': self.uuid,
                'sebackbone_ip': self.node_sebackbone_ip,
                'name': self.node_name,
                'address': self.get_ip()
            }
            message_json = json.dumps(message)
            try:
                # Broadcast to all devices on the network
                self.sock.sendto(message_json.encode('utf-8'), ('<broadcast>', PORT))
            except Exception as e:
                print(f"Error sending data: {e}")
            time.sleep(DISCOVERY_INTERVAL)

    def start(self):
        """Start the node."""
        # Enable broadcasting
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Start listening thread
        listen_thread = threading.Thread(target=self.listen, daemon=True)
        listen_thread.start()

        # Start announcing thread
        announce_thread = threading.Thread(target=self.announce, daemon=True)
        announce_thread.start()

        print("Node started")
        # try:
        #     while True:
        #         time.sleep(1)  # Keep the main thread alive
        # except KeyboardInterrupt:
        #     print("Exiting.")
