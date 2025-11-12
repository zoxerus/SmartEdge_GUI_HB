if [ "$(id -u)" -ne 0 ]; then
  echo "Please run this script as root or using sudo!"
  exit 1
fi

screen -dmS bmv2 bash -c "simple_switch $(pwd)/p4app/ap.json"

# screen -d -m sh -c "simple_switch $(pwd)/p4app/ap.json"
