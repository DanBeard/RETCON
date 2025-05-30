import time
from jinja2 import Template
import meshtastic 
import meshtastic.serial_interface
from .base_plugin import RetconPlugin

meshtastic_config_template = """
  [[Meshtastic Interface]]
    type = Meshtastic_Interface
    enabled = true
    #mode = roaming
    port = {{port}}  # Optional: Meshtastic serial device port
    #ble_port = short_1234  # Optional: Meshtastic BLE device ID (Replacement for serial port)
    #tcp_port = 10.0.0.246  #Optional: Meshtastic TCP IP. [port is optional if using default port] (Replacement for serial or ble)
    data_speed = {{data_speed}}  # Radio speed setting desired for the network(do not use long-fast)
    hop_limit = {{hop_limit}}

"""

rnode_config_template = """
  [[RnodeUSB]]
    type = RNodeInterface
    interface_enabled = true
    #mode = roaming
    port = {{port}}
    frequency = {{frequency}}
    bandwidth = {{bandwidth}}
    txpower = {{txpower}}
    spreadingfactor = {{spreadingfactor}}
    codingrate = {{codingrate}}
    name = RnodeUSB

"""


class UsbAutodetectPlugin(RetconPlugin):

    PLUGIN_NAME = "usb_autodetect"
    
    # plugin config code. Take the config object, the template string
    # and return any Jinja vars in reticulum.config template
    # (for example) plugin_interfaces
    def get_config(self) -> dict:
        print("loading meshtastic plugin..........")
        
        # the string we're going to append to rns config
        interface_str = ""
        
        meshtastic_interface_config = self.config.get("meshtastic", None)
        meshtastic_port = None
        if meshtastic_interface_config is not None:
            ports = meshtastic.util.findPorts(True) # likely ports
            
            # try to connect o each likely port and see if we get meshtastic data back
            for port in ports:
                if meshtastic_port is None: 
                    try:
                        print(f"Trying to connect meshtastic to {port}")
                        conn = meshtastic.serial_interface.SerialInterface(port)
                        time.sleep(1)
                        if conn.getMyNodeInfo() is not None:
                            meshtastic_port = port
                        conn.close()
                    except Exception as e:
                        print(f"Couldn't connect to {port}. Got exception {e}")
                
                
            if meshtastic_port is None:
                interface_str += "\n\n  # Could not include Meshtastic device. "\
                    f"No verified port among {ports} \n"
            else:
                interface_str += "\n\n" + Template(meshtastic_config_template).render(
                port=meshtastic_port,
                **meshtastic_interface_config
            )
            
        rnode_interface_config = self.config.get("rnode", None)
        if rnode_interface_config is not None:
            ports = meshtastic.util.findPorts(True) # likely ports, same as meshtastic
            # remove the meshtastic port
            if meshtastic_port is not None:
                ports = [x for x in ports if x != meshtastic_port]
                
                
            if len(ports) == 0:
                interface_str += "\n  # No Rnode ports attached. "
            else:
                if len(ports) > 1:
                    interface_str += "\n  # Warning, more than one possible RNode port. "\
                        f"Trying first in list: {ports}"
                    
                interface_str += "\n\n" + Template(rnode_config_template).render(
                    port=ports[0],
                    **rnode_interface_config
                )
            
        
        return {
            "plugin_interfaces" : interface_str
        }
        
    # An init function that will get called on RETCON startup for init/bootstrapping
    def init(self) -> None:
        pass
