import subprocess
import os
import netifaces as ni
import time
import sqlite3
from glob import glob 


class MeshchatHandle():
    
    _singleton = None
    _homepage_singleton = None
    _tls_proxy_singletone = None

    @classmethod
    def start_meshchat(cls, iface, ssid, retcon_config):
        ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
        print(f"Starting Meshchat on {ip}")
        current_env = os.environ.copy()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        
        
        print("Modifying meshchat config")
        cls.alter_meshchat_config(retcon_config)
        
        cls._singleton = subprocess.Popen(
            f"python {dir_path}/../apps/reticulum-meshchat/meshchat.py --headless --host {ip}", 
            shell=True, env=current_env)
        
        time.sleep(0.25)
                
        print("starting retcon client homepage")
        # Also launch the retcon homepage!
        cls._homepage_singleton = subprocess.Popen(
            f"authbind --deep python {dir_path}/client_web_ui/retcon_client_ui.py {ssid}", 
            shell=True, env=current_env)
        
        time.sleep(0.25)
        
        print("starting retcon TLS proxy")
        # and the reverse proxy for tls
        cls._tls_proxy_singletone = subprocess.Popen(
            f"authbind --deep node proxy.js {ip}", 
            shell=True, env=current_env, cwd=f"{dir_path}/client_web_ui/tls_proxy")
        
       
        
    @classmethod
    def alter_meshchat_config(cls, retcon_config):
        
        config = retcon_config.get("meshchat",{})
        if len(config) == 0:
            print("No meshchat config overrides. ejecting...")
            return
        
        ident_path = os.path.expanduser("~/retcon/storage/identities/")
        database_paths = glob( ident_path + "*/database.db")
        if len(database_paths) == 0:
            print(f"ERROR: Could not modify meshchat config. No database files at {ident_path}")
            return
        
        for db_path in database_paths:
            con = sqlite3.connect(db_path)
            try:
                cur = con.cursor()
                
                # have we already modified the config?
                already_modified = cur.execute("SELECT value FROM config WHERE key='retcon_modified'").fetchone()
                if already_modified is not None and already_modified == 1:
                    print("Already modified, ejecting...")
                    return
                
                # we haven't modified the config yet, let's do it
                for key, val in config.items():
                    print(f"Setting {key}={val}")
                    cur.execute("INSERT into config (key, value, created_at, updated_at) VALUES (?, ?, datetime(), datetime()) "
                        "ON CONFLICT(key) DO UPDATE SET value=?", (key, val, val))
                
                # finally upsert the retcon_modified key so we know we've already done this
                if already_modified is None:
                    cur.execute("INSERT into config (key, value, created_at, updated_at) VALUES ('retcon_modified', 1, datetime(), datetime())")
                else:
                    cur.execute("UPDATE config SET value=1 WHERE key='retcon_modified'")
                    
                con.commit()
            finally:
                con.close()
        
        
        
                              
        