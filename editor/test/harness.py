"""
Tests the editor UI without a phone.

Serves the page with a fake Android bridge (window.Android over synchronous XHR),
uses test/data like the phone's FNAFAR_server folder, runs headless Edge with the
?test=1 scenario and prints the results the page writes.

Setup:  copy cdn/8.0.0/Masterdata/800 and a save/state.json into test/data first.
Usage:  python harness.py
"""
import os
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
APP = os.path.join(os.path.dirname(HERE), "assets", "index.html")
SCENARIO = os.path.join(HERE, "scenario.js")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 8765

MOCK = """<script>
function _x(m, u, b) { var r = new XMLHttpRequest(); r.open(m, u, false); r.send(b || null); return r; }
window.Android = {
  basePath: function () { return "/sdcard/FNAFAR_server"; },
  hasPermission: function () { return true; },
  exists: function (p) { return _x("GET", "/__read?p=" + encodeURIComponent(p)).status == 200; },
  read: function (p) { var r = _x("GET", "/__read?p=" + encodeURIComponent(p)); return r.status == 200 ? r.responseText : null; },
  write: function (p, c) { return _x("POST", "/__write?p=" + encodeURIComponent(p), c).responseText; }
};
window.confirm = function () { return true; };
</script>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/plain; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/__read":
            f = os.path.join(DATA, q["p"][0])
            if os.path.isfile(f):
                return self.send(200, open(f, encoding="utf-8").read())
            return self.send(404, "")
        html = open(APP, encoding="utf-8").read().replace("<head>", "<head>" + MOCK, 1)
        if "test=1" in u.query:
            html = html.replace("</body>", "<script>" + open(SCENARIO, encoding="utf-8").read() + "</script></body>")
        self.send(200, html, "text/html; charset=utf-8")

    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")
        f = os.path.join(DATA, q["p"][0])
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(body)
        self.send(200, "")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run",
                          "--user-data-dir=" + os.path.join(HERE, ".edge"),
                          "--virtual-time-budget=15000", "--dump-dom",
                          "http://127.0.0.1:%d/?test=1" % PORT],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    dom = out.stdout
    start, end = dom.find('<pre id="testout">'), dom.find("</pre>", dom.find('<pre id="testout">'))
    print(dom[start + 18:end] if start >= 0 else "NO RESULT\n" + dom[:2000] + out.stderr[-2000:])
    server.shutdown()
    sys.exit(0 if start >= 0 and "FAIL" not in dom[start:end] else 1)
