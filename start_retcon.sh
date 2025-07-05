#!/usr/bin/env bash
# disable ssh server. WE can re-enable it temporarily via admin controls
sudo systemctl stop ssh || true
sudo systemctl disable ssh || true

# make sure our pwd is the same as the script
cd "$(dirname "$0")"

source ./venv/bin/activate

echo "Starting retcon in 3"
sleep 3
python retcon.py

