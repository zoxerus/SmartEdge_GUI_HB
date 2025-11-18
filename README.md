# Installing Dependencies and Running
## 1- For Colocated AP and CO 
For this run from the main directory
Then make sure to install the following packages
```
sudo apt install python3-venv python3-dev net-tools screen
```
Now create a virtual environment running the command in the main directory of smartedge
```
python3 -m venv .venv
```

Then install the required python3 modules
```
.venv/bin/pip -r ./requirements/ap.txt
.venv/bin/pip -r ./requirements/co.txt
```

You might as well need to install docker engine for the later steps  
It can be installed from the link:
https://docs.docker.com/engine/install/


### Cassandra docker image is needed
This image is installed and run by the script ./run_cassandra_docker.sh
be patient it takes a couple of minute for the database to be online

### Access Points, a P4 switch is needed  
For devices with x86 processors it can be installed from the link:
or alternatively can be run from a docker image by running the script ./run_bmv2_docker.sh  
https://github.com/p4lang/behavioral-model


While for devices wit ARM processors e.g Raspberry Pi a docker image can be installed.
Check the script  
./shell_scripts/fetch_se_network_images.sh


## 2- For Smart Nodes
First make sure to install the following packages
```
sudo apt install python3-venv python3-dev net-tools screen
```
Now create a virtual environment running the command in main directory
```
python3 -m venv .venv
```

Then install the required python3 modules
```
.venv/bin/pip install -r ./requirements/sn.txt
```

# Running the scripts
on the coordinator node run the log collector
```
cd ./GUI/backend
../../.venv/bin/python /coordinator_log_server.py
```

run the cassandra database 
```
sudo docker run --rm -d --name cassandra --hostname cassandra --network host cassandra
```
wait about a minute or two, as it takes some time to run

to start the colocated AP and CO
from the main directory of smartedge run
create a screen
```
screen -S ap
```
inside the screen execute (must be in the main directory of smartedge):
```
sudo ./run.py --type ac --uuid-ap 2 --uuid-co 1
```
where the uuids in the previous command 2 and 1 are custom but each node must have a unique id 

for running smart node, create a screen
```
screen -S node
```
from inside the screen run this command from the main directory
```
sudo ./run.py --type sn --uuid-self 3
```
where the uuid 3 is custom but must be unique for each node

# Integration with TUB
- The Swarm coordinator can be reached on the TCP port 9999.

- message format for requesting nodes to join is :
```
message = {'Type': 'Type of message',
           'nids': ['id1', 'id2'] 
           }
```
 
Where Type can be 'njl' for node joinning list or 'nll' for nodes leaving list.


- message format for requesting nodes to join is :
```
message = {'Type': 'njl',
           'nids': ['SN000002', 'SN000003'] 
           }
```


- message format for requesting nodes to be kicked out is :
```
message = {'Type': 'nll',
           'nids': ['SN000002', 'SN000003'] 
           }

```