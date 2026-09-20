#!/usr/bin/env bash

prompt_confirm() {
  while true; do
    read -r -n 1 -p "${1:-Continue?} [y/n]: " REPLY
    case $REPLY in
      [yY]) echo ; return 0 ;;
      [nN]) echo ; return 1 ;;
      *) printf " \033[31m %s \n\033[0m" "invalid input"
    esac 
  done  
}

# make sure our pwd is the same as the script
SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
cd $SCRIPTPATH

# hard-fail on errors. A silently half-installed RETCON is worse than a
# failed install, especially during image builds.
set -e


if [ "$1" != "-y" ]; then
echo ""
echo "WARNING:"
echo "This will install retcon LOCALLY. (i.e. on the current device). If you're trying to build a pi image, this probably isn't what you want"
echo "To cross compile a pi image, run ./build_retcon.sh"
echo ""
prompt_confirm "continue?" || exit 0
fi


# install nvm
echo "insalling nvm and npm"
# much curl, so secure
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.7/install.sh | bash
source $HOME/.nvm/nvm.sh
source $HOME/.bashrc
nvm install --lts
nvm use --lts

# python venv needs ensurepip which debian splits out into python3-venv
if ! python3 -m ensurepip --version >/dev/null 2>&1; then
  echo "ERROR: python3-venv is required but ensurepip is not available."
  echo "On debian: sudo apt install python3-venv python3-dev"
  exit 1
fi

echo creating venv....
rm -rf venv || true

python3 -m venv venv
source ./venv/bin/activate

# special dbus install to ensure binary version installed
echo installing python dbus libs
pip install --only-binary ':all:' sdbus
pip install --only-binary ':all:' sdbus-networkmanager

echo installing python requirements
pip install -r requirements.txt

# ---- crns: the C++ reticulum transport + host ----
# RETCON runs its mesh over crns (crnsd-compatible C++ stack, wire-compatible
# with python rns). The transport owns the interfaces from ~/.reticulum/config;
# the admin console drives it through the crns python binding; meshchat (still
# python rns) joins over a loopback TCP interface. The branch carries the
# rnsd-config compat keys (device/port/listen_on) + RNodeInterface support that
# RETCON's generated configs need.
#
# Source resolution order:
#   1. $CRNS_LOCAL_DIR   — an existing checkout (image builds stage one)
#   2. $SCRIPTPATH/crns  — a checkout staged next to the repo
#   3. clone $CRNS_REPO at $CRNS_REF (dev hosts with ssh access)
crns_repo=${CRNS_REPO:-ssh://git@192.168.0.2:2222/dbeard/crns.git}
crns_ref=${CRNS_REF:-main}
mkdir -p apps
if [ -n "${CRNS_LOCAL_DIR:-}" ] && [ -d "$CRNS_LOCAL_DIR" ]; then
  echo "using local crns checkout: $CRNS_LOCAL_DIR"
  cp -r "$CRNS_LOCAL_DIR" apps/crns
elif [ -d "$SCRIPTPATH/crns" ]; then
  echo "using staged crns checkout: $SCRIPTPATH/crns"
  cp -r "$SCRIPTPATH/crns" apps/crns
else
  echo "building crns from $crns_repo ($crns_ref)"
  git clone "$crns_repo" apps/crns
  (cd apps/crns && git checkout "$crns_ref")
fi
cd apps/crns
git submodule update --init --recursive 2>/dev/null || true
cmake -S . -B build -DCRNS_BUILD_SHARED=ON -DCRNS_WITH_BEARSSL=ON
cmake --build build -j$(nproc)
mkdir -p ../../crns_lib
cp -a build/libcrns.so* ../../crns_lib/
cd ../../
# python binding: pure python + cffi; expects libcrns.so next to it or $CRNS_LIBRARY
pip install cffi
mkdir -p python_packages
cp -a apps/crns/python/crns ./python_packages/crns
# install the binding into the venv so `import crns` works everywhere,
# and stage the library next to it (the binding dlopens
# site-packages/crns/_lib/libcrns.so* when CRNS_LIBRARY is unset)
SP=$(python -c "import site; print(site.getsitepackages()[0])")
rm -rf "$SP/crns"
cp -a apps/crns/python/crns "$SP/crns"
mkdir -p "$SP/crns/_lib"
cp -a crns_lib/libcrns.so* "$SP/crns/_lib/"
export CRNS_LIBRARY=$SCRIPTPATH/crns_lib/$(ls crns_lib | grep 'libcrns.so' | head -1)
echo "CRNS_LIBRARY=$CRNS_LIBRARY"
python -c "import crns; print('crns python binding OK, abi', crns.abi_version())"
# ---- end crns ----

# install web-apps
cd utils/client_web_ui/static
#rnode web flasher
git clone https://github.com/liamcottle/rnode-flasher
cd ../../../
# end rnode web-flasher


# install apps
mkdir -p ./apps
cd ./apps

#noadmnet is easy-peasy
pip install nomadnet

#same with rnsh
pip install rnsh

#meshchat
git clone --depth 1 https://github.com/liamcottle/reticulum-meshchat.git
cd reticulum-meshchat

pip install -r requirements.txt

# DO we have have enough memory? or not like on a raspi zero 2W                                                         
MYMEM=$(free | awk '/^Mem:/{print $2}')
echo $MYMEM

if [ "$MYMEM" -gt "1000000" ]; then
 npm install --omit=dev

 #build it
 npm run build-frontend
else
  echo "WARNING: Not enough memory to build meshchat frontend"
  echo "You will need to build the frontend remotely and then move it over into $SCRIPTPATH/apps if you want to use meshchat in client mode" 
  prompt_confirm "ok? n will abort install" || exit 0
fi
#end meshchat
cd ../

# i2pd is a distro package on debian trixie (>= 2.56). install_retcon_locally.sh
# also runs inside the image build where the retcon-apps layer already
# installed it, so this is a no-op there.
if ! command -v i2pd >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y i2pd || echo "WARNING: i2pd install failed"
  else
    apt-get update && apt-get install -y i2pd || echo "WARNING: i2pd install failed"
  fi
fi
#end i2p

# yggdrasil support
# pkg is out of date. Need to build locally which means we need to install golang
# wget "https://dl.google.com/go/$(curl https://go.dev/VERSION?m=text | head -n1).linux-arm64.tar.gz" -O go.tar.gz
# sudo tar -C /usr/local -xzf go.tar.gz

# echo 'export GOPATH=$HOME/go' >> ~/.bashrc
# echo 'export PATH=/usr/local/go/bin:$PATH:$GOPATH/bin' >> ~/.bashrc

# source ~/.bashrc

# git clone https://github.com/yggdrasil-network/yggdrasil-go
# cd yggdrasil-go
# GOOS=linux GOOARCH=arm64 ./build
# sudo cp {yggdrasil,yggdrasilctl} /usr/bin
# sudo groupadd --system yggdrasil
# sudo cp contrib/systemd/yggdrasil.service /etc/systemd/system
# #sudo systemctl daemon-reload
# sudo systemctl enable yggdrasil
# sudo yggdrasil -genconf > /etc/yggdrasil.conf
# end apps


# nodogsplash for captive portal
# Disabled for now -- we're handling it through just clever DNSmasq rules
# sudo apt-get install libmicrohttpd-dev
# git clone https://github.com/nodogsplash/nodogsplash.git
# cd nodogsplash
# make
# sudo make install
# cd ../
#end nodogsplash
# download custom interfaces into ./apps/interfaces
mkdir interfaces
# Install RNS_Over_meshtastic and soft link it to interfaces folder
git clone https://github.com/landandair/RNS_Over_Meshtastic.git
# copy interface file into interface folder
cp RNS_Over_Meshtastic/Interface/Meshtastic_Interface.py ./interfaces/

if [ -d "$HOME/.reticulum" ]; then
  if [ "$1" != "-y" ]; then
    echo " "
    echo "---------------------------------------------------"
    prompt_confirm "Old reticulum config detected. Installing will delete and rebuild the config. ok?" || exit 0
  fi
fi

echo "Deleting any old config"
rm -rf $HOME/.reticulum || true
# remake
mkdir -p $HOME/.reticulum

rm -rf $HOME/.retcon || true
mkdir -p $HOME/.retcon

# Begin proxy install 
# generate a tls cert and install http-proxy so browsers don't complain about http
# NOTE: This provides only the thinnest veneer of security. It's just to shut the browsers security policy up.
# ANYONE on the client-side wifi should be trested as trusted. Change your client PSK and only give it out to trusted users!!
openssl req -x509 -newkey rsa:4096 -keyout $HOME/.retcon/key.pem -out $HOME/.retcon/cert.pem -sha256 -days 365000 -nodes -subj "/CN=retcon"

cd $SCRIPTPATH/utils/client_web_ui/tls_proxy
npm install
# end proxy install 
cd $SCRIPTPATH

#soft link interface folder to here
ln -s  "$SCRIPTPATH/apps/interfaces" $HOME/.reticulum/interfaces

# add crontab to start on startup. Note: inside an image build this will
# fail (build hooks can't write /var/spool/cron); the retcon-apps layer
# installs /etc/cron.d/retcon-start instead, so that's not an error.
echo "@reboot $SCRIPTPATH/start_retcon.sh &> /dev/null" | crontab -u $USER - 2>/dev/null || \
    echo "INFO: skipping user crontab (managed by /etc/cron.d/retcon-start in the image build)"

# meshchat's own reticulum config dir: meshchat (still python rns) cannot
# share the crns host's sockets, so it joins the mesh through the crns
# host's loopback TCP listener (127.0.0.1:4243, HDLC framing).
mkdir -p $HOME/.meshchat-rns
cat > $HOME/.meshchat-rns/config <<EOMC
[reticulum]

  enable_transport = no
  # join the crns host over loopback directly; never look for a python-rns
  # shared instance on this machine (crns owns the mesh, not rnsd)
  share_instance = no

[logging]
  loglevel = 4

[interfaces]

  [[crns Host Loopback]]
    type = TCPClientInterface
    interface_enabled = true
    target_host = 127.0.0.1
    target_port = 4243
EOMC

echo Done. Please reboot to see changes. 
echo hint: you can reboot with sudo reboot now
