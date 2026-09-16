#!/usr/bin/env bash
# disable ssh server. WE can re-enable it temporarily via admin controls
sudo systemctl stop ssh || true
sudo systemctl disable ssh || true

echo "Starting retcon in 3"
sleep 3

# make sure our pwd is the same as the script
cd "$(dirname "$0")"

source ./venv/bin/activate
source $HOME/.nvm/nvm.sh
nvm use default

# crns shared library for the python binding (admin.py also self-resolves
# via crns_lib/; exporting here makes it explicit for child processes)
if [ -z "${CRNS_LIBRARY:-}" ] && [ -d ./crns_lib ]; then
  export CRNS_LIBRARY=$(ls ./crns_lib/libcrns.so* | sort -V | tail -1)
fi

python retcon.py

