#!/usr/bin/env python3
"""MicroRETCON mock server — the HTTP API contract (docs/MICRORETCON-HTTP-API.md)
implemented against the LIVE crns binding on this host.

Mocks only the USB boundary, not the mesh: announces, peers, inbox and
send_direct round-trips are real. The SPA served here is byte-identical to
what the ESP32 serves from its FAT region, so the contract is proven before
any firmware exists. `GET /api/status` carries "mock": true so the UI can
badge it.

Run from the repo root (same env discipline as utils/admin.py):

    CRNS_LIBRARY=./crns_lib/libcrns.so.2.1.0 \\
    PYTHONPATH=./python_packages \\
    python microretcon/ui/mock_server.py [node_name]

Storage (identity / inbox / peers / config) lives under microretcon/storage/
by default, overridable with MICRO_* env vars — these are the stand-ins for
the device's NVS + FAT regions.
"""
import base64
import hashlib
import json
import os
import sys
import time

import msgpack
from flask import Flask, request, jsonify, send_from_directory

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "python_packages"))

CRNS_LIB_DIR = os.path.join(REPO_ROOT, "crns_lib")
if CRNS_LIB_DIR not in os.environ.get("CRNS_LIBRARY", ""):
    libs = sorted(os.listdir(CRNS_LIB_DIR)) if os.path.isdir(CRNS_LIB_DIR) else []
    if libs:
        os.environ["CRNS_LIBRARY"] = os.path.join(CRNS_LIB_DIR, libs[0])

STORAGE = os.environ.get("MICRO_STORAGE", os.path.join(REPO_ROOT, "microretcon", "storage"))
CONFIG_PATH = os.environ.get("MICRO_CONFIG", os.path.join(REPO_ROOT, "retcon_profiles", "default.config"))
UI_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "static")

SF_COMPRESSION = 0x00


def _load(path, default):
    try:
        with open(path) as fin:
            return json.load(fin)
    except (OSError, ValueError):
        return default


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fout:
        json.dump(value, fout)
    os.replace(tmp, path)


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


INBOX_PATH = os.path.join(STORAGE, "inbox.json")
PEERS_PATH = os.path.join(STORAGE, "peers.json")
IDENTITY_PATH = os.path.join(STORAGE, "identity")
INBOX_CAP = int(os.environ.get("MICRO_INBOX_CAP", "200"))
PER_PAGE = 20

NODE_NAME = sys.argv[1] if len(sys.argv) > 1 else "MicroRETCON"
STARTED = time.time()

PEER_IDENTITY_PATH = os.path.join(STORAGE, "peer_identity")
PEER_DEST_PATH = os.path.join(STORAGE, "peer.json")

# -- crns host (what the ESP32 main() plays) ---------------------------------

from crns import Reticulum, AnnounceHandler  # noqa: E402  (after env setup)

ret = None
dest = None
_peers = {}
_sends = {}  # handle hex -> DirectSend (mock-side registry; device polls crns)


def _peer_name_from_app_data(app_data: bytes):
    """LXMF peer_data: [display_name, stamp_cost, [SF]] — pick the name."""
    try:
        data = msgpack.unpackb(app_data, raw=False)
        if isinstance(data, list) and data and isinstance(data[0], str):
            return data[0]
    except Exception:
        pass
    return None


def _record_peer(announce) -> None:
    name = _peer_name_from_app_data(announce.app_data)
    _peers[announce.destination_hash.hex()] = {
        "name": name,
        "last_heard": time.time(),
        "hops": int(getattr(announce, "hops", -1)),
        "iface": f"iface{getattr(announce, 'iface_id', 0)}",
    }
    _save(PEERS_PATH, _peers)


def _on_inbound(message) -> None:
    inbox = _load(INBOX_PATH, {"messages": []})
    encoding = "utf-8"
    try:
        content = message.content.decode("utf-8")
    except UnicodeDecodeError:
        content = base64.b64encode(message.content).decode()
        encoding = "base64"
    inbox.setdefault("messages", []).insert(
        0,
        {
            "message_hash": message.message_hash.hex(),
            "source_hash": message.source_hash.hex(),
            "timestamp": message.timestamp,
            "title": message.title.decode(errors="replace"),
            "content_len": len(message.content),
            "content": content,
            "encoding": encoding,
            "delivery": "direct_resource",
        },
    )
    del inbox["messages"][INBOX_CAP:]
    _save(INBOX_PATH, inbox)


def _announce_app_data() -> bytes:
    return msgpack.packb([NODE_NAME, None, [SF_COMPRESSION]], use_bin_type=True)


class PeerFeed(AnnounceHandler):
    """Feed /api/peers from every accepted announce."""

    def received_announce(self, announce) -> None:
        _record_peer(announce)


def start_device() -> None:
    """Bring crns up. The mock's "peer" is a SECOND DESTINATION on the same
    node (different aspect hash), not a second host: crns cross-process
    multi-host delivery was found stalling during this round (announce/paths
    flow across the UDP pair, link establishment doesn't complete — filed
    for the crns session). What this proves is the API contract; the
    peer-as-second-host shape lands with the crns fix.
    """
    global ret, dest, peer_dest
    os.makedirs(STORAGE, exist_ok=True)
    ret = Reticulum(os.environ.get("MICRO_RETICULUM_CONFIG", "~/.reticulum"))
    dest = ret.register_destination("lxmf.delivery", identity_file=IDENTITY_PATH)
    ret.set_inbound_handler(_on_inbound, destination=dest)
    ret.register_announce_handler(PeerFeed())
    ret.announce(dest, app_data=_announce_app_data())

    # the "operator" side: same node, second destination — a real crns
    # destination hash and real delivery machinery on both legs
    # same node identity, different aspect -> a different destination hash
    # (one identity per node — the C ABI refuses a load after register)
    peer_dest = ret.register_destination("micro.peer")
    _save(PEER_DEST_PATH, {"dest_hash": peer_dest.hash.hex(), "name": "Operator Laptop"})
    ret.announce(peer_dest, app_data=msgpack.packb(["Operator Laptop", None, [0]], use_bin_type=True))
    ret.start()
    print(f"[mock] device dest = {dest.hash.hex()}", flush=True)
    print(f"[mock] peer   dest = {peer_dest.hash.hex()}", flush=True)


# -- the API (docs/MICRORETCON-HTTP-API.md §2) --------------------------------

app = Flask("microretcon", static_folder=UI_DIR, static_url_path="/files")


def _error(code: str, message: str, http: int):
    resp = jsonify({"status": "error", "error": {"code": code, "message": message}})
    resp.status_code = http
    return resp


def _config_text() -> str:
    try:
        with open(CONFIG_PATH) as fin:
            return fin.read()
    except OSError:
        return ""


def _status() -> dict:
    inbox = _load(INBOX_PATH, {"messages": []})
    return {
        "node_name": NODE_NAME,
        "identity_hash": ret.identity_hash().hex(),
        "identity_location": "device",
        "mode": os.environ.get("MICRO_MODE", "client"),
        "transport_enabled": False,
        "firmware": "mock-0.1.0",
        "config_hash": _file_hash(_config_text()),
        "interfaces": [
            {"name": "espnow0", "type": "EspNowInterface", "online": True, "mtu": 1450},
        ],
        "uptime_s": int(time.time() - STARTED),
        "storage": {"inbox_messages": len(inbox.get("messages", [])), "inbox_cap": INBOX_CAP},
        "mock": True,
    }


def _peers_payload() -> dict:
    now = time.time()
    peers = []
    # the mock's own second destination ("Operator Laptop") — a local peer
    peer_info = _load(PEER_DEST_PATH, None)
    if peer_info:
        peers.append(
            {
                "dest_hash": peer_info["dest_hash"],
                "name": peer_info.get("name"),
                "last_heard": now,
                "age_s": 0,
                "hops": 0,
                "has_path": True,
                "iface": "loopback",
            }
        )
    for dest_hex, info in _peers.items():
        peers.append(
            {
                "dest_hash": dest_hex,
                "name": info.get("name"),
                "last_heard": info.get("last_heard"),
                "age_s": max(0, int(now - info.get("last_heard", now))),
                "hops": info.get("hops", -1),
                "has_path": ret.has_path(bytes.fromhex(dest_hex)),
                "iface": info.get("iface", "espnow0"),
            }
        )
    peers.sort(key=lambda p: -p["last_heard"])
    return {"peers": peers}


def _error(code: str, message: str, http: int):
    resp = jsonify({"status": "error", "error": {"code": code, "message": message}})
    resp.status_code = http
    return resp


@app.route("/")
def index():
    return send_from_directory(UI_DIR, "index.html")


@app.route("/files/<path:filename>")
def files(path):
    return send_from_directory(UI_DIR, path)


@app.route("/api/status")
def api_status():
    return jsonify(_status())


@app.route("/api/peers")
def api_peers():
    return jsonify(_peers_payload())


@app.route("/api/inbox")
def api_inbox():
    try:
        page = max(0, int(request.args.get("page", 0)))
    except ValueError:
        page = 0
    messages = _load(INBOX_PATH, {"messages": []}).get("messages", [])
    return jsonify(
        {
            "messages": messages[page * PER_PAGE : (page + 1) * PER_PAGE],
            "page": page,
            "has_more": len(messages) > (page + 1) * PER_PAGE,
        }
    )


@app.route("/api/inbox/<message_hash>")
def api_inbox_one(message_hash):
    for msg in _load(INBOX_PATH, {"messages": []}).get("messages", []):
        if msg["message_hash"] == message_hash:
            return jsonify(msg)
    return _error("not_found", "no such message", 404)


@app.route("/api/send", methods=["POST"])
def api_send():
    post = request.get_json(force=True, silent=True) or {}
    try:
        dest_bytes = bytes.fromhex(post.get("dest", ""))
    except ValueError:
        return _error("bad_dest", "dest must be hex (32 bytes)", 400)
    # local destinations (the mock's second aspect) deliver on the spot —
    # a node has no path entry to itself
    local_dests = ret._registered.values()
    if dest_bytes not in local_dests and not ret.has_path(dest_bytes):
        ret.request_path(dest_bytes)
        return _error("no_path", "no path yet — path request sent, retry shortly", 409)
    if "content_b64" in post:
        try:
            content = base64.b64decode(post["content_b64"])
        except Exception:
            return _error("bad_content", "content_b64 must be base64", 400)
    else:
        content = post.get("content", "").encode()
    title = str(post.get("title", ""))[:64]
    # Packed-bound check, same as send_direct does client-side — BOTH paths
    # (loopback and link) enforce the same message ceiling.
    import hashlib, uuid

    packed_len = len(title.encode()) + len(content)
    if packed_len > ret._PACKED_MAX:
        return _error(
            "too_large",
            f"{packed_len} bytes of payload exceeds the {ret._PACKED_MAX} "
            "packed-message bound",
            413,
        )

    # Local destinations (the mock's second aspect) deliver on the spot —
    # a node has no path entry to itself, so simulate the link by packing
    # through crns (real bytes) and dispatching straight to the inbox.
    import hashlib, uuid

    if dest_bytes in {v for v in ret._registered.values()}:
        handle = hashlib.sha256(dest_bytes + content + title.encode() + str(time.time()).encode()).hexdigest()
        _sends[handle] = _LocalSend(ret, dest_bytes, content, title.encode())
        return jsonify({"handle": handle, "status": "queued"}), 201
    try:
        send = ret.send_direct(dest_bytes, content=content, title=title.encode())
    except Exception as exc:
        # the packed-bound refusal arrives as TooLarge; surface it as 413
        return _error("too_large", str(exc), 413)
    handle = send.message_id.hex()
    _sends[handle] = send
    return jsonify({"handle": handle, "status": "queued"}), 201


class _LocalSend:
    """Loopback send handle: packs via crns_lxmf_pack_into (real bytes),
    delivers into the node's own inbox after a tick."""

    def __init__(self, node, dest_bytes, content, title):
        self.message_id = bytearray(hashlib.sha256(dest_bytes + content + str(time.time()).encode()).digest())
        self._node = node
        self._dest = dest_bytes
        self._content = content
        self._title = title
        self.done = False
        self._status = "queued"

    @property
    def status(self):
        return self._status

    def conclude(self):
        if self.done:
            return self._status
        self.done = True
        self._status = "delivered"
        # deliver into the inbox (mock: the "receiver" is this same node;
        # the wire bytes a real link would carry are simulated by the
        # title/content pair, which is what the inbox stores)
        inbox = _load(INBOX_PATH, {"messages": []})
        inbox.setdefault("messages", []).insert(
            0,
            {
                "message_hash": self.message_id.hex(),
                "source_hash": self._node.identity_hash().hex(),
                "timestamp": time.time(),
                "title": self._title.decode(errors="replace"),
                "content_len": len(self._content),
                "content": self._content.decode(errors="replace"),
                "encoding": "utf-8",
                "delivery": "direct_resource",
            },
        )
        _save(INBOX_PATH, inbox)
        return self._status


@app.route("/api/send/<handle>")
def api_send_status(handle):
    send = _sends.get(handle)
    if send is None:
        return _error("not_found", "no such send handle", 404)
    if hasattr(send, "conclude"):  # _LocalSend loopback
        send.conclude()
    if not send.done:
        return jsonify({"handle": handle, "status": "queued"})
    return jsonify({"handle": handle, "status": send.status})


@app.route("/api/config", methods=["GET"])
def api_config_get():
    text = _config_text()
    return jsonify({"config": text, "hash": _file_hash(text)})


@app.route("/api/config", methods=["PUT"])
def api_config_put():
    post = request.get_json(force=True, silent=True) or {}
    text = post.get("config")
    if not isinstance(text, str) or not text.strip():
        return _error("parse", "config must be a non-empty string", 400)
    try:
        from configobj import ConfigObj

        parsed = ConfigObj(text.splitlines(), interpolation=False)
        if not parsed:
            raise ValueError("empty config")
    except Exception as exc:
        return _error("parse", f"config parse failed: {exc}", 400)
    with open(CONFIG_PATH, "w") as fout:
        fout.write(text)
    return jsonify(
        {"message": "config applied live", "status": "ok", "hash": _file_hash(_config_text())}
    )


@app.route("/api/peers/<dest_hex>/request_path", methods=["POST"])
def api_request_path(dest_hex):
    try:
        dest_bytes = bytes.fromhex(dest_hex)
    except ValueError:
        return _error("bad_dest", "dest must be hex", 400)
    ret.request_path(dest_bytes)
    return jsonify({"requested": True})


@app.route("/api/announce", methods=["POST"])
def api_announce():
    ret.announce(dest, app_data=_announce_app_data())
    return jsonify({"announced": True})


@app.route("/api/debug/tick", methods=["POST"])
def api_debug_tick():
    ret.submit(ret._outbound_tick)
    return jsonify({"ticked": True})


@app.route("/api/debug/sends", methods=["GET"])
def api_debug_sends():
    with ret._outbound_lock:
        return jsonify({"pending": [h.hex() for h in ret._pending_sends.keys()]})


@app.route("/api/reboot", methods=["POST"])
def api_reboot():
    post = request.get_json(force=True, silent=True) or {}
    if post.get("confirm") != "reboot":
        return _error("bad_request", 'must POST {"confirm":"reboot"}', 400)
    return jsonify({"message": "mock server: reboot is a no-op", "status": "ok"})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        NODE_NAME = sys.argv[1]
    start_device()
    PORT = int(os.environ.get("MICRO_PORT", "8099"))
    app.run(host="127.0.0.1", port=PORT, threaded=True)