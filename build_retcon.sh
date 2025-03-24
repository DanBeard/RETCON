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
#echo $SCRIPTPATH

echo "WARNING: This utility is meant for advanced users to build a customized RETCON image" 
echo "Examine the script before running to make sure you're cool with what it's doing!"
echo ""
echo "Ensure you ran ./install_prereqs.sh FIRST. That is REQUIRED for this process to work"
echo "This script will install and use the rpi-image-gen at at ~/.retcon-build/  to build an deployable rpi image "
echo "It is heavily dependent on debian and is recommended to be run on a an rpi4 or rpi5"
echo "(Though it has been tested on x86 using the automatic qemu arm emulation layer and that appears to work)"
echo "Non debian based distros (e.g. fedora, arch, etc) will probably not work"
echo ""

prompt_confirm "ok to run?" || exit 0

sudo rm -rf $HOME/.retcon-build || true

mkdir $HOME/.retcon-build

cd $HOME/.retcon-build
git clone https://github.com/raspberrypi/rpi-image-gen.git

cd rpi-image-gen

# deps should already have been installed in ./install_prereqs
# Do the build
./build.sh -c retcon -D $SCRIPTPATH/retcon_pi/ -o $SCRIPTPATH/retcon_pi/retcon.options -N retcon

echo "DONE!"
echo ""
echo "image file located at $HOME/.retcon-build/rpi-image-gen/work/retcon/artefacts/retcon.img"
