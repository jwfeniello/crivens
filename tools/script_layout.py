"""Data-driven operand layout probe: for each opcode, string positions and word statistics.
usage: python -I script_layout.py <assets_dir> [opcode_hex ...]
"""
import collections
import re
import struct
import sys
from pathlib import Path

root = Path(sys.argv[1])
want = {int(x, 16) for x in sys.argv[2:]}
insts = collections.defaultdict(list)
seen = set()
for d in root.rglob("Script__*"):
    if d.name in seen:
        continue
    seen.add(d.name)
    data = (d / "descriptor").read_bytes()
    o = 0
    while o + 8 <= len(data):
        size, op = struct.unpack_from("<II", data, o)
        insts[op].append(data[o + 8:o + size])
        o += size
        if op == 0:
            break

for op in sorted(insts):
    if want and op not in want:
        continue
    ex = insts[op]
    n = len(ex[0])
    # string starts: offsets (4-aligned) where any instance has >=3 printable chars beginning there
    strs = collections.Counter()
    for b in ex:
        for m in re.finditer(rb"[\x20-\x7e]{3,}", b):
            strs[m.start()] += 1
    words = []
    for k in range(0, n - n % 4, 4):
        vals = [struct.unpack_from("<I", b, k)[0] for b in ex]
        uniq = sorted(set(vals))
        words.append((k, len(uniq), uniq[:4]))
    print(f"op 0x{op:02x} n={len(ex)} size={n} strings@{dict(strs)}")
    nonzero = [(k, c, [hex(v) for v in u]) for k, c, u in words if not (c == 1 and u[0] == 0)]
    shown = [w for w in nonzero if not any(s <= w[0] < s + 64 for s in strs)]
    print("    words:", shown[:12])
    sample = ex[0]
    print("    sample strings:", [m.group().decode() for m in re.finditer(rb"[\x20-\x7e]{3,}", sample)][:4])
