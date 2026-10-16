"""
Patches global-metadata.dat of FNAF AR (IL2CPP).

1. The PlayFab SDK builds its URL as "https://<TitleId>." + "playfabapi.com". When that
   string starts with "http" the SDK uses it as-is, so replacing the "playfabapi.com"
   literal with e.g. http://127.0.0.1:9000 sends every PlayFab request to the local server.
2. InternetPinger pings 8.8.8.8 to check connectivity; the ping target becomes 127.0.0.1.

Usage:
    python patch_metadata.py <input global-metadata.dat> <output> [url]
"""
import struct
import sys

DEFAULT_URL = "http://127.0.0.1:9000"
PING_TARGET = "127.0.0.1"


def replacements(url):
    return {"playfabapi.com": url, "8.8.8.8": PING_TARGET}


def patch(src, dst, url):
    data = bytearray(open(src, "rb").read())
    magic, version, lit_off, lit_size, data_off, data_size = struct.unpack_from("<6I", data, 0)
    if magic != 0xFAB11BAF:
        sys.exit("not a global-metadata.dat (magic=%x)" % magic)
    print("metadata version:", version)

    for old, new in replacements(url).items():
        old_b = old.encode("utf-8")
        entries = []
        for i in range(lit_size // 8):
            length, index = struct.unpack_from("<Ii", data, lit_off + i * 8)
            start = data_off + index
            if length == len(old_b) and data[start:start + length] == old_b:
                entries.append(i)
        if not entries:
            sys.exit("string literal '%s' not found (already patched?)" % old)

        # Append the new string to the end of the file. IL2CPP reads literals at
        # "stringLiteralDataOffset + dataIndex" without a bounds check.
        new_b = new.encode("utf-8")
        new_index = len(data) - data_off
        data += new_b
        for i in entries:
            struct.pack_into("<Ii", data, lit_off + i * 8, len(new_b), new_index)
            print("literal #%d: %s -> %s" % (i, old, new))

    open(dst, "wb").write(data)
    print("written:", dst)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    patch(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else DEFAULT_URL)
