"""
RETCON administration utility — crns edition.

Speaks LXMF over the crns C++ reticulum stack via its python binding
(libcrns.so). The crns host owns the mesh interfaces declared in
~/.reticulum/config (same rnsd config format python rns uses); this console
is the application layer on top: an lxmf.delivery destination that receives
operator commands and replies.

meant to be run from main as a subprocess, not imported:
    python utils/admin.py <admin_name>

Requires: the crns python package on PYTHONPATH (vendored to
./python_packages/crns by install_retcon_locally.sh) and CRNS_LIBRARY
pointing at libcrns.so.
"""
import os
import sys
import asyncio
import time
import subprocess
import msgpack

# where the crns python package + libcrns.so were vendored by the installer.
# Paths must be set up before `from crns import ...` below.
UTILS_DIR = os.path.dirname(os.path.realpath(__file__))
REPO_ROOT = os.path.dirname(UTILS_DIR)
CRNS_LIB_DIR = os.path.join(REPO_ROOT, "crns_lib")
sys.path.insert(0, os.path.join(REPO_ROOT, "python_packages"))

if CRNS_LIB_DIR not in os.environ.get("CRNS_LIBRARY", ""):
    libs = sorted(os.listdir(CRNS_LIB_DIR)) if os.path.isdir(CRNS_LIB_DIR) else []
    if libs:
        os.environ["CRNS_LIBRARY"] = os.path.join(CRNS_LIB_DIR, libs[0])

from crns import (
    Reticulum,
    AnnounceHandler,
    Identity,
    Destination,
)

from rns_config_gen import get_recton_config

# LXMF announce app_data peer_data shape (LXMF/LXMRouter.py:get_announce_app_data):
#   [display_name_or_None, stamp_cost_or_None, [SF_COMPRESSION]]
SF_COMPRESSION = 0x00


def pack_display_name_app_data(display_name: str) -> bytes:
    """Pack the LXMF peer_data announce app_data so python clients see our
    display name in announces (what meshchat/nomadnet parse)."""
    return msgpack.packb([display_name, None, [SF_COMPRESSION]], use_bin_type=True)


class RetconAdmin:
    """ The actual admin functionality (config + OS level)"""

    def __init__(self, name):
        self.config = get_recton_config(None) # always the active profile
        self.name = name

    # write the config to the active profile
    def write_config(self):
        profile_path = os.path.join(REPO_ROOT, "retcon_profiles", "active")
        with open(profile_path, 'wb') as fout:
            self.config.write(fout)

    def reboot(self):
        # trigger the shutdown
        subprocess.Popen(f"sleep 3; sudo reboot",shell=True)

    def toggle_ssh(self):
        status = self.ssh_enabled

        # toggle it off or on
        if status:
            subprocess.Popen(f"sudo systemctl stop ssh", shell=True)
        else:
            subprocess.Popen(f"sudo systemctl start ssh", shell=True)

    def set_time(self, epoch):
        p = subprocess.Popen(f"sudo date -s '@{epoch}'", shell=True, stdout=subprocess.PIPE)
        out, err = p.communicate()
        return out

    def reset_reticulum_config(self):
        subprocess.Popen(f"cd ~/.reticulum && rm -rf `ls ~/.reticulum | grep -v interfaces`", shell=True)

    @property
    def ssh_enabled(self):
         p = subprocess.Popen("sudo systemctl status ssh", shell=True, stdout=subprocess.PIPE)
         out, err = p.communicate()
         return b"active (running)" in out

    @property
    def profile_name(self):
        return self.config['retcon'].get("name", "no name")

    @property
    def announce_every(self):
        return float(self.config['retcon'].get("announce_every", 10*60)) #announce every 10 mins

    @property
    def admins(self):
        return self.config['retcon'].get("admins","").split(",")

    @property
    def client_iface(self):
        return self.config['retcon']["wifi"].get("client_iface", None)

    @property
    def password(self):
        """A Passowrd to authenticate a user as an admin over an admin interface like LXMF or html"""
        return self.config['retcon'].get("password", None)

    @property
    def client_ap_psk(self):
        return self.config["retcon"]['wifi'].get('client_ap_psk',"")

    @client_ap_psk.setter
    def client_ap_psk(self, psk):
        self.config["retcon"]['wifi']['client_ap_psk'] = psk
        self.config["retcon"]['client_info_changed'] = True
        self.write_config()

    @property
    def client_ap_ssid(self):
        return self.config["retcon"]['wifi'].get('client_ap_prefix',"")

    @client_ap_ssid.setter
    def client_ap_ssid(self, ssid):
        self.config["retcon"]['wifi']['client_ap_prefix'] = ssid
        self.config["retcon"]['client_info_changed'] = True
        self.write_config()

    @property
    def client_info_changed(self):
        """
        Flag that indicates the client config has been changed by a user.
        Useful to know if we need to show Wizards or tips during setup
        """
        self.config["retcon"].get('client_info_changed', False)

    @property
    def is_transport(self):
        return self.config['retcon'].get("mode", "ui") == "transport"

    @property
    def config_str(self):
        with open(os.devnull, "wb") as sink:
            self.config.write(sink)
        # configobj writes to a file object; render through a temp file to
        # keep this free of third-party stream wrappers
        import io
        buf = io.BytesIO()
        self.config.write(buf)
        return buf.getvalue().decode()

    @config_str.setter
    def config_str(self, value:str):
        import io
        new_config = None
        buf = io.BytesIO(value.encode())
        # lazy import keeps ConfigObj usage identical to the python-rns era
        from configobj import ConfigObj
        new_config = ConfigObj(buf, interpolation=False)
        self.config = new_config
        self.write_config()

    def is_admin(self, user_id, password):
        return user_id in self.admins or (self.password is not None and password == self.password)

    @property
    def connected_ap(self):
        """ What AP are we connected to? (best-effort via nmcli)"""
        try:
            out = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,DEVICE,STATE", "con", "show", "--active"],
                capture_output=True, text=True, timeout=5
            ).stdout
            for line in out.splitlines():
                parts = line.split(":")
                if len(parts) >= 3 and "wlan" in parts[1]:
                    return parts[0]
            return None
        except Exception:
            return None


class LXMFAdminConsole:
    """
    The RETCON admin console over LXMF, backed by crns.

    Owns the crns Reticulum host (the loop thread lives in libcrns_host).
    Registers the lxmf.delivery destination, announces with the node's
    display name, receives admin commands, and replies opportunistically.
    """

    def __init__(self, admin: RetconAdmin):
        self.admin = admin
        self._response_queue = []
        self._announced_peers = {}
        self._identity_path = os.path.expanduser("~/retcon/storage/identity")

        os.makedirs(os.path.dirname(self._identity_path), exist_ok=True)

        # Bring the crns host up on the standard config dir. This parses the
        # same ~/.reticulum/config python rns used, and owns the interfaces.
        self.r = Reticulum("~/.reticulum")
        self.dest = self.r.register_destination(
            "lxmf.delivery", identity_file=self._identity_path
        )
        self.r.set_inbound_handler(self.on_lxmf_recv, destination=self.dest)
        self.r.register_announce_handler(self)
        # the loop thread must be running before any traffic flows
        self.r.start()

    # -- announce feed ---------------------------------------------------

    def received_announce(self, announce):
        """Track heard LXMF peers so replies know when a path is fresh."""
        self._announced_peers[announce.destination_hash] = time.time()

    # -- mesh file send ---------------------------------------------------

    # A single DIRECT LXMF message tops out at the packed-message bound
    # (0xFFFF on hosted crns profiles). The packed wire adds the LXMF header,
    # signature and bin headers, so keep the file payload well under it.
    SENDFILE_MAX_BYTES = 0xF000

    def send_file(self, dest_hash: bytes, path: str, title: str = ""):
        """Send a small file to a peer over the mesh via send_direct.

        Uses the crns Link+Resource path (rns-wire Resources, auto-chained
        across 32 KiB segments), so the transfer is reliable and concludes —
        returns the DirectSend handle so the caller can wait on it.

        Bound: SENDFILE_MAX_BYTES of payload per message (the packed LXMF
        ceiling is 0xFFFF; overhead eats the difference). Larger files need
        chunking or the dashboard download path instead.
        """
        path = os.path.realpath(os.path.expanduser(path))
        size = os.path.getsize(path)
        if size > self.SENDFILE_MAX_BYTES:
            raise ValueError(
                f"{size} bytes exceeds the {self.SENDFILE_MAX_BYTES} "
                "send_direct file bound — use the dashboard download path"
            )
        with open(path, "rb") as fin:
            content = fin.read()
        send = self.r.send_direct(
            dest_hash,
            content=content,
            title=(title or os.path.basename(path)).encode()[:64],
        )
        return send

    # -- command handling --------------------------------------------------

    def process_command(self, message:bytes):
        command, *rest = message.decode(errors="replace").strip().split(" ", 1)
        args = rest[0] if rest else ""
        command = command.lower()

        if command == "status":
            result = ""
            # crnsd doesn't ship a probe responder yet; report what the
            # binding can see: our identity, known paths, announce count.
            try:
                ident_hash = self.r.identity_hash().hex()
            except Exception:
                ident_hash = "?"
            result += f"node identity: {ident_hash}\n"
            result += f"destinations: {len(self.r._registered)}\n"
            result += f"heard announces: {len(self._announced_peers)}\n"
            result += "rnsh is not available on the crns transport; use this console"
            return result
        elif command == "peers":
            # heard LXMF destinations with rough freshness — what an operator
            # needs to pick a target for sendfile
            if not self._announced_peers:
                return "no peers heard yet"
            lines = []
            for dest, heard_at in sorted(
                self._announced_peers.items(), key=lambda kv: -kv[1]
            ):
                age = max(0, int(time.time() - heard_at))
                lines.append(f"{dest.hex()} (heard {age}s ago)")
            return "\n".join(lines)
        elif command == "sendfile":
            # sendfile <dest_hash_hex> <path> [title] — push a small file to
            # a peer over the mesh (Link + rns-wire Resources).
            parts = args.split()
            if len(parts) < 2:
                return "usage: sendfile <dest_hash_hex> <path> [title]"
            dest_hex, fpath = parts[0], parts[1]
            title = parts[2] if len(parts) > 2 else ""
            try:
                dest = bytes.fromhex(dest_hex)
            except ValueError:
                return "destination hash must be 32 hex characters"
            if len(dest) != 16 and len(dest) != 32:
                return "destination hash must be 32 hex characters (16 or 32 bytes)"
            if not self.r.has_path(dest):
                self.r.request_path(dest)
                return "no path yet — path request sent; try again shortly"
            try:
                send = self.send_file(dest, fpath, title)
            except ValueError as e:
                return f"refused: {e}"
            except Exception as e:
                return f"send failed: {e}"
            status = send.wait(90)
            return f"transfer {status.name if hasattr(status, 'name') else status}"
        elif command == "btpan":
            # opt-in wireless console: bluez NAP + dnsmasq on br-bt. Not
            # enabled by default (pairing ceremony + no iPhone client).
            sub = args.strip().lower()
            if sub == "on":
                subprocess.Popen("sudo systemctl start retcon-bt-nap.service retcon-bt-dnsmasq.service", shell=True)
                return "BT PAN starting on br-bt (10.56.0.1/24). Pair, join the PAN, then browse retcon.local."
            elif sub == "off":
                subprocess.Popen("sudo systemctl stop retcon-bt-nap.service retcon-bt-dnsmasq.service", shell=True)
                return "BT PAN stopped."
            else:
                return "usage: btpan on|off"
        else:
            return ("Welcome to the RETCON LXMF admin interface. Possible commands are: \n"
                            "status\n"
                            "peers\n"
                            "sendfile <dest_hash_hex> <path> [title]  (push a small file over the mesh)\n"
                            "btpan on|off  (wireless console over bluetooth PAN; iPhones not supported)")

    def on_lxmf_recv(self, message):
        reply_hash = message.source_hash
        response = self.process_command(message.content)
        self._response_queue.append((reply_hash, response))

    # -- main loop ----------------------------------------------------------

    async def loop(self):
        # Announce immediately, then on the configured cadence.
        last_announce = 0.0
        app_data = pack_display_name_app_data(self.admin.name)

        while True:
            r_q = self._response_queue
            self._response_queue = []
            for reply_hash, text in r_q:
                if self.r.has_path(reply_hash):
                    try:
                        self.r.send(reply_hash, text.encode(), title=b"RETCON console")
                    except Exception as e:
                        print("send failed:", e)
                else:
                    self.r.request_path(reply_hash)
                    self._response_queue.append((reply_hash, text))

            # announce when it's time
            now = time.time()
            if now - last_announce > self.admin.announce_every:
                print("announcing again!")
                self.r.announce(self.dest, app_data=app_data)
                last_announce = now

            await asyncio.sleep(2)


if __name__ == "__main__":
    name = sys.argv[1]
    admin = RetconAdmin(name)
    lxmf_admin = LXMFAdminConsole(admin)

    asyncio.run(lxmf_admin.loop())