"""
Builds the FNAF AR Editor APK without Android Studio.

Needs (in tools/, run: python tools/setup_tools.py --editor): jdk-17*,
android-sdk/android-14 (build-tools 34), android-sdk/android-8.0.0 (platform 26), uber-apk-signer.jar.

Usage:   python build.py
Output:  editor/build/FNAF.AR.Editor-aligned-debugSigned.apk
"""
import glob
import math
import os
import shutil
import struct
import subprocess
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.dirname(HERE), "tools")
BUILD = os.path.join(HERE, "build")
JDK = glob.glob(os.path.join(TOOLS, "jdk-17*"))
JDK = [j for j in JDK if not j.endswith("-jre")][0]
JAVA = os.path.join(JDK, "bin", "java.exe")
JAVAC = os.path.join(JDK, "bin", "javac.exe")
BT = os.path.join(TOOLS, "android-sdk", "android-14")
AAPT2 = os.path.join(BT, "aapt2.exe")
D8_JAR = os.path.join(BT, "lib", "d8.jar")
ANDROID_JAR = os.path.join(TOOLS, "android-sdk", "android-8.0.0", "android.jar")
SIGNER = os.path.join(TOOLS, "uber-apk-signer.jar")


def run(*cmd):
    print(">", " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    subprocess.check_call(list(cmd))


def write_png(path, size, pixel):
    """Dependency-free PNG writer; pixel(x, y) -> (r, g, b, a)."""
    raw = b"".join(b"\0" + b"".join(bytes(pixel(x, y)) for x in range(size)) for y in range(size))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        f.write(chunk(b"IEND", b""))


def icon_pixel(size):
    c = size / 2

    def px(x, y):
        dx, dy = x + 0.5 - c, y + 0.5 - c
        r = math.hypot(dx, dy) / c
        if r > 0.98:
            return (0, 0, 0, 0)
        # glowing eyes
        for ex in (-0.32, 0.32):
            if math.hypot(dx / c - ex, dy / c + 0.05) < 0.12:
                return (255, 214, 120, 255)
        if r > 0.86:
            return (232, 163, 60, 255)          # amber ring
        shade = int(28 + 22 * (1 - r))
        return (shade, shade - 6, shade - 10, 255)  # dark inside
    return px


def main():
    shutil.rmtree(BUILD, ignore_errors=True)
    for d in ("res/mipmap", "classes", "dex"):
        os.makedirs(os.path.join(BUILD, d), exist_ok=True)

    # 1) icon
    res = os.path.join(BUILD, "res")
    write_png(os.path.join(res, "mipmap", "ic_launcher.png"), 192, icon_pixel(192))

    # 2) resources + manifest
    res_zip = os.path.join(BUILD, "res.zip")
    run(AAPT2, "compile", "--dir", res, "-o", res_zip)
    base_apk = os.path.join(BUILD, "base.apk")
    run(AAPT2, "link", "-o", base_apk, "-I", ANDROID_JAR,
        "--manifest", os.path.join(HERE, "AndroidManifest.xml"),
        "-A", os.path.join(HERE, "assets"), res_zip)

    # 3) Java -> class -> dex
    sources = glob.glob(os.path.join(HERE, "src", "**", "*.java"), recursive=True)
    run(JAVAC, "-encoding", "UTF-8", "-source", "8", "-target", "8", "-Xlint:-options",
        "-bootclasspath", ANDROID_JAR, "-d", os.path.join(BUILD, "classes"), *sources)
    classes = glob.glob(os.path.join(BUILD, "classes", "**", "*.class"), recursive=True)
    run(JAVA, "-cp", D8_JAR, "com.android.tools.r8.D8", "--lib", ANDROID_JAR, "--min-api", "24",
        "--output", os.path.join(BUILD, "dex"), *classes)

    # 4) add the dex to the APK
    unsigned = os.path.join(BUILD, "FNAF.AR.Editor.apk")
    shutil.copy(base_apk, unsigned)
    with zipfile.ZipFile(unsigned, "a", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(BUILD, "dex", "classes.dex"), "classes.dex")

    # 5) zipalign + signature
    run(JAVA, "-jar", SIGNER, "--apks", unsigned, "--out", BUILD, "--allowResign")
    print("ready:", glob.glob(os.path.join(BUILD, "*-aligned-debugSigned.apk")))


if __name__ == "__main__":
    main()
