import netifaces as ni
from flask import Flask, render_template
import os
import subprocess

dir_path = os.path.dirname(os.path.realpath(__file__) + "../")

app = Flask(__name__)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/shutdown')
def shutdown():
    # trigger the shutdown
    subprocess.Popen(f"sleep 3; sudo reboot",shell=True)
    return render_template("index.html")

# main driver function
if __name__ == '__main__':
    try:
        iface = "uap0"
        ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
        # run() method of Flask class runs the application 
        # on the local development server.
        app.run(host=ip,port=80)
    except ValueError:
        print("ERROR Couldn't get netinfo for uap. Assuming dev session and launching with default settings")
        app.run()