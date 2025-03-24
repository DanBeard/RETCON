#!/usr/bin/env bash

# make sure our pwd is the same as the script
cd "$(dirname "$0")"

source ./venv/bin/activate

echo "Starting retcon in 3"
sleep 3
python retcon.py

