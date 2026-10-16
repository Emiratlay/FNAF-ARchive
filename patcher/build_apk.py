"""
Builds the offline APK from your own copy of the FNaF ARchive 8.0.0 APK:
  1. global-metadata.dat: PlayFab URL -> local server, ping target -> 127.0.0.1
  2. libil2cpp.so: code patches (see CODE_PATCHES)
  3. drops the old signature (META-INF), copies everything else unchanged
  4. zipalign + debug signature with uber-apk-signer

Usage:
    python build_apk.py [input.apk] [url]
Default input: patcher/input/FNaF.ARchive.8.0.0.apk
Output:        patcher/build/FNaF.AR.8.0.0.offline-aligned-debugSigned.apk
Run tools/setup_tools.py first (downloads Java and the signer).
"""
import glob
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from patch_metadata import DEFAULT_URL, patch  # noqa: E402

METADATA = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
LIBIL2CPP = "lib/arm64-v8a/libil2cpp.so"

ARM64_RET = bytes.fromhex("c0035fd6")

# (file offset, expected original bytes, new bytes, description)
# Offsets are method RVAs from an Il2CppDumper dump of the ARchive 8.0.0 build.
CODE_PATCHES = [
    # NetworkAvailabilityChecker.PopupDialogIfNecessary: return immediately, so the
    # "Connection Lost" dialog never opens when Wi-Fi / mobile data is off.
    (0x2BA5D74, bytes.fromhex("f50f1df8"), ARM64_RET, "Connection Lost dialog disabled"),
]


def patch_code(data):
    data = bytearray(data)
    for off, orig, new, desc in CODE_PATCHES:
        cur = bytes(data[off:off + len(orig)])
        if cur == new:
            print("already patched:", desc)
            continue
        if cur != orig:
            sys.exit("unexpected bytes in libil2cpp.so @%x: %s. This patcher only supports the "
                     "FNaF ARchive 8.0.0 APK." % (off, cur.hex()))
        data[off:off + len(new)] = new
        print("code patch:", desc)
    return bytes(data)


def main():
    src_apk = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "input", "FNaF.ARchive.8.0.0.apk")
    url = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_URL
    if not os.path.isfile(src_apk):
        sys.exit("APK not found: %s\nPut your FNaF.ARchive.8.0.0.apk there or pass its path." % src_apk)
    build = os.path.join(HERE, "build")
    os.makedirs(build, exist_ok=True)

    orig_meta = os.path.join(build, "global-metadata.orig.dat")
    new_meta = os.path.join(build, "global-metadata.dat")
    with zipfile.ZipFile(src_apk) as z:
        with open(orig_meta, "wb") as f:
            f.write(z.read(METADATA))
    patch(orig_meta, new_meta, url)

    unsigned = os.path.join(build, "FNaF.AR.8.0.0.offline.apk")
    with zipfile.ZipFile(src_apk) as zin, zipfile.ZipFile(unsigned, "w") as zout:
        for info in zin.infolist():
            if info.filename.startswith("META-INF/") and info.filename.upper().endswith(
                    (".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")):
                continue
            if info.filename == METADATA:
                data = open(new_meta, "rb").read()
            elif info.filename == LIBIL2CPP:
                data = patch_code(zin.read(info))
            else:
                data = zin.read(info)
            out = zipfile.ZipInfo(info.filename, info.date_time)
            out.compress_type = info.compress_type
            out.external_attr = info.external_attr
            zout.writestr(out, data)
    print("unsigned APK:", unsigned)

    java = glob.glob(os.path.join(ROOT, "tools", "jdk-*", "bin", "java.exe")) or ["java"]
    signer = os.path.join(ROOT, "tools", "uber-apk-signer.jar")
    if not os.path.isfile(signer):
        sys.exit("uber-apk-signer.jar not found. Run: python tools/setup_tools.py")
    subprocess.check_call([java[0], "-jar", signer, "--apks", unsigned, "--out", build, "--allowResign"])
    os.remove(unsigned)
    print("ready:", glob.glob(os.path.join(build, "*-aligned-debugSigned.apk")))


if __name__ == "__main__":
    main()
