import typing

class RetconPlugin:
    
    PLUGIN_NAME = "BASE"
    
    def __init__(self, node_ssid: str, plugin_config : dict, retcon_config: dict, restart_rnsd:typing.Callable):
        self.node_ssid = node_ssid.encode()
        self.config = plugin_config
        self.retcon_config = retcon_config
        self.restart_rnsd = restart_rnsd
        
    # plugin code. Take the config object, the template string
    # and return any Jinja vars in reticulum.config template
    # (for example) plugin_interfaces
    def get_config(self) -> dict:
        return {
            "plugin_interfaces" : ""  # interface customization here
        }
        
        
    async def loop(self):
        pass
    
    # An init function that will get called on RETCON startup for init/bootstrapping
    def init(self) -> typing.Union[None, typing.Coroutine]:
        pass