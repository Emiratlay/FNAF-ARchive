"""
Local PlayFab server for FNAF AR 8.0.0 (FNaF ARchive build).

The patched APK sends every PlayFab request to http://127.0.0.1:9000.
- PC mode:    "adb reverse tcp:9000 tcp:9000" forwards that address to this PC over USB.
- Phone mode: this script runs on the phone itself (Termux), so no forwarding is needed.

Modes:
  record   Forwards requests to the real PlayFab title (internet required) and saves
           every request/response to captures/. Useful to study new server calls.
  offline  Never touches the internet. Game logic lives in game.py, the player save
           in save/state.json and game assets are served from cdn/.

Usage:
  python server.py record
  python server.py offline
Standard library only (runs on Windows, Linux and Termux).
"""
import gzip
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import game

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURES = os.path.join(HERE, "captures")
SAVE = os.path.join(HERE, "save")
CDN_DIR = os.path.join(HERE, "cdn")
SETTINGS_FILE = os.path.join(HERE, "settings.json")
PORT = int(os.environ.get("PORT", "9000"))

DEFAULT_SETTINGS = {
    # Learned automatically from the login request in record mode.
    "title_id": "",
    # URLs in responses that are rewritten to the local CDN, so the phone never
    # caches the online CDN address (it would get stuck loading when offline).
    "cdn_rewrite": {
        "https://raw.githubusercontent.com/Forsaken-Gaming/Forsaken-AR-CDN/main/": "http://127.0.0.1:9000/cdn/",
    },
}

FORWARD_HEADERS = ("Content-Type", "Content-Encoding", "X-Authorization",
                   "X-EntityToken", "X-SecretKey", "X-PlayFabSDK", "X-ReportErrorAsSuccess")

lock = threading.Lock()


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


settings = dict(DEFAULT_SETTINGS, **load_json(SETTINGS_FILE, {}))


def decode_body(raw, encoding):
    if encoding and "gzip" in encoding.lower():
        raw = gzip.decompress(raw)
    try:
        return json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        return None


def capture_key(path, req):
    """Capture file name: API path + CloudScript function name (if any)."""
    name = path.split("?")[0].strip("/").replace("/", "_")
    if isinstance(req, dict) and req.get("FunctionName"):
        name += "__" + str(req["FunctionName"])
    # Strip characters that are not allowed in Windows file names.
    return "".join(c if c.isalnum() or c in "_-." else "_" for c in name)


def param_hash(req):
    if not isinstance(req, dict):
        return ""
    p = req.get("FunctionParameter", req)
    return hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:10]


def find_urls(obj, out):
    if isinstance(obj, str):
        if obj.startswith("http://") or obj.startswith("https://"):
            out.add(obj)
        elif obj[:1] in "{[":
            try:
                find_urls(json.loads(obj), out)
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            find_urls(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_urls(v, out)


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with lock, open(os.path.join(HERE, "server.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- record

def record(path, full_path, raw, headers, req):
    title_id = settings.get("title_id")
    if isinstance(req, dict) and req.get("TitleId") and req["TitleId"] != title_id:
        title_id = settings["title_id"] = req["TitleId"]
        save_json(SETTINGS_FILE, settings)
        log("Learned TitleId: " + title_id)
    if not title_id:
        return 503, {"code": 503, "status": "ServiceUnavailable",
                     "error": "NoTitleId", "errorMessage": "TitleId not known yet"}

    url = "https://%s.playfabapi.com%s" % (title_id, full_path)
    fwd = {k: headers[k] for k in FORWARD_HEADERS if headers.get(k)}
    request = urllib.request.Request(url, data=raw, headers=fwd, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            status, body, enc = r.status, r.read(), r.headers.get("Content-Encoding")
    except urllib.error.HTTPError as e:
        status, body, enc = e.code, e.read(), e.headers.get("Content-Encoding")
    resp = decode_body(body, enc)

    key = capture_key(path, req)
    entry = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "path": path,
             "request": req, "status": status, "response": resp}
    with lock:
        lst = load_json(os.path.join(CAPTURES, key + ".json"), [])
        lst.append(entry)
        save_json(os.path.join(CAPTURES, key + ".json"), lst)
        urls = set()
        find_urls(resp, urls)
        if urls:
            known_path = os.path.join(CAPTURES, "urls.txt")
            known = set(open(known_path, encoding="utf-8").read().split()) if os.path.exists(known_path) else set()
            with open(known_path, "a", encoding="utf-8") as f:
                for u in sorted(urls - known):
                    f.write(u + "\n")
    return status, resp


# ---------------------------------------------------------------- offline

def ok(data):
    return 200, {"code": 200, "status": "OK", "data": data}


def replay(path, req):
    """Recorded response for the same request, else the latest one for that API/function."""
    lst = load_json(os.path.join(CAPTURES, capture_key(path, req) + ".json"), [])
    if not lst:
        return None
    h = param_hash(req)
    for e in reversed(lst):
        if param_hash(e["request"]) == h:
            return e
    return lst[-1]


def rewrite_cdn(obj):
    rules = settings.get("cdn_rewrite") or {}
    if not rules:
        return obj
    s = json.dumps(obj)
    for old, new in rules.items():
        s = s.replace(old, new)
    return json.loads(s)


def recorded_ids():
    """Player ids from record mode (swapped for the local player in replayed responses)."""
    lst = load_json(os.path.join(CAPTURES, "Client_LoginWithCustomID.json"), [])
    d = ((lst[0].get("response") or {}).get("data") or {}) if lst else {}
    ent = ((d.get("EntityToken") or {}).get("Entity") or {}).get("Id")
    return {"PlayFabId": d.get("PlayFabId"), "TitlePlayerId": ent}


def with_player_ids(obj):
    s = json.dumps(obj)
    state = game.load_state()
    for k, old in recorded_ids().items():
        if old:
            s = s.replace(old, state[k])
    return json.loads(s)


def offline(path, req):
    result = game.handle(path, req)
    if result is not None:
        return result[0], rewrite_cdn(result[1])

    # No game logic for this call yet: replay a recorded response if there is one.
    req = req if isinstance(req, dict) else {}
    e = replay(path, req)
    if e:
        log("  ~~ REPLAY (no logic): %s %s" % (path, req.get("FunctionName", "")))
        return e["status"], rewrite_cdn(with_player_ids(e["response"]))

    if path in ("/Client/ExecuteCloudScript", "/CloudScript/ExecuteEntityCloudScript"):
        log("  !! NOT IMPLEMENTED: CloudScript %s -> empty response" % req.get("FunctionName"))
        fr = dict(req.get("FunctionParameter") or {})
        fr.update({"scriptData": {"ProfileRead": {}, "ProfileWrite": {}}, "scriptError": {}})
        return ok({"FunctionName": req.get("FunctionName"), "Revision": 1, "FunctionResult": fr,
                   "Logs": [], "ExecutionTimeSeconds": 0.01, "ProcessorTimeSeconds": 0,
                   "MemoryConsumedBytes": 0, "APIRequestsIssued": 0, "HttpRequestsIssued": 0})
    log("  !! NOT IMPLEMENTED: %s -> empty response" % path)
    return ok({})


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_json(self, status, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/cdn/8.0.0/Masterdata/"):
            # Master data is served merged with custom content, whatever the version folder.
            body = game.masterdata_bytes(self.path.split("?")[0].rsplit("/", 1)[-1])
            if body is not None:
                log("CDN " + self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        if self.path.startswith("/cdn/"):
            rel = urllib.request.url2pathname(self.path[5:].split("?")[0])
            full = os.path.normpath(os.path.join(CDN_DIR, rel))
            if full.startswith(CDN_DIR) and os.path.isfile(full):
                log("CDN " + self.path)
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(os.path.getsize(full)))
                self.end_headers()
                with open(full, "rb") as f:
                    while True:
                        chunk = f.read(1 << 20)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                return
            log("CDN MISSING " + self.path)
            self.send_error(404)
            return
        self.send_json(200, {"server": "FNAF AR local", "mode": MODE})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        req = decode_body(raw, self.headers.get("Content-Encoding"))
        path = self.path.split("?")[0]
        name = path + (" [%s]" % req.get("FunctionName") if isinstance(req, dict) and req.get("FunctionName") else "")
        try:
            if MODE == "record":
                status, resp = record(path, self.path, raw, self.headers, req)
                # The phone caches the CDN address; give it the local one in record mode
                # too, so switching to offline later does not get stuck on the online URL.
                resp = rewrite_cdn(resp)
            else:
                status, resp = offline(path, req)
        except Exception as ex:  # a server bug must not hang the game; log it
            log("ERROR %s: %r" % (name, ex))
            status, resp = 500, {"code": 500, "status": "InternalServerError",
                                 "error": "LocalServerError", "errorMessage": str(ex)}
        log("%s %s -> %s" % (MODE, name, status))
        self.send_json(status, resp)


MODE = "offline"

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("record", "offline"):
        sys.exit(__doc__)
    MODE = sys.argv[1]
    for d in (CAPTURES, SAVE, CDN_DIR):
        os.makedirs(d, exist_ok=True)
    log("Server started: mode=%s port=%d" % (MODE, PORT))
    # On Windows SO_REUSEADDR lets two servers share a port: turn it off so a second
    # window fails loudly. On Linux/Termux keep it on, otherwise a quick restart
    # reports the port as busy for a while.
    ThreadingHTTPServer.allow_reuse_address = os.name != "nt"
    try:
        # Accept connections from this device only (adb reverse also arrives on localhost).
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        sys.exit("Port %d is busy. Close the other server window and try again." % PORT)
    server.serve_forever()
