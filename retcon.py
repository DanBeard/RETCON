#!/usr/bin/env python

import os
import sys
import importlib.util
import asyncio
import time
import subprocess
import signal
import uuid
from base64 import a85encode
    

from utils.rns_config_gen import generate_rns_config, get_recton_config
from utils.meshchat_handler import MeshchatHandle

wifi_channel_to_freq = {
    1: 2412,
    2: 2417,
    3: 2422,
    4: 2427,
    5:2432,
    6: 2437,
    7: 2442,
    8: 2447,
    9: 2452,
    10: 2457,
    11:2462,
    12: 2467,
    13: 2472,
    14: 2484
}

wifi_freq_to_channel = {f:c for c,f in wifi_channel_to_freq.items()}


# This script will be our entry point for RETCON
if __name__ == "__main__":

    # where are we now?
    dir_path = os.path.dirname(os.path.realpath(__file__)) 
    
    # first things first, regenerate the reticulum config
    # So we can auto-detect anything hooked up  
    profile = sys.argv[1] if len(sys.argv) > 1 else None
    #Load our retcon profile config file    
    config = get_recton_config(profile)
    r_config = config["retcon"]
    
    # startup the ap, this is the same  whether we're a transport or client

    # are we just a transport? or should we launch ui?
    is_transport = r_config.get("mode", "client") == "transport"
    is_client = r_config.get("mode", "client") == "client"
    
    wifi_config = r_config["wifi"]
    
    if "prefix" not in wifi_config or "psk" not in wifi_config or "freq" not in wifi_config:
        print("ERROR!  'prefix', 'psk', and freq are required in [[wifi]] section of config")
        exit()
        
    client_iface = wifi_config["client_iface"]
    ap_iface = wifi_config["ap_iface"]
    node_id = uuid.getnode() 
    
    if is_client:
        ssid = wifi_config.get("client_ap_prefix", wifi_config["prefix"]) + a85encode(node_id.to_bytes(6, signed=False)).decode()
        psk = wifi_config.get("client_ap_psk", wifi_config["psk"])
    else:
        ssid = wifi_config["prefix"] + a85encode(node_id.to_bytes(6, signed=False)).decode()
        psk = wifi_config['psk']
        
    channel = wifi_freq_to_channel[int(wifi_config["freq"])]
    
    # TODO: We should really use dbus directly for this, but nmcli is so much easier
    # Setup wifi interfaces
    commands = [
        "nmcli connection delete preconfigured", # bring down and connection that user preconfiged to setup retcon
        "nmcli connection delete RETCON_WIFI_MESH",
        "nmcli connection delete retcon_ap",
        f"nmcli con add con-name retcon_ap ifname {ap_iface} type wifi ssid '{ssid}'",
        f"nmcli con modify retcon_ap wifi-sec.key-mgmt wpa-psk",
        f"nmcli con modify retcon_ap wifi-sec.psk '{psk}' ",
        f"nmcli con modify retcon_ap 802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel {channel} ipv4.method shared"
    ]
    for command in commands:
        print(command)
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        process.wait()
    
    print("Brought up AP now letting it settle")
    time.sleep(8)
    
    rnsd_tasks=[]
    
    async def run_admin_interfaces():
        await asyncio.sleep(5) # give some time for wifimesh and other init before loading admin iface
        env_copy = os.environ.copy()
        t = subprocess.Popen(["python", f"{dir_path}/utils/admin.py", ssid], env=env_copy)
        rnsd_tasks.append(t)
    
    async def restart_rnsd():
        print("restarting rnsd")
        old_tasks = [x for x in rnsd_tasks]
        rnsd_tasks.clear()
        for t in old_tasks:
            t.terminate()
        for t in old_tasks:
            t.wait()
            
        await asyncio.sleep(1)
        await run_admin_interfaces()
        

    # init any plugins defined in the retcon profile and run admin iface
    loaded_plugins = {}
    async def load_plugins():
        import plugins
        from plugins.base_plugin import RetconPlugin
        
        subclses = RetconPlugin.__subclasses__()
        plugin_classes = {cls.PLUGIN_NAME : cls for cls in subclses}
        
        #load all defined plugins
        for plugin_name, plugin_config in config.get("retcon_plugins",{}).items():
            print("Loading plugin "+ plugin_name)
            # spec = importlib.util.spec_from_file_location(plugin_name,f"{dir_path}/plugins/{plugin_name}.py")
            # mod  = importlib.util.module_from_spec(spec)
            # spec.loader.exec_module(mod)
            # cls = mod.plugin
            cls = plugin_classes[plugin_name]
            loaded_plugins[plugin_name] = cls(ssid, plugin_config, config, restart_rnsd)
        
        # regenerate rns config based on hardware and plugins
        rns_config = generate_rns_config(loaded_plugins, profile)
        with open(os.path.expanduser("~/.reticulum/config"), "w") as fin:
            fin.write(rns_config)
            
        # init all the plugins and await any that return tasks
        plugin_tasks = []
        for plugin in loaded_plugins.values():
            maybe_awaitable = plugin.init()
            if maybe_awaitable is not None:
                plugin_tasks.append(maybe_awaitable)
                
        await asyncio.gather(*plugin_tasks)

   
    #tasks to run if we're in ui mode
    # these wont be run if we're in transport mode
    async def run_ui_tasks():
        await asyncio.sleep(3) # sleep for a few seconds to allow server to settle
        print("Starting meshchat")
        MeshchatHandle.start_meshchat(ap_iface, ssid, config)
        await asyncio.sleep(2)
    
    async def run():
        # busy loop so we don't exit
        async def busy_loop():
            await load_plugins()
            await asyncio.sleep(1)
            while True:
                plugin_loops = [x.loop() for x in loaded_plugins.values()]
                await asyncio.gather(*plugin_loops)
                await asyncio.sleep(60)
                
        tasks = [busy_loop(), run_admin_interfaces()]
        if is_client:
            tasks.append(run_ui_tasks())
            
        await asyncio.gather(*tasks)
        
    asyncio.run(run())
    # now parse the retcon config and 
    #app.run(host="0.0.0.0")
