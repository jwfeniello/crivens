"""Check a model asset against the game's loading rules (each resource chunk is allocated
separately; mesh vertex data is addressed from the chunk containing the mesh's resource offset;
textures are located individually and must not span chunks).

usage: python -I check_model.py <model_asset_dir>
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_model as gm  # noqa: E402

d = Path(sys.argv[1])
desc = (d / "descriptor").read_bytes()
sizes = []
while (d / f"resource{len(sizes)}").exists():
    sizes.append((d / f"resource{len(sizes)}").stat().st_size)
starts = [sum(sizes[:i]) for i in range(len(sizes))]


def chunk_of(off):
    return next((i for i, (s, n) in enumerate(zip(starts, sizes)) if s <= off < s + n), None)


problems = []
m = gm.read_model(desc)
fp, nf = struct.unpack_from("<II", desc, 0)
footer = [struct.unpack_from("<II", desc, fp + 8 * e) for e in range(nf)]
t0 = next(p for t, p in footer if t == 0)
base = struct.unpack_from("<I", desc, t0 + 4)[0]  # mesh resource offset (0 = start of chunk 0)
bc = chunk_of(base)
mb = m["meshes"][0]["bytes"]
n_views = 0
for r in m["meshes"][0]["roots"]:
    for _, n in r.walk():
        vbs = [n] if n.name == "ndVertexBuffer" else []
        if n.name == "ndBlendShape":
            vbs = [gm.Node(mb, p) for p in n.data["vertex_buffers"]]
        for vb in vbs:
            for v in vb.data["views"]:
                if not v["size"]:
                    continue
                n_views += 1
                a, b = base + v["begin"], base + v["begin"] + v["size"] - 1
                if chunk_of(a) != bc or chunk_of(b) != bc:
                    problems.append(f"vertex view type {v['type']} [{a}, {b}] not inside base chunk {bc}")
t7 = next(p for t, p in footer if t == 7)
count, lst = struct.unpack_from("<II", desc, t7)
for i in range(count):
    rec = struct.unpack_from("<I", desc, lst + 4 * i)[0]
    off, size = struct.unpack_from("<II", desc, rec + 0x14)
    if size and chunk_of(off) != chunk_of(off + size - 1):
        problems.append(f"texture {i} [{off}, {off + size}] spans chunks")
    if size and chunk_of(off) is None:
        problems.append(f"texture {i} outside resources")
print(f"chunks {sizes}; {n_views} vertex views, {count} textures checked; problems: {len(problems)}")
for p in problems[:10]:
    print("  " + p)
sys.exit(1 if problems else 0)
