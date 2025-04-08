import subprocess
import os
import netifaces as ni

class MeshchatHandle():
    
    _singleton = None
    _homepage_singleton = None

    @classmethod
    def start_meshchat(cls, iface, ssid):
        ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
        print(f"Starting Meshchat on {ip}")
        current_env = os.environ.copy()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        cls._singleton = subprocess.Popen(
            f"python {dir_path}/../apps/reticulum-meshchat/meshchat.py --headless --host {ip}", 
            shell=True, env=current_env)
        
        print("starting retcon client homepage")
        # Also launch the retcon homepage!
        cls._homepage_singleton = subprocess.Popen(
            f"authbind --deep python {dir_path}/../client_web_ui/retcon_client_ui.py {ssid}", 
            shell=True, env=current_env)