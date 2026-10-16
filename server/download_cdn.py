"""
Downloads one game version from the public Forsaken-AR-CDN repository into server/cdn/.
Files that are already present with the right size are skipped, so it can be re-run
if it gets interrupted.

Usage:
    python download_cdn.py [version]      (default 8.0.0, about 1.1 GB)
"""
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = "Forsaken-Gaming/Forsaken-AR-CDN"
RAW = "https://raw.githubusercontent.com/%s/main/" % REPO
HERE = os.path.dirname(os.path.abspath(__file__))
CDN_DIR = os.path.join(HERE, "cdn")
EXTRA = ["ssd_mobilenet_v2_coco_2018_03_29.mlmodel"]


def api(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def files_for(version):
    root = api("https://api.github.com/repos/%s/contents/" % REPO)
    sha = next(x["sha"] for x in root if x["name"] == version)
    tree = api("https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, sha))
    if tree.get("truncated"):
        sys.exit("GitHub truncated the file list; the download would be incomplete")
    out = [(version + "/" + x["path"], x["size"]) for x in tree["tree"] if x["type"] == "blob"]
    sizes = {x["name"]: x["size"] for x in root if x["type"] == "file"}
    out += [(name, sizes.get(name)) for name in EXTRA]
    return out


def fetch(item):
    rel, size = item
    dst = os.path.join(CDN_DIR, *rel.split("/"))
    if size is not None and os.path.exists(dst) and os.path.getsize(dst) == size:
        return 0
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(RAW + urllib.request.quote(rel), timeout=120) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            os.replace(tmp, dst)
            return os.path.getsize(dst)
        except OSError as e:
            print("retrying (%d): %s %s" % (attempt + 1, rel, e), flush=True)
    print("FAILED:", rel, flush=True)
    return 0


def main():
    version = sys.argv[1] if len(sys.argv) > 1 else "8.0.0"
    items = files_for(version)
    total = sum(s or 0 for _, s in items)
    print("%d files, %.2f GB" % (len(items), total / 1e9), flush=True)
    done = 0
    with ThreadPoolExecutor(4) as pool:
        for i, n in enumerate(pool.map(fetch, items), 1):
            done += n
            if i % 10 == 0 or i == len(items):
                print("%d/%d files, %.0f MB downloaded this run" % (i, len(items), done / 1e6), flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main()
