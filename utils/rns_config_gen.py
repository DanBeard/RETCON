import os
import sys
import importlib.util
from jinja2 import Environment, Template
from typing import Optional
from io import BytesIO
from configobj import ConfigObj

dir_path = os.path.dirname(os.path.realpath(__file__)) + "/.."

def get_recton_config(retcon_profile: Optional[str] = None):
    profile_path = (retcon_profile + ".config") if retcon_profile is not None else "active"
    profile_path = dir_path + "/retcon_profiles/" + profile_path
    return ConfigObj(profile_path, interpolation=False)

def generate_rns_config(plugins: dict, retcon_profile: Optional[str] = None):
    """Generate an RNS config file based on the retcon config"""   
    
    with open(dir_path+"/templates/reticulum.config") as f:
        t_str = f.read()
    
    # read the rns config template    
    template = Template(t_str)
    
    # parse the retcon config
    config = get_recton_config(retcon_profile)
   
    mode = config["retcon"]["mode"]
    # generate the values
    enable_transport = "yes" if mode == "transport" else "no"
    plugin_interfaces = ""
    hardcoded_interfaces = config.get('interfaces', None)
    
    if hardcoded_interfaces is not None:
        # configObj doesn't give us access to the string that built a section
        # so we have to be hacky and re-construc it from the parsed section dict
        section_config = ConfigObj()
        section_config.merge(hardcoded_interfaces)
        with BytesIO() as fout:
            section_config.write(fout)
            hardcoded_interfaces = fout.getvalue().decode()
        
    
    for plugin in plugins.values():
        template_vars = plugin.get_config()
        # right now just plugin config, but maybe more later
        plugin_interfaces += template_vars.get("plugin_interfaces","")
        
    return template.render(enable_transport=enable_transport, 
                           plugin_interfaces=plugin_interfaces, 
                           hardcoded_interfaces="" if hardcoded_interfaces is None else hardcoded_interfaces
                           )

