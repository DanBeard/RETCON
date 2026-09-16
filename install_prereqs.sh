#!/usr/bin/env bash
SCRIPT=$(realpath "$0")
SCRIPTPATH=$(dirname "$SCRIPT")
cd $SCRIPTPATH



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


echo "This will install RETCON dependencies and configuration files"
echo "It is heavily reliant on debian amd may or might not work on other linux distros Use at your own risk"
echo "sudo is required"
echo "Examine the script before running to make sure you're cool with these changes!"

prompt_confirm "ok to run?" || exit 0

if [ $(id -u) -ne 0 ]
  then echo Please run with sudo
  exit
fi

#install python prereqs
echo Installing python....
sudo apt update
sudo apt upgrade -y
sudo apt install git -y
sudo apt install python3-pip python3-venv python3-dev curl git dbus libdbus-glib-1-dev libdbus-1-dev jq -y
sudo apt autoremove -y

# deps copied from rpi-image-gen v2 'depends' file. bdebstrap, genimage and
# recent zstd are built into a private sysroot by rpi-image-gen itself.
sudo apt install coreutils zip dosfstools e2fsprogs grep rsync curl genimage mtools mmdebstrap bdebstrap podman crudini zstd pv uidmap python-is-python3 dbus-user-session btrfs-progs dctrl-tools uuid-runtime python3-yaml python3-debian python3-jsonschema dpkg-dev cryptsetup binfmt-support -y
# unofficial rpi-image-gen deps (cross building arm64 images on other archs)
sudo apt install qemu-user-static -y
# copy default config to active
export ACTIVE_CONFIG=$SCRIPTPATH/retcon_profiles/active
if [ -f $ACTIVE_CONFIG ]; then
  echo "active config detected. Not overwriting"
else
   echo "No active config. Copying over default"
   cp "$SCRIPTPATH/retcon_profiles/default.config" $ACTIVE_CONFIG
fi
