"""Simulate the game's bundle loader for one model asset and read its data the way the game does.

Follows ActuallyLoadBNLFile (sequential stream: asset descriptions, data-view lists, then every
asset's chunks in asset order, each chunk XPhysicalAlloc'd separately), DataViewList::
GetResourceByAddress (mesh base) and TextureResource::updatePointers (per-texture translation).
usage: python -I sim_load.py <bundle.bnl> <asset name>
"""
import struct
import sys
import zlib

import numpy as np

raw = open(sys.argv[1], "rb").read()
want = sys.argv[2]
hdr = raw[:40]
count = struct.unpack_from("<H", hdr, 0)[0]
views = [struct.unpack_from("<II", hdr, 8 + 8 * i) for i in range(4)]
stream = zlib.decompress(raw[40:])
pos = 0


def take(n):
    global pos
    b = stream[pos:pos + n]
    pos += n
    return b


descs = take(views[0][1])
dvls = take(views[1][1])
# the stream reader then reads, for every asset with totalAllocSize != 0, each item in order
allocs = {}
for i in range(count):
    rec = descs[0xA0 * i: 0xA0 * (i + 1)]
    name = rec[:128].split(b"\0")[0].decode()
    typ, u1, u2, fld, dptr, dsize, dvl_ptr, rsize = struct.unpack_from("<8I", rec, 128)
    if not rsize:
        continue
    _ls, n = struct.unpack_from("<II", dvls, dvl_ptr)
    items = [struct.unpack_from("<II", dvls, dvl_ptr + 8 + 8 * k) for k in range(n)]
    mem = [take(size) for _off, size in items]  # each item = separate allocation, read sequentially
    allocs[name] = (items, mem, (dptr, dsize, rsize))
desc_seg = take(views[3][1])
print("stream fully consumed:", pos == len(stream), f"({pos} of {len(stream)})")

items, mem, (dptr, dsize, rsize) = allocs[want]
desc = desc_seg[dptr:dptr + dsize]
print(f"{want}: {len(items)} chunks {[s for _o, s in items]}, resource_size {rsize}")
# what is in the chunk positions vs the in-bundle offsets?
print("  chunk buffer offsets in bundle:", [o for o, _s in items])


def translate(virtual):
    total = 0
    for k, (_o, s) in enumerate(items):
        if virtual < total + s:
            return k, virtual - total
        total += s
    return None, None


fp, nf = struct.unpack_from("<II", desc, 0)
footer = [struct.unpack_from("<II", desc, fp + 8 * e) for e in range(nf)]
t0 = next(p for t, p in footer if t == 0)
mesh_hdr, res_off = struct.unpack_from("<II", desc, t0)
bk, boff = translate(res_off)
print(f"  mesh base: virtual {res_off} -> chunk {bk} + {boff}")
# body VB positions via the game's rule: base + view begin, inside the base chunk allocation
sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
import ghoul_model as gm  # noqa: E402

m = gm.read_model(desc)
vb = m["meshes"][0]["roots"][0].children[0]
for v in vb.data["views"]:
    if v["type"] == 9 and v["size"]:
        a = boff + v["begin"]
        chunk = mem[bk]
        ok = a + v["size"] <= len(chunk)
        p = np.frombuffer(chunk[a:a + min(v["size"], 12 * 5)], "<f4").reshape(-1, 3) if ok else None
        print(f"  positions view begin {v['begin']} size {v['size']}: inside base chunk = {ok}; first verts {None if p is None else p.round(2).tolist()}")
t7 = next(p for t, p in footer if t == 7)
tc, tl = struct.unpack_from("<II", desc, t7)
for ti in (8, 11):
    rec = struct.unpack_from("<I", desc, tl + 4 * ti)[0]
    off, size = struct.unpack_from("<II", desc, rec + 0x14)
    k, lo = translate(off)
    data = mem[k][lo:lo + size]
    print(f"  texture {ti}: virtual {off} -> chunk {k} + {lo}; first bytes {data[:8].hex()}")
