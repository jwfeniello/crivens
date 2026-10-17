"""Survey Ghoulies Script assets: opcode frequency, operand sizes, parse integrity.
usage: python -I script_survey.py <assets_dir> <out.json>
"""
import collections
import json
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
scripts = {}
for d in root.rglob("Script__*"):
    scripts.setdefault(d.name[len("Script__"):], d)

ops = collections.defaultdict(lambda: {"count": 0, "sizes": collections.Counter(), "scripts": set(), "example": None})
bad = []
nops = 0
for name, d in sorted(scripts.items()):
    data = (d / "descriptor").read_bytes()
    o = 0
    while o + 8 <= len(data):
        size, op = struct.unpack_from("<II", data, o)
        if size < 8 or o + size > len(data):
            bad.append((name, o, size, op, len(data)))
            break
        rec = ops[op]
        rec["count"] += 1
        rec["sizes"][size - 8] += 1
        rec["scripts"].add(name)
        if rec["example"] is None:
            rec["example"] = (name, data[o + 8:o + size].hex())
        nops += 1
        o += size
        if op == 0:
            break
    else:
        pass
    if o != len(data) and not any(b[0] == name for b in bad):
        bad.append((name, o, "trailing", len(data) - o, len(data)))

print(f"{len(scripts)} scripts, {nops} instructions, {len(ops)} distinct opcodes, {len(bad)} parse problems")
for b in bad[:8]:
    print("  problem:", b)
out = {}
for op in sorted(ops):
    r = ops[op]
    out[op] = {"count": r["count"], "sizes": dict(r["sizes"]), "nscripts": len(r["scripts"]), "example": r["example"]}
    sizes = ",".join(f"{s}x{c}" for s, c in sorted(r["sizes"].items()))
    print(f"  op {op:3d} (0x{op:02x}) n={r['count']:5d} in {len(r['scripts']):3d} scripts  operand sizes {sizes}")
json.dump(out, open(sys.argv[2], "w"), indent=1)
