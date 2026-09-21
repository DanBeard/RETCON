import netifaces as ni
import json 
from flask import Flask, render_template, request, jsonify, abort
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
    
# ---- MicroRETCON board flashing (RAK4631 UF2) ----
MICRORETCON_FW_DIR = os.path.join(util_path, "..", "artifacts", "firmware", "microretcon")

def _latest_uf2():
    """Newest microretcon UF2 in the artifacts tree, or None."""
    d = MICRORETCON_FW_DIR
    if not os.path.isdir(d):
        return None
    cands = sorted(
        (f for f in os.listdir(d) if f.endswith(".uf2")),
        key=lambda f: os.path.getmtime(os.path.join(d, f)),
        reverse=True,
    )
    return os.path.join(d, cands[0]) if cands else None

def _uf2_drives():
    """Mounted drives that look like a UF2 bootloader (RAK4631 double-tap
    reset). The universal marker is INFO_UF2.TXT at the drive root."""
    import glob
    drives = []
    for m in glob.glob("/media/*/*") + glob.glob("/media/*") + glob.glob("/run/media/*/*") + glob.glob("/mnt/*"):
        if os.path.isfile(os.path.join(m, "INFO_UF2.TXT")):
            drives.append(m)
    return sorted(set(drives))

def _rak_serial_ports():
    """USB serial ports that are a RAK4631 in application mode
    (Adafruit VID 0x239A, RAK4631 PIDs 0029/002A/8029/802A)."""
    import serial.tools.list_ports
    pids = {0x0029, 0x002A, 0x8029, 0x802A}
    return [
        {"device": p.device, "desc": p.description}
        for p in serial.tools.list_ports.comports()
        if p.vid == 0x239A and p.pid in pids
    ]

@app.route('/flash')
def flash_page():
    return render_template("flash.html",
        uf2=_latest_uf2(),
        uf2_name=os.path.basename(_latest_uf2() or "") or None,
        drives=_uf2_drives(),
        ports=_rak_serial_ports())

@app.route('/flash/uf2')
def flash_uf2_download():
    """Serve the baked UF2 (the file the UI copies / the user drags)."""
    uf2 = _latest_uf2()
    if not uf2:
        abort(404)
    from flask import send_file
    return send_file(uf2, as_attachment=True,
                     download_name=os.path.basename(uf2))

@app.route('/flash/scan')
def flash_scan():
    """Re-scan for UF2 bootloader drives + serial ports (polled by the page)."""
    return jsonify({"drives": _uf2_drives(), "ports": _rak_serial_ports()})

@app.route('/flash/copy', methods=['POST'])
def flash_copy():
    """Copy the baked UF2 onto a detected UF2 drive. This is the flash —
    the board's bootloader takes the file, verifies, and reboots."""
    data = request.get_json(force=True, silent=True) or {}
    drive = data.get("drive", "")
    uf2 = _latest_uf2()
    if not uf2:
        return jsonify({"message": "no microretcon UF2 in artifacts (build with microretcon/firmware/rak/build-uf2.sh)", "status": "error"})
    # guard: the drive must actually be a UF2 bootloader mount
    if drive not in _uf2_drives():
        return jsonify({"message": f"{drive} is not a UF2 bootloader drive (no INFO_UF2.TXT)", "status": "error"})
    dst = os.path.join(drive, os.path.basename(uf2))
    try:
        import shutil
        shutil.copyfile(uf2, dst)
        # give the umount a beat; the board self-resets after flashing
        time.sleep(2)
        return jsonify({"message": f"copied {os.path.basename(uf2)} to {drive} — the board reboots itself when the write completes", "status": "ok"})
    except Exception as e:
        return jsonify({"message": str(e), "status": "error"})

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
        print(f"Running retcon UI on {ip}")
        app.run(host=ip,port=80)
    except ValueError:
        print("ERROR Couldn't get netinfo for uap. Assuming dev session and launching with default settings")
        app.run()