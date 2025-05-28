import netifaces as ni
import json 
from flask import Flask, render_template, request, jsonify
import os
import sys
import subprocess

# dirty hack that allows us to run this as a flask entry point ANY take advantage of code reuse
util_path = os.path.dirname(os.path.realpath(__file__)) + "/../"
print(util_path)
sys.path.append(util_path)
from admin import RetconAdmin


app = Flask(__name__)
admin = RetconAdmin("UNKNOWN")

@app.route('/')
def index():
    return render_template("index.html", admin=admin)

@app.route('/wifi', methods=['POST'])
def wifi():
    try:
        post = json.loads(request.data)
        client_ap_psk = post["client_ap_psk"]
        admin.client_ap_psk = client_ap_psk
        
        return jsonify({ "message" : "Config Saved. Changes only take effect after a reboot.", "status": "ok"})
    except Exception as e:
        return jsonify({ "message" : str(e), "status": "error"})

@app.route('/advanced', methods=['POST'])
def advanced():
    try:
        post = json.loads(request.data)
        config_file = post["config_file"]
        admin.config_str = config_file
        
        return jsonify({ "message" : "Config Saved. Changes only take effect after a reboot.", "status": "ok"})
    except Exception as e:
        return jsonify({ "message" : str(e), "status": "error"})
    
# @app.route('/reboot')
# def reboot():
#     admin.reboot()
#     return render_template("index.html")

# main driver function
if __name__ == '__main__':
    
    if len(sys.argv) > 1:
        admin = RetconAdmin(sys.argv[1])
    
    try:
        iface = "uap0"
        ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
        # run() method of Flask class runs the application 
        # on the local development server.
        app.run(host=ip,port=80)
    except ValueError:
        print("ERROR Couldn't get netinfo for uap. Assuming dev session and launching with default settings")
        app.run()