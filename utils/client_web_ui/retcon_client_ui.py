import netifaces as ni
from flask import Flask, render_template
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
    return render_template("index.html")

@app.route('/reboot')
def reboot():
    admin.reboot()
    return render_template("index.html")

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