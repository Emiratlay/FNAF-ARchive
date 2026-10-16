"""
Downloads the third-party tools this project needs into tools/ (Windows x64).

    python tools/setup_tools.py            Java runtime, uber-apk-signer, adb (platform-tools)
    python tools/setup_tools.py --editor   also JDK 17 + Android build-tools 34 + platform 26,
                                           needed only to build the editor app yourself

Sources: Eclipse Adoptium (Java), github.com/patrickfav/uber-apk-signer and
dl.google.com (Android SDK packages, subject to the Android SDK license terms).
"""
import io
import os
import sys
import urllib.request
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))

BASE = [
    ("Java 17 runtime", "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jre/hotspot/normal/eclipse",
     TOOLS, "jdk-*-jre"),
    ("uber-apk-signer", "https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar",
     os.path.join(TOOLS, "uber-apk-signer.jar"), None),
    ("adb (platform-tools)", "https://dl.google.com/android/repository/platform-tools-latest-windows.zip",
     TOOLS, "platform-tools"),
]
EDITOR = [
    ("JDK 17", "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse",
     TOOLS, "jdk-17*[!e]"),
    ("Android build-tools 34", "https://dl.google.com/android/repository/build-tools_r34-windows.zip",
     os.path.join(TOOLS, "android-sdk"), "android-14"),
    ("Android platform 26", "https://dl.google.com/android/repository/platform-26_r02.zip",
     os.path.join(TOOLS, "android-sdk"), "android-8.0.0"),
]


def present(dest, marker):
    import glob
    if marker is None:
        return os.path.isfile(dest)
    return bool(glob.glob(os.path.join(dest, marker)))


def fetch(name, url, dest, marker):
    if present(dest, marker):
        print("ok      ", name)
        return
    print("download", name, "...", flush=True)
    with urllib.request.urlopen(url, timeout=600) as r:
        data = r.read()
    if marker is None:
        with open(dest, "wb") as f:
            f.write(data)
    else:
        os.makedirs(dest, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(data)).extractall(dest)
    print("done    ", name)


if __name__ == "__main__":
    items = BASE + (EDITOR if "--editor" in sys.argv else [])
    for item in items:
        fetch(*item)
