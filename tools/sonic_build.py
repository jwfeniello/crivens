"""Put Sonic (from bl_sonic_export.py's .npz) into Cooper's model.

Cooper's animations store per-bone rotations plus translation *deltas* from the skeleton's bind
positions, so the skeleton can be moved onto Sonic's joints and Sonic keeps his own proportions.
Each Sonic bone is mapped to a Cooper bone; weights are summed per Cooper bone (max 2 per vertex).

usage: python -I sonic_build.py <Model__aid_model_ghoulies_actor_boy dir> <sonic.npz> <textures dir> <out_dir> [height]
       [--fit-textures]

Sonic's textures are added at their own size in a new resource chunk and the materials are pointed
at them. --fit-textures instead shrinks them into Cooper's texture slots (no new chunk).
"""
import struct
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.image as mpimg  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_modelwrite as mw  # noqa: E402

full_textures = "--fit-textures" not in sys.argv
argv = [a for a in sys.argv[1:] if not a.startswith("--")]
src, npz, tex_dir, out = map(Path, argv[:4])
height = float(argv[4]) if len(argv) > 4 else 21.0  # Cooper is ~21 units tall

# Sonic bone -> Cooper bone ("{s}" = LF for +X, RT for -X; the character's left is +X)
SIDE_MAP = {
    "Bone025": "BACK_A", "Bone026": "BACK_A", "Bone027": "{s}_S", "Bone028": "{s}_S", "Bone031": "{s}_S",
    "Bone029": "{s}_E", "Bone030": "{s}_W",
    "Bone043": "{s}_H", "Bone048": "{s}_H", "Bone044": "{s}_K", "Bone047": "{s}_K",
    "Bone045": "{s}_A", "Bone046": "{s}_T",
}
MIRROR = {"Bone025": "Bone032", "Bone026": "Bone033", "Bone027": "Bone034", "Bone028": "Bone035",
          "Bone031": "Bone038", "Bone029": "Bone036", "Bone030": "Bone037", "Bone043": "Bone049",
          "Bone048": "Bone054", "Bone044": "Bone050", "Bone047": "Bone053", "Bone045": "Bone051",
          "Bone046": "Bone052"}
CENTRE = {"Bone001": "BASE", "Bone002": "BASE", "Bone055": "BASE", "Bone003": "BASE", "Bone041": "BASE",
          "Bone042": "BASE", "Bone004": "BACK", "Bone005": "BACK_A", "Bone039": "BACK_A",
          "Bone040": "BACK_A", "Bone006": "NECK"}  # Bone007 and everything under it -> HEAD
# Cooper joint <- Sonic joint, for moving the skeleton
JOINTS = {"BASE": "Bone003", "BACK": "Bone004", "BACK_A": "Bone005", "NECK": "Bone006", "HEAD": "Bone007",
          "LF_S": "Bone028", "LF_E": "Bone029", "LF_W": "Bone030", "LF_H": "Bone043", "LF_K": "Bone044",
          "LF_A": "Bone045", "LF_T": "Bone046",
          "RT_S": "Bone035", "RT_E": "Bone036", "RT_W": "Bone037", "RT_H": "Bone049", "RT_K": "Bone050",
          "RT_A": "Bone051", "RT_T": "Bone052"}
HAND_PARTS = {"N114", "N115"}  # hand meshes are weighted to the forearm in the rip; bind them to the wrist
# Sonic texture -> (Cooper material = blend ndShaderParam2 of ndShader2 #, that material's colour0
# texture: used as the template for the new texture, or overwritten in place with --fit-textures)
MATERIALS = {"ch_sonic_a.png": (0, 11), "ch_sonic_b.png": (4, 8), "ch_sonic_eye.png": (2, 7)}

d = np.load(npz)
names = list(d["bone_names"])
parents = d["parents"]
cooper_of = {}
for i, n in enumerate(names):
    if n in CENTRE:
        cooper_of[i] = CENTRE[n]
    elif n in SIDE_MAP:
        cooper_of[i] = SIDE_MAP[n].format(s="LF")
    elif n in MIRROR.values():
        left = next(k for k, v in MIRROR.items() if v == n)
        cooper_of[i] = SIDE_MAP[left].format(s="RT")
for i, n in enumerate(names):  # head children
    if i not in cooper_of:
        j = i
        while j >= 0 and names[j] != "Bone007":
            j = parents[j]
        if j < 0:
            sys.exit(f"unmapped Sonic bone {n}")
        cooper_of[i] = "HEAD"

# ---- Cooper model and its bone names
chunks = []
while (src / f"resource{len(chunks)}").exists():
    chunks.append((src / f"resource{len(chunks)}").read_bytes())
model = mw.Model((src / "descriptor").read_bytes(), chunks)
mb = model.mb
bone_index = {}
kv = mw.u32(mb, 0x10)
nkv, dp = struct.unpack_from("<II", mb, kv)
for i in range(nkv):
    k, v, s = struct.unpack_from("<III", mb, dp + 12 * i)
    if s == 4:
        bone_index.setdefault(mw.gm.cstr(mb, k), mw.u32(mb, v))
bones = model.skel.data["bones"]

scale = height / float(d["pos"][:, 1].max())
heads = d["heads"] * scale

# ---- move the skeleton onto Sonic's joints (bind = local offset, global = model space)
glob = [np.array(b["global"]) for b in bones]
new_glob = list(glob)
moved = {bone_index[c]: heads[names.index(s)] for c, s in JOINTS.items()}
ratio = height / 21.1
for i, b in enumerate(bones):  # parents come before children
    p = b["parent"]
    if i in moved:
        new_glob[i] = moved[i]
    elif p != 0xFFFF:
        new_glob[i] = new_glob[p] + (glob[i] - glob[p]) * ratio  # fingers, eyes, toe tips: keep shape
sk = mw.u32(mb, model.skel.off + 0x24)
for i, b in enumerate(bones):
    p = b["parent"]
    local = new_glob[i] - (new_glob[p] if p != 0xFFFF else 0)
    model.put(sk + 0x20 * i + 4, "<3f", *local)
    model.put(sk + 0x20 * i + 0x10, "<3f", *new_glob[i])

# ---- textures: add at full size, or box-filter down to the replaced texture's size
mats = {si: sp for si, var, sp in model.materials() if var == "blend"}
tex_names = list(d["tex_names"])
material_of_tex = {}
for t, (si, ti) in MATERIALS.items():
    img = mpimg.imread(str(tex_dir / t))
    if img.dtype != np.uint8:
        img = np.round(img * 255).astype(np.uint8)
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    img[..., 3] = 255
    if full_textures:
        new = model.add_texture(img, ti)
        model.set_material_texture(mats[si].off, new)
        ti = new
    else:
        _t7, _n, lst = model.texture_list()
        tw = struct.unpack_from("<H", model.desc, mw.u32(model.desc, lst + 4 * ti) + 8)[0]
        while img.shape[0] > tw:
            img = img.reshape(img.shape[0] // 2, 2, img.shape[1] // 2, 2, 4).mean((1, 3)).round().astype(np.uint8)
        model.replace_texture(ti, img)
    material_of_tex[tex_names.index(t)] = mats[si].off
    print(f"{t} -> texture {ti} ({img.shape[1]}x{img.shape[0]}) on ndShader2 {si}")

# ---- geometry
groups = {off: mw.Group(off, max_bones=4) for off in material_of_tex.values()}
pos, nrm, uv = d["pos"] * scale, d["nrm"], d["uv"]
cache = {}


def vertex(c):
    key = (tuple(pos[c].round(6)), tuple(nrm[c].round(4)), tuple(uv[c].round(6)), str(d["part"][c]))
    if key in cache:
        return cache[key]
    w = {}
    if any(str(d["part"][c]).endswith(h) for h in HAND_PARTS):
        w = {bone_index["LF_W" if pos[c][0] > 0 else "RT_W"]: 1.0}
    else:
        for bi, bw in zip(d["bi"][c], d["bw"][c]):
            if bw > 0:
                b = bone_index[cooper_of[int(bi)]]
                w[b] = w.get(b, 0.0) + float(bw)
    top = sorted(w.items(), key=lambda x: -x[1])[:2]
    tot = sum(x for _b, x in top)
    bs, ws = tuple(b for b, _x in top), tuple(x / tot for _b, x in top)
    v = mw.Vertex(tuple(map(float, pos[c])), tuple(map(float, nrm[c])), (float(uv[c][0]), 1.0 - float(uv[c][1])),
                  b"\xff\xff\xff\xff", bs, ws)
    cache[key] = v
    return v


for t in range(len(pos) // 3):
    c = 3 * t
    groups[material_of_tex[int(d["mat"][c])]].tris.append((vertex(c), vertex(c + 1), vertex(c + 2)))
model.hide_blend_shape()  # Cooper's face: kept in the tree (the game drives it), drawn as nothing
stats = model.write_geometry([g for g in groups.values() if g.tris])
desc, new_chunks = model.finish()
print("written:", stats, "descriptor", len(desc), "chunks", [len(c) for c in new_chunks])

out.mkdir(parents=True, exist_ok=True)
for f in out.glob("resource*"):
    f.unlink()
(out / "descriptor").write_bytes(desc)
for i, c in enumerate(new_chunks):
    (out / f"resource{i}").write_bytes(c)
print("wrote", out)
