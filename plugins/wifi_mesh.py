# wifi mesh class imports
import asyncio
import uuid
import sys
import os
import time
import re 
from jinja2 import Template
import sdbus
import netifaces as ni
from sdbus_async.networkmanager import (
    NetworkManager,
    NetworkDeviceWireless,
    NetworkManagerSettings,
    AccessPoint,
)
from .base_plugin import RetconPlugin

auto_iface_template = """

[[Auto Interface {{iface}}]]
  type = AutoInterface
  interface_enabled = True

  mode= {{mode}}
  name = auto_iface_hack_{{iface}}
  devices = {{iface}}
  
  """
  
tcp_server_iface_template = """
  [[TCP Server Interface]]
  type = TCPServerInterface
  enabled = yes
  mode= {{mode}}
  device = {{iface}}
  name = retcon_tcp_server_iface_{{iface}}
  listen_port = 4242
  
  """
  
tcp_client_iface_template = """
  [[TCP Client Interface]]
  type = TCPClientInterface
  enabled = yes
  mode= {{mode}}
  name = retcon_tcp_client_iface_{{iface}}
  target_host = retcon.gateway
  target_port = 4242
  """

class WifiMeshPlugin(RetconPlugin):

    PLUGIN_NAME = "wifi_mesh"
    
    mesh = None
    
        
    # plugin config code. Take the config object, the template string
    # and return any Jinja vars in reticulum.config template
    # (for example) plugin_interfaces
    def get_config(self) -> dict:
        wifi = self.retcon_config["retcon"]["wifi"]
        
        # Auto interface is too flaky with changing topologies 
        #interface_str =  Template(auto_iface_template).render(iface=wifi['client_iface'], mode="full")
        #interface_str += Template(auto_iface_template).render(iface=wifi['ap_iface'], mode="gateway")
        
        # tcp interfaces
        interface_str =  Template(tcp_client_iface_template).render(iface=wifi['client_iface'], mode="full")
        interface_str += Template(tcp_server_iface_template).render(iface=wifi['ap_iface'], mode="gateway")
        return {
            "plugin_interfaces" : interface_str
        }
        
    # An init function that will get called on RETCON startup for init/bootstrapping
    def init(self) -> None:
        print("Init RETCON wifimesh plugin")

        # use multiprocessing for this
        current_env = os.environ.copy()
        script_path = os.path.realpath(__file__)
        wifi = self.retcon_config["retcon"]["wifi"]
        ap_iface = wifi['ap_iface'] if self.retcon_config["retcon"]["mode"] == 'transport' else None
        if ap_iface:
            self.transport_update_dnsmasq(ap_iface)
            
        mesh = RetconMesh(wifi['prefix'].encode(), wifi['psk'], int(wifi['freq']), wifi['client_iface'], ap_iface)
        self.mesh = mesh
        #return mesh.mesh_up(self)
        # process = subprocess.Popen(
        #     f"python {script_path} '{wifi['prefix']}' '{wifi['psk']}' {wifi['freq']} '{wifi['client_iface']}' '{ap_iface}' ", 
        #     shell=True, env=current_env)


    def transport_update_dnsmasq(self, ap_iface):
        # update the DNS masd file so retcon stuff points to us
        # only for transport nodes
        ip = ni.ifaddresses(ap_iface)[ni.AF_INET][0]['addr']
        urls = ["retcon.gateway", "retcon.local", "retcon.radio", "retcon.com", "retcon"]
        redirect_str = "\n".join(f"address=/{x}/{ip}" for x in urls)
        config_path = "/etc/NetworkManager/dnsmasq-shared.d/retcon_redirect.conf"
        with open(config_path, "w") as fout:
            fout.write(redirect_str)
        
        
    async def loop(self):
        await self.mesh.mesh_up(self)
    

class RetconMesh:
    
    MIN_STREN = 33  # below this we won't try to connect
    
    def __init__(self, ssid_prefix: bytes, password:str, freq: int, client_iface: str, ap_iface=None):
        
        # explicit type check since it's so easy to mess up
        if type(ssid_prefix) == str:
            raise Exception("ssid_prefix must be BYTES not STRING")
        print(ssid_prefix)
        self.ssid_prefix = ssid_prefix
        self.password = password
        self.freq = freq
        self.client_iface = client_iface
        self.client = None
        self._client_path = None
        self.ap = None
        self.ap_iface = ap_iface
        self.is_transport= ap_iface is not None # For now we know we're a transport if we are supplied an ap iface to manage
        self._client_ap_choices = []
        self._active = True # we working? set to false to shutdown all loops
        self._dynamic_auto_iface = None
        self._last_client_connection_time = None
        #client state
        
    async def mesh_up(self, plugin=None) -> None:
        # Init devices  
        #system_bus = sdbus.sd_bus_open_system()  # We need system bus
        # just set default to system dbus so we don't have to pass it around.  
        sdbus.set_default_bus(sdbus.sd_bus_open_system()) 
        self.nm = NetworkManager()
        self.plugin = plugin
        
        
        devices_paths = await self.nm.get_devices()
        for device_path in devices_paths:
            generic_device = NetworkDeviceWireless(device_path)
            name = await generic_device.interface
            
            if name == self.client_iface:
                self.client = generic_device
                self._client_path = device_path
                print('Client : ', await generic_device.interface)
            elif name == self.ap_iface:
                self.ap = generic_device
                print('AP     : ', await generic_device.interface)
            else:
                print('       : ', await generic_device.interface)
                
        if self.client is None:
            raise ConnectionError("Could not find client iface " + self.client_iface)
        
        if self.ap is None and self.ap_iface is not None:
            raise ConnectionError("Could not find ap iface " + self.ap_iface)
        
        
        self._scan_task = asyncio.create_task(self._scan_loop())
        
        # busy loop here to keep control
        while self._active:
            await asyncio.sleep(5)
                    
        
    async def _scan_loop(self):
        while self._active:
            if await self._should_scan():
                print("Scanning...")
                await self.client.request_scan({})
                print("Sleeping...")
                await asyncio.sleep(3)
                ap_paths = await self.client.access_points
                print("Aping...")
                all_aps = [AccessPoint(p) for p in ap_paths]

                # limit to only ones that match our prefix
                valid_aps = []
                for ap in all_aps:
                    ssid = await ap.ssid
                    freq = await ap.frequency
                    if ssid.startswith(self.ssid_prefix):
                        if freq == self.freq:
                            valid_aps.append(ap)
                        else:
                            print("WARNING: found SSID prefix that matched but wrong freq. ")
                            print(f"Expected {self.freq} but ap with ssid={ssid} had {freq}")
                
                self._client_ap_choices = valid_aps
                if len(self._client_ap_choices) > 0:
                    try:
                        await self.connect_client()
                    except Exception as e:
                        print("ERROR! " + str(e))
                        print("re-looping")
            
            # wait before next scan
            await asyncio.sleep(5)
            
    async def connect_client(self):
        # Go through all the valid APs and pick one to connect to
        aps = [(x, await x.ssid, await x.strength) for x in self._client_ap_choices]
        aps.sort(key=lambda y: y[2], reverse=True) # sort by strength DESC
        print("APs :", aps)
        if len(aps) == 0:
            return
        
        # select the candidate to connect to
        # if we're not a transport then it's easy, just the strongest
        cand_ap, cand_ssid, cand_str = aps[0]
        # if we're a transport though, we want to avoid 2 nodes being double connected to eachother. 
        # so connect to the strongest that has a LARGER SSID than us (or MIN-strength)
        # This should lead to heavy centralization of tightly grouped nodes (which is more efficient) 
        # and we can control which takes priority by the name
        if self.is_transport and len(aps) > 1:
            i=1
            while i < len(aps) and cand_ssid <= self.plugin.node_ssid and aps[i][2] > RetconMesh.MIN_STREN:
                cand_ap, cand_ssid, cand_str = aps[i]
                i+=1
        
        active_ap = await self.active_client_ap
        if active_ap is not None:
            if await active_ap.ssid != cand_ssid:
                await self.client.disconnect()

        print("connecting to ", cand_ssid)
        connection = await NetworkManagerSettings().add_connection_unsaved(
            {
                "connection": {
                    "type": ("s", "802-11-wireless"),
                    "uuid": ("s", str(uuid.uuid4())),
                    "id": ("s", "RETCON_WIFI_MESH"),
                    "interface-name": ("s", self.client_iface),
                    "autoconnect": ("b", False),
                },
                "802-11-wireless": {"ssid": ("ay", cand_ssid), "mode": ("s", "infrastructure")},
                "802-11-wireless-security" : {"key-mgmt": ("s", "wpa-psk"), "auth-alg": ("s", "open"), "psk": ("s", self.password)},
                "ipv4": {"method": ("s", "auto")},
                "ipv6": {"method": ("s", "auto")},
            }
        )
        
        print(connection)
        
        await self.nm.activate_connection(
            connection=connection, device=self._client_path
        )
        
        self._last_client_connection_time = time.time()
        
        # After we have dchp, change /etc/hosts so retcon.gateway goes to our gateway
        retry = 10
        ip = None
        
        while ip is None and retry > 0:
            try:
                print("Attemping to get IP for TCP client")
                await asyncio.sleep(5)
                retry-=1
                ip = ni.ifaddresses(self.client_iface)[ni.AF_INET][0]['addr']
                print(f"Got IP {ip}")
            except: 
                pass
            
        if ip is None:
            await self.client.disconnect()
            
        with open("/etc/hosts", 'r') as fin:
            print("Reading hosts file")
            hosts = fin.read()
     
        with open("/etc/hosts", "w") as fout:
            fout.write(re.sub(r'\d+\.\d+\.\d+\.\d+ retcon\.gateway','',hosts))
            gateway_ip = '.'.join(ip.split(".")[0:3] + ['1'])
            print(f"Writing gateway_ip = {gateway_ip} to hosts file")
            fout.write(f"\n{gateway_ip} retcon.gateway")
        
        print("Dynamically rebooting reticulum")
        await self.plugin.restart_rnsd()
        await asyncio.sleep(10)
        print("done")

            
    @property
    async def active_client_ap(self):
        if self.client is None:
            return None
        
        active_ap_path = await self.client.active_access_point
        #print(f"active_ap_path={active_ap_path}")
        if len(active_ap_path) <3:
            return None
        
        return AccessPoint(active_ap_path)
        
    async def _should_scan(self):
        """ should we scan for new wifi access points?"""
        if self.client is None:
            return False
        
        # TODO some strength and timing checks here
        # Like if the connected SSID is too weak, maybe we scan again
        # and if we just connected to someone, give it a delay so we're not swapping back and forth and back and forth
        active_ap = await self.active_client_ap
        if active_ap is None:
            return True
        
        # ok so if we got this far we're alreaddy connected to an SSID
        # is it a valid one though?
        ssid = await active_ap.ssid
        valid_connection = ssid.startswith(self.ssid_prefix) 
        if not valid_connection:
            return True
        
        # If we got this far, then it is valid, so if it's been longer than 10 minutes than we connected, we should scan
        return time.time() - self._last_client_connection_time > 600
            

if __name__ == "__main__":
    args = sys.argv
    ap_iface = args[5] if len(args[5]) > 1 else None
    mesh = RetconMesh(args[1].encode(), args[2], int(args[3]), args[4], ap_iface)
    asyncio.run(mesh.mesh_up())

