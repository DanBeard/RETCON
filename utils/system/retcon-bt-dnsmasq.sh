#!/bin/bash
# RETCON dnsmasq for the BT PAN bridge (br-bt). Runs as a systemd unit pair
# with retcon-bt-nap.service; NOT enabled by default — btpan turns it on.
exec /usr/sbin/dnsmasq --no-daemon --bind-interfaces --interface=br-bt \
  --except-interface=lo --dhcp-range=10.56.0.10,10.56.0.200,255.255.255.0,12h \
  --dhcp-option=option:router,10.56.0.1 \
  --address=/retcon.local/10.56.0.1 --address=/retcon.gateway/10.56.0.1 \
  --pid-file=/run/retcon-bt-dnsmasq.pid