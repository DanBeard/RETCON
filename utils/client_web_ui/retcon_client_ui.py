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

@app.route('/api/mesh/status')
def mesh_status():
    """Get batman-adv mesh status for web UI display."""
    status = {
        "state": "unknown",
        "peer_count": 0,
        "bat0_ip": None,
        "interface": None,
        "bat0_up": False,
        "ibss_mode": False,
    }

    try:
        # Check if bat0 is up
        result = subprocess.run(
            "ip link show bat0 2>/dev/null | grep -q 'state UP\\|state UNKNOWN'",
            shell=True, capture_output=True
        )
        status["bat0_up"] = result.returncode == 0

        # Get bat0 IP address
        try:
            addrs = ni.ifaddresses("bat0")
            if ni.AF_INET in addrs:
                status["bat0_ip"] = addrs[ni.AF_INET][0].get("addr")
        except Exception:
            pass

        # Get peer count from batctl
        result = subprocess.run("batctl o 2>/dev/null", shell=True, capture_output=True)
        if result.returncode == 0:
            lines = result.stdout.decode().strip().split('\n')
            status["peer_count"] = max(0, len(lines) - 2)  # Subtract header lines

        # Check which interface is attached to batman-adv
        result = subprocess.run("batctl if 2>/dev/null", shell=True, capture_output=True)
        if result.returncode == 0:
            output = result.stdout.decode().strip()
            if output:
                # Parse "wlan0: active" format
                parts = output.split(':')
                if parts:
                    status["interface"] = parts[0].strip()

        # Check if interface is in IBSS mode
        if status["interface"]:
            result = subprocess.run(
                f"iw {status['interface']} info 2>/dev/null | grep -q 'type IBSS'",
                shell=True, capture_output=True
            )
            status["ibss_mode"] = result.returncode == 0

        # Determine overall state
        if status["bat0_up"] and status["ibss_mode"]:
            status["state"] = "running"
        elif status["bat0_up"] or status["interface"]:
            status["state"] = "degraded"
        else:
            status["state"] = "unconfigured"

    except Exception as e:
        status["error"] = str(e)
        status["state"] = "error"

    return jsonify(status)

@app.route('/api/bluetooth/status')
def bluetooth_status():
    """Get Bluetooth PAN status for web UI display."""
    status = {
        "state": "unknown",
        "bt_name": None,
        "pan_ip": "192.168.4.1",
        "connected_devices": 0,
    }

    try:
        # Check if bluetooth service is running
        result = subprocess.run(
            "systemctl is-active bluetooth",
            shell=True, capture_output=True
        )
        bt_active = result.returncode == 0

        # Check if bt-network service is running
        result = subprocess.run(
            "systemctl is-active bt-network",
            shell=True, capture_output=True
        )
        nap_active = result.returncode == 0

        # Get Bluetooth adapter name/alias
        result = subprocess.run(
            "bluetoothctl show 2>/dev/null | grep -E 'Alias|Name' | head -1 | cut -d' ' -f2-",
            shell=True, capture_output=True
        )
        if result.returncode == 0 and result.stdout:
            status["bt_name"] = result.stdout.decode().strip()

        # Get connected devices count
        result = subprocess.run(
            "bluetoothctl devices Connected 2>/dev/null",
            shell=True, capture_output=True
        )
        if result.returncode == 0:
            output = result.stdout.decode().strip()
            if output:
                status["connected_devices"] = len(output.split('\n'))

        # Determine overall state
        if bt_active and nap_active:
            status["state"] = "running"
        elif bt_active:
            status["state"] = "degraded"
        else:
            status["state"] = "unconfigured"

    except Exception as e:
        status["error"] = str(e)
        status["state"] = "error"

    return jsonify(status)

# main driver function
if __name__ == '__main__':

    if len(sys.argv) > 1:
        admin = RetconAdmin(sys.argv[1])

    try:
        # Use pan0 (Bluetooth PAN) interface for client UI access
        iface = "pan0"
        ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
        # run() method of Flask class runs the application
        # on the local development server.
        print(f"Running retcon UI on {ip} (Bluetooth PAN)")
        app.run(host=ip, port=80)
    except (ValueError, KeyError):
        print("ERROR Couldn't get netinfo for pan0. Assuming dev session and launching with default settings")
        app.run()