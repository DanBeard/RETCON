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
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source $HOME/.nvm/nvm.sh
source $HOME/.bashrc
nvm install --lts
nvm use --lts

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
git clone https://github.com/liamcottle/reticulum-meshchat.git
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
# i2pd support
#TODO Make this optional? It brings in boost and stuff
sudo apt-get install libminiupnpc-dev
git clone https://github.com/PurpleI2P/i2pd.git
# Known good version. Keep this up to date :)
git checkout 2.58.0
cd i2pd/build
cmake  . 
make -j4     
#sudo make install 
cd ../
debuild --no-tgz-check -us -uc -b
cd ../
sudo dpkg -i i2pd_2.58.0-1_arm64.deb
#copy systemd service file
# sudo ln -s /usr/local/bin/i2pd /usr/bin/i2pd
# sudo mkdir /var/log/i2pd
# sudo cp i2pd/contrib/i2pd.service /lib/systemd/system/i2pd.service
# sudo mkdir /etc/i2pd
# sudo mkdir /run/i2pd
# sudo mkdir /root/.i2pd
# sudo cp -R i2pd/contrib/certificates/ /root/.i2pd/
# sudo cp i2pd/contrib/i2pd.conf /etc/i2pd/
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

# add crontab to start on startup
echo "@reboot $SCRIPTPATH/start_retcon.sh &> /dev/null" | crontab -u $USER -

echo Done. Please reboot to see changes. 
echo hint: you can reboot with sudo reboot now
