"""
RETCON administration utility
"""
import os
import asyncio
import RNS
import base64
import time
from LXMF import LXMessage, LXMRouter
import subprocess
from rns_config_gen import get_recton_config
import sdbus
from sdbus_block.networkmanager import (
    NetworkManager,
    NetworkDeviceWireless,
    NetworkManagerSettings,
    AccessPoint,
)


# meant to be run from main as a sort of root rnsd, don't import me
dir_path = os.path.dirname(os.path.realpath(__file__)) + "/.."

class RetconAdmin:
    """ The actual admin functionality"""
    
    def __init__(self, name):
        self.config = get_recton_config(None) # always the active profile
        self.name = name
        
        
    # write the config to the active profile
    def write_config(self):
        profile_path = dir_path + "/retcon_profiles/active"
        with open(profile_path, 'w') as fout:
            self.config.write(profile_path)
       
    @property
    def announce_every(self):
        return float(self.config['retcon'].get("announce_every", 10*60)) #announce every 10 mins
        
    @property
    def admins(self):
        return self.config['retcon'].get("admins","").split(",")
    
    @property
    def client_iface(self):
        return self.config['retcon']["wifi"].get("client_iface", None)
    
    @property
    def password(self):
        return self.config['retcon'].get("password", None)
    
    @property
    def is_transport(self):
        return self.config['retcon'].get("mode", "ui") == "transport"
    
    def is_admin(self, user_id, password):
        return user_id in self.admins or (self.passowrd is not None and password == self.password)
    
    @property
    def connected_ap(self):
        """ What AP are we connected to?"""
        sdbus.set_default_bus(sdbus.sd_bus_open_system()) 
        nm = NetworkManager()
        client = None
        devices_paths = nm.get_devices()
        for device_path in devices_paths:
            generic_device = NetworkDeviceWireless(device_path)
            name = generic_device.interface
            
            if name == self.client_iface:
                client = generic_device
                print('Client : ',  generic_device.interface)
            else:
                print('       : ',  generic_device.interface)
                
        if client is None:
            return f"No client iface named {self.client_iface}"
        
        active_ap_path =  self.client.active_access_point
        if len(active_ap_path) <3:
            return None
        
        return AccessPoint(active_ap_path)
        
    

class LXMFAdminConsole:                  
    
    def __init__(self, admin: RetconAdmin):
        base_storage_dir = os.path.join(dir_path, "storage")
        self.admin = admin
        self.r = RNS.Reticulum()
        self.router = LXMRouter(storagepath=base_storage_dir)
        self.router.register_delivery_callback(self.on_rns_recv)
        self._announce_interval = 2
        
         # ensure provided storage dir exists, or the default storage dir exists
        
        os.makedirs(base_storage_dir, exist_ok=True)

        # configure path to default identity file
        default_identity_file = os.path.join(dir_path, "identity")

        # if default identity file does not exist, generate a new identity and save it
        if not os.path.exists(default_identity_file):
            identity = RNS.Identity(create_keys=True)
            with open(default_identity_file, "wb") as file:
                file.write(identity.get_private_key())
            print("Reticulum Identity <{}> has been randomly generated and saved to {}.".format(identity.hash.hex(), default_identity_file))

        # default identity file exists, load it
        identity = RNS.Identity(create_keys=False)
        identity.load(default_identity_file)
        print("Reticulum Identity <{}> has been loaded from file {}.".format(identity.hash.hex(), default_identity_file))
        
        self.ident = identity
        self.source = self.router.register_delivery_identity(self.ident, display_name=self.admin.name)
        self.router.announce(self.source.hash)
        self._msg_queue = []
        self._response_queue = []
        
        
    def process_command(self, message:bytes):
        command, *args = message.decode().strip().split(" ", 1)
        command = command.lower()
        
        if command == "status":
            result = "" 
            current_env = os.environ.copy()
            result = subprocess.run(['rnstatus'], stdout=subprocess.PIPE, env=current_env)
            result+= result.stdout.decode()
            
            result+= "wifi is connected to: " + self.admin.connected_ap
        else:
            return ("Welcome to the RETCON LXMF admin interface. Possible commands are: \n" +
                            "status")
        
                    
    def on_rns_recv(self, message : LXMessage):        
        # DO STUFF WITH MESSAGE HERE
        reply_hash = message.source_hash
        response = self.process_command(message.content)
        RNS.Transport.request_path(reply_hash)
        self._response_queue.append((reply_hash, response))
           
            
    async def loop(self):
        last_announce = 0 # never announced
        
        while True:
            self._msg_queue = []
                  
            # help queue for responding with help to messages
            r_q = self._response_queue
            self._response_queue = []
            for reply_hash, text in r_q:
                dest_id = RNS.Identity.recall(reply_hash)
                if dest_id is not None and RNS.Transport.has_path(reply_hash):
                    destination = RNS.Destination(dest_id, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery")
                    lxm = LXMessage(destination, self.source,
                                    text,
                                    "RETCON console",
                                    desired_method=LXMessage.OPPORTUNISTIC)
            
                    self.router.handle_outbound(lxm)
                    print(" -> " + str(text))
                else:
                    RNS.Transport.request_path(reply_hash)
                    self._response_queue.append((reply_hash, text))
                    
            # announce when it's time
            now = time.time()
            if now - last_announce > self._announce_interval:
                print("announcing again!")
                self.router.announce(self.source.hash)
                last_announce = now
                # double the announce interval until we hit the desired max. This means way MORE announces on startup 
                # before leveling off as qw're been around longer
                self._announce_interval = min(self.admin.announce_every, self._announce_interval * 2)
                
            #print(os.getppid())
            await asyncio.sleep(2)
                    
    
    
if __name__ == "__main__":
    import sys
    name = sys.argv[1]
    admin = RetconAdmin(name)
    lxmf_admin = LXMFAdminConsole(admin)
    
    asyncio.run(lxmf_admin.loop())