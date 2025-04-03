# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
import netifaces as ni
from flask import Flask
import os


dir_path = os.path.dirname(os.path.realpath(__file__) + "../")

# Flask constructor takes the name of 
# current module (__name__) as argument.
app = Flask(__name__)

# The route() function of the Flask class is a decorator, 
# which tells the application which URL should call 
# the associated function.
@app.route('/')
# ‘/’ URL is bound with hello_world() function.
def hello_world():
    return 'Hello World'

# main driver function
if __name__ == '__main__':
    iface = "uap0"
    ip = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
    # run() method of Flask class runs the application 
    # on the local development server.
    app.run(host=ip,port=80)