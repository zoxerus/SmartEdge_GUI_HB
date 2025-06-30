import socket
import json 


str_TYPE = 'Type'
str_NODE_JOIN_LIST = 'njl'
str_NODE_LEAVE_LIST = 'nll'
str_NODE_IDS = 'nids'


# , 'SN:00:00:03'





message = {'Type': str_NODE_JOIN_LIST,
           str_NODE_IDS: ['SN000002'] 
           }





str_message = json.dumps(message)

host = 'localhost'
port = 9999

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(('0.0.0.0', 9999))
    s.sendall( bytes( str_message.encode() ) )
    data = s.recv(1024).decode() #receive up to 1024 bytes.
    data_json = json.loads(data)
    print(json.dumps(data_json, indent= 2 ))
