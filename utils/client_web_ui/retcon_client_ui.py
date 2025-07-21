import netifaces as ni
import json 
from flask import Flask, render_template, request, jsonify
import os
import sys
import subprocess
import time

from flask_file_explorer.file_explorer import file_explorer_bp  # The blueprint code
from flask_file_explorer.filters import register_filters        # Filters used in the viewer

# dirty hack that allows us to run this as a flask entry point AND take advantage of code reuse
util_path = os.path.dirname(os.path.realpath(__file__)) + "/../"
print(util_path)
sys.path.append(util_path)
from admin import RetconAdmin


app = Flask(__name__)
admin = RetconAdmin("UNKNOWN")

# file browser
app.config["FFE_BASE_DIRECTORY"] = util_path + '../artifacts'         # The directory the explorer is limited to
app.register_blueprint(file_explorer_bp, url_prefix='/file-explorer')   # Add the blueprint to the flask app
register_filters(app)                                                   # Register the filter

@app.route('/')
def index():
    return render_template("index.html", admin=admin)

@app.route('/wifi', methods=['POST'])
def wifi():
    try:
        post = json.loads(request.data)
        client_ap_ssid = post["client_ap_ssid"]
        client_ap_psk = post["client_ap_psk"]
        
        admin.client_ap_psk = client_ap_psk
        admin.client_ap_ssid = client_ap_ssid
        
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
    
@app.route('/reboot', methods=['POST'])
def reboot():
    post = json.loads(request.data)
    if post["reboot"] == "reboot":
        admin.reboot()
        return jsonify({ "message" : "rebooting", "status": "ok"})
    else:
        return jsonify({ "message" : "must POST with reboot='reboot'", "status": "error"})
    
@app.route('/toggle_ssh', methods=['POST'])
def toggle_ssh():
    admin.toggle_ssh()
    time.sleep(2)
    return jsonify({ "message" : f"SSH Enabled = {admin.ssh_enabled}", "status": "ok"})

@app.route('/set_time', methods=['POST'])
def set_time():
    print("set_time", request.data)
    post = json.loads(request.data)
    epoch = post.get("epoch", 0)
    if epoch > 1751917835 and epoch < 5000000000:
        result = admin.set_time(epoch)
        return jsonify({ "message" : "set", "status": "ok"})
    else:
        return jsonify({ "message" : f"{epoch} is not a valid unix epoch. Eopich must be int, and seconds. Must be between 1751917835 and  5000000000", "status": "error"})
   
   
@app.route('/reset_reticulum_config', methods=['POST'])
def reset_reticulum_config():
    print("RESETTING", request.data)
    post = json.loads(request.data)
    do_it = post.get("do_reset", 0)
    if do_it == 1:
        admin.reset_reticulum_config()
        time.sleep(1)
        admin.reboot()
        return jsonify({ "message" : "set", "status": "ok"})
    else:
        return jsonify({ "message" : "do_reset must be = 1"})
   
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