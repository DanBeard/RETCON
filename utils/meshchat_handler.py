import subprocess
import os

class MeshchatHandle():
    
    _singleton = None

    @classmethod
    def start_meshchat(cls):
        print("Starting Meshchat")
        current_env = os.environ.copy()
        dir_path = os.path.dirname(os.path.realpath(__file__))
        cls._singleton = subprocess.Popen(
            f"python {dir_path}/apps/reticulum-meshchat/meshchat.py --headless", 
            shell=True, env=current_env)