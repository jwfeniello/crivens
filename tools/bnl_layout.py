"""Analyse the internal layout of a BNL bundle (ordering, alignment, padding).
usage: python -I bnl_layout.py <file.bnl>
"""
import collections
import struct
import sys
import zlib
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
hdr = raw[:40]
full = hdr + zlib.decompress(raw[40:])
count, flags = struct.unpack_from("<HB", hdr, 0)
unk = hdr[3:8]
views = [struct.unpack_from("<II", hdr, 8 + 8 * i) for i in range(4)]
names = ["asset_desc", "buffer_views", "buffer", "descriptors"]
print(f"file_count={count} flags={flags:#x} unk={unk.hex()} total_decompressed={len(full)}")
for n, (o, s) in zip(names, views):
    print(f"  {n:13} off={o:#010x} size={s:#010x} end={o + s:#010x}  off%0x1000={o % 0x1000:#x}")

ad_off, bv_off, buf_off, de_off = (v[0] for v in views)
assets = []
for i in range(count):
    b = full[ad_off + 0xA0 * i: ad_off + 0xA0 * (i + 1)]
    name = b[:128].split(b"\0")[0].decode()
    typ, u1, u2, chunks, dptr, dsize, dvl_ptr, rsize = struct.unpack_from("<8I", b, 128)
    views_ = []
    if rsize:
        vsize, nv = struct.unpack_from("<II", full, bv_off + dvl_ptr)
        views_ = [struct.unpack_from("<II", full, bv_off + dvl_ptr + 8 + 8 * k) for k in range(nv)]
    assets.append(dict(i=i, name=name, type=typ, u1=u1, u2=u2, chunks=chunks, dptr=dptr, dsize=dsize,
                       dvl=dvl_ptr, rsize=rsize, views=views_, tail=b[160 - 0:]))

print("sorted by name:", [a["name"] for a in assets] == sorted(a["name"] for a in assets))
print("u1/u2 values:", collections.Counter((a["u1"], a["u2"]) for a in assets).most_common(5))
print("chunk_count vs views:", collections.Counter((a["chunks"], len(a["views"])) for a in assets).most_common(6))
print("rsize vs dvl bytes:", collections.Counter((a["rsize"] - (8 + 8 * len(a["views"]))) if a["views"] else None for a in assets).most_common(5))

# descriptor ordering / padding
ds = sorted((a["dptr"], a["dsize"], a["i"]) for a in assets)
gaps = collections.Counter()
for (p0, s0, _), (p1, _s1, _) in zip(ds, ds[1:]):
    gaps[p1 - (p0 + s0)] += 1
print("descriptor order == asset order:", [x[2] for x in ds] == sorted(x[2] for x in ds))
print("descriptor gaps:", gaps.most_common(6), " first dptr", ds[0][0])
print("descriptor alignment:", collections.Counter(p % 16 for p, _, _ in ds).most_common(4))

# buffer chunk ordering / alignment
allv = sorted((o, s, a["i"]) for a in assets for (o, s) in a["views"])
g2 = collections.Counter()
for (o0, s0, _), (o1, _, _) in zip(allv, allv[1:]):
    g2[o1 - (o0 + s0)] += 1
print("buffer chunks:", len(allv), "first", allv[0][0] if allv else None)
print("buffer gaps:", g2.most_common(8))
for al in (16, 128, 256, 512, 4096):
    print(f"  chunks aligned to {al}: {sum(1 for o, _, _ in allv if o % al == 0)}/{len(allv)}")
print("chunk order == asset order:", [x[2] for x in allv] == sorted(x[2] for x in allv))
# dvl ordering
dv = sorted((a["dvl"], a["i"]) for a in assets if a["views"])
print("dvl order == asset order:", [x[1] for x in dv] == sorted(x[1] for x in dv), " dvl contiguous:",
      all(dv[k + 1][0] - dv[k][0] == 8 + 8 * len(assets[dv[k][1]]["views"]) for k in range(len(dv) - 1)))
# section gaps
print("section gaps:", [views[k + 1][0] - (views[k][0] + views[k][1]) for k in range(3)],
      " trailing:", len(full) - (views[3][0] + views[3][1]))
print("padding byte values in buffer gaps:",
      collections.Counter(full[buf_off + o0 + s0: buf_off + o1][:1] for (o0, s0, _), (o1, _, _) in zip(allv, allv[1:]) if o1 > o0 + s0).most_common(3))
