"""
Disassembles a method of libil2cpp.so and annotates string literals and called methods
using Il2CppDumper output (script.json, stringliteral.json).

Needs your own analysis files next to the repo root (not included):
  unity/scripts/il2cpp/script.json + stringliteral.json  (Il2CppDumper output)
  resources/lib/arm64-v8a/libil2cpp.so                  (from the APK)
and capstone (pip install capstone).

Usage:
    python il2dis.py <Class$$Method or RVA (0x..)> [line_limit]
"""
import bisect
import json
import os
import sys

import capstone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "unity", "scripts", "il2cpp")
SO = os.path.join(ROOT, "resources", "lib", "arm64-v8a", "libil2cpp.so")

script = json.load(open(os.path.join(D, "script.json"), encoding="utf-8"))
methods = {m["Address"]: m["Name"] for m in script["ScriptMethod"]}
addrs = sorted(methods)
lits = {int(x["address"], 16): x["value"] for x in json.load(open(os.path.join(D, "stringliteral.json"), encoding="utf-8"))}
meta = {}
for key in ("ScriptMetadata", "ScriptMetadataMethod"):
    for m in script.get(key, []):
        meta[m["Address"]] = m["Name"]
so = open(SO, "rb").read()


def _relocs():
    """R_AARCH64_RELATIVE relocations: pointer slot -> target VA. String literals are loaded
    through such a slot, so this maps the slot back to the literal's metadata-usage address."""
    import struct
    phoff, = struct.unpack_from("<Q", so, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", so, 0x36)
    loads, dyn = [], None
    for i in range(phnum):
        p_type, _, p_off, p_vaddr, _, p_filesz, _, _ = struct.unpack_from("<IIQQQQQQ", so, phoff + i * phentsize)
        if p_type == 1:
            loads.append((p_vaddr, p_off, p_filesz))
        elif p_type == 2:
            dyn = (p_off, p_filesz)
    tags = {}
    for i in range(dyn[1] // 16):
        t, v = struct.unpack_from("<qQ", so, dyn[0] + i * 16)
        if t == 0:
            break
        tags.setdefault(t, v)
    base = next(o + tags[7] - a for a, o, n in loads if a <= tags[7] < a + n)
    out = {}
    for i in range(tags[8] // 24):
        r_off, r_info, r_add = struct.unpack_from("<QQq", so, base + i * 24)
        if r_info & 0xffffffff == 1027:
            out[r_off] = r_add
    return out


rel = _relocs()


def find(name):
    if name.startswith("0x"):
        return int(name, 16)
    hits = [a for a, n in methods.items() if n == name or n.endswith(name)]
    if not hits:
        sys.exit("not found: " + name)
    if len(hits) > 1:
        print("several matches, using the first:", [methods[h] for h in hits[:5]])
    return hits[0]


def disasm(start, limit=400):
    i = bisect.bisect_right(addrs, start)
    end = addrs[i] if i < len(addrs) else start + 0x400
    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    md.detail = True
    page = {}
    print("==", methods.get(start, hex(start)))
    for n, ins in enumerate(md.disasm(so[start:end], start)):
        if n >= limit:
            break
        note = ""
        if ins.mnemonic == "adrp":
            page[ins.operands[0].reg] = ins.operands[1].imm
        elif ins.mnemonic in ("ldr", "add") and len(ins.operands) >= 2:
            op = ins.operands[1]
            base = op.mem.base if op.type == capstone.arm64.ARM64_OP_MEM else (op.reg if op.type == capstone.arm64.ARM64_OP_REG else None)
            if base in page:
                disp = op.mem.disp if op.type == capstone.arm64.ARM64_OP_MEM else (ins.operands[2].imm if len(ins.operands) > 2 else 0)
                a = page[base] + disp
                a = rel.get(a, a)
                if a in lits:
                    note = "  ; \"%s\"" % lits[a][:80]
                elif a in meta:
                    note = "  ; " + meta[a][:90]
        elif ins.mnemonic in ("bl", "b"):
            t = ins.operands[0].imm
            if t in methods:
                note = "  ; " + methods[t][:90]
        print("%x  %-6s %s%s" % (ins.address, ins.mnemonic, ins.op_str, note))


if __name__ == "__main__":
    disasm(find(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 400)
