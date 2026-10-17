"""Export a Grabbed by the Ghoulies model as a rigged, skinned, animated .glb.

usage: python -I ghoul_gltf.py <model_asset_dir> <out.glb> [anim_dir | @list_file ...]
                                [--anim-filter=STR] [--no-root-motion]

model_asset_dir: an extracted Model__* folder (descriptor, resource0.., imageN.png from bnl).
anim_dir: folders searched (recursively) for Anim__*/descriptor with a matching bone count.

Skinning (from default.xbe): ndMtxArray entries map palette entries to skeleton bones,
ndRigidSkinIdx selects a per-draw palette, and each vertex stores two palette register
offsets (24 + 3*slot, float) and two weights. Skin matrix = bone_world * translate(-global).
Game data is left-handed (D3D); we mirror Z to produce right-handed glTF.
"""
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghoul_anim  # noqa: E402
import ghoul_model as gm  # noqa: E402

PRIM_STRIP, PRIM_LIST, PRIM_FAN = 6, 5, 7


# Game data is already right-handed, Y-up, facing +Z (LF_* bones sit at +X), matching glTF.
# These hooks stay in case a coordinate conversion is ever needed.
def mirror_v(v):
    return list(v)


def mirror_q(q):
    return list(q)


class Builder:
    def __init__(self):
        self.g = {"asset": {"version": "2.0", "generator": "ghoul_gltf (Grabbed by the Ghoulies RE)"},
                  "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [],
                  "textures": [], "images": [], "samplers": [{"magFilter": 9729, "minFilter": 9987}],
                  "accessors": [], "bufferViews": [], "buffers": [], "skins": [], "animations": []}
        self.bin = bytearray()

    def view(self, data, target=None):
        while len(self.bin) % 4:
            self.bin.append(0)
        bv = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
        if target:
            bv["target"] = target
        self.bin.extend(data)
        self.g["bufferViews"].append(bv)
        return len(self.g["bufferViews"]) - 1

    def acc(self, values, typ, comp=5126, normalized=False, minmax=False, target=None):
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[typ]
        flat = [c for v in values for c in (v if isinstance(v, (list, tuple)) else [v])]
        fmt = {5126: "f", 5123: "H", 5125: "I", 5121: "B"}[comp]
        a = {"bufferView": self.view(struct.pack(f"<{len(flat)}{fmt}", *flat), target),
             "componentType": comp, "count": len(values), "type": typ}
        if normalized:
            a["normalized"] = True
        if minmax:
            a["min"] = [min(flat[i::n]) for i in range(n)]
            a["max"] = [max(flat[i::n]) for i in range(n)]
        self.g["accessors"].append(a)
        return len(self.g["accessors"]) - 1

    def node(self, **kw):
        self.g["nodes"].append(kw)
        return len(self.g["nodes"]) - 1

    def glb(self):
        js = json.dumps(self.g, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        self.bin.extend(b"\0" * (-len(self.bin) % 4))
        self.g["buffers"] = [{"byteLength": len(self.bin)}]
        js = json.dumps(self.g, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        total = 12 + 8 + len(js) + 8 + len(self.bin)
        return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js
                + struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))


def read_views(vb_node, res):
    out = {}
    for v in vb_node.data["views"]:
        if v["size"]:
            out[v["type"]] = (v["begin"], v["stride"], v["size"] // v["stride"])
    return out


def get_attr(res, views, t, i, fmt):
    begin, stride, _ = views[t]
    return struct.unpack_from(fmt, res, begin + i * stride)


def shader_material(mb, node):
    """ndShaderParam2 -> (texture index or None, RGB colour).

    The diffuse texture is the slot named by the 'colour0' attribute (as in bnl); other slots
    are Rare's cel-shading ramp / lightmap. Flat colours (skin, lips...) are pixel shader
    constants stored as RGBA bytes; we use the first non-white one.
    """
    p = gm.u32(mb, node.off + 0x20)
    if not p:
        return None, (1.0, 1.0, 1.0)
    ps_start, _vs, tex_start, ntex, _nvs, nps = struct.unpack_from("<6I", mb, p)
    attr_start, nattr = gm.u32(mb, p + 0x24), gm.u32(mb, p + 0x28)
    tex = None
    for i in range(nattr):
        name_ptr, _v1, v2 = struct.unpack_from("<III", mb, attr_start + 16 * i)
        if gm.cstr(mb, name_ptr) == "colour0" and v2 < ntex:
            tex = gm.u32(mb, tex_start + 28 * v2)
    colour = (1.0, 1.0, 1.0)
    for i in range(nps):
        r, gg, b, _a = mb[ps_start + 4 * i: ps_start + 4 * i + 4]
        if (r, gg, b) != (255, 255, 255):
            colour = (r / 255, gg / 255, b / 255)
            break
    return tex, colour


def triangles(idx, prim):
    tris = []
    if prim == PRIM_STRIP:
        for i in range(len(idx) - 2):
            a, b, c = (idx[i], idx[i + 1], idx[i + 2]) if i % 2 == 0 else (idx[i + 1], idx[i], idx[i + 2])
            if a != b and b != c and a != c:
                tris.append((a, b, c))
    elif prim == PRIM_LIST:
        tris = [tuple(idx[i:i + 3]) for i in range(0, len(idx) - 2, 3)]
    elif prim == PRIM_FAN:
        tris = [(idx[0], idx[i], idx[i + 1]) for i in range(1, len(idx) - 1)]
    return tris


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flt = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--anim-filter=")), "")
    root_motion = "--no-root-motion" not in sys.argv
    model_dir, out_path = Path(args[0]), Path(args[1])
    anim_dirs = []
    for a in args[2:]:
        if a.startswith("@"):  # file listing Anim__ folders, one per line
            anim_dirs += [Path(x) for x in Path(a[1:]).read_text().splitlines() if x.strip()]
        else:
            anim_dirs.append(Path(a))

    desc = (model_dir / "descriptor").read_bytes()
    chunks = []
    while (model_dir / f"resource{len(chunks)}").exists():  # large models have dozens of chunks
        chunks.append((model_dir / f"resource{len(chunks)}").read_bytes())
    res = b"".join(chunks)
    model = gm.read_model(desc)
    mesh0 = model["meshes"][0]
    mb = mesh0["bytes"]

    # bone names from the mesh key/value map (name -> bone index)
    names = {}
    kv = gm.u32(mb, 0x10)
    if kv:
        nkv, dp = struct.unpack_from("<II", mb, kv)
        for i in range(nkv):
            k, v, s = struct.unpack_from("<III", mb, dp + 12 * i)
            if s == 4:
                names.setdefault(gm.u32(mb, v), gm.cstr(mb, k))

    B = Builder()
    g = B.g

    # textures (imageN.png written by bnl / model_textures; some may be missing)
    material_for_tex = {}

    def material(tex_colour):
        tex, colour = tex_colour if tex_colour else (None, (1.0, 1.0, 1.0))
        if tex is not None and not (model_dir / f"image{tex}.png").exists():
            tex = None
        key = (tex, colour)
        if key not in material_for_tex:
            hexcol = "".join(f"{round(c * 255):02x}" for c in colour)
            m = {"name": f"mat_tex{tex}" if tex is not None else f"mat_{hexcol}",
                 "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 1.0,
                                          "baseColorFactor": [*colour, 1.0]}, "doubleSided": False}
            if tex is not None:
                png = (model_dir / f"image{tex}.png").read_bytes()
                g["images"].append({"name": f"image{tex}", "mimeType": "image/png", "bufferView": B.view(png)})
                g["textures"].append({"source": len(g["images"]) - 1, "sampler": 0})
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(g["textures"]) - 1}
                m["alphaMode"] = "MASK"
                m["alphaCutoff"] = 0.5
            g["materials"].append(m)
            material_for_tex[key] = len(g["materials"]) - 1
        return material_for_tex[key]

    # skeleton
    skel = next((n for r in mesh0["roots"] for _, n in r.walk() if n.name == "ndSkeleton"), None)
    joints, bones = [], []
    if skel:
        bones = skel.data["bones"]
        for i, b in enumerate(bones):
            joints.append(B.node(name=names.get(i, f"bone_{i}"), translation=mirror_v(b["bind"])))
        roots = []
        for i, b in enumerate(bones):
            if b["parent"] == 0xFFFF or b["parent"] >= len(bones) or b["parent"] == i:
                roots.append(joints[i])
            else:
                g["nodes"][joints[b["parent"]]].setdefault("children", []).append(joints[i])
        ibm = []
        for b in bones:
            x, y, z = mirror_v(b["global"])
            ibm.append([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, -x, -y, -z, 1])
        armature = B.node(name=model_dir.name.replace("Model__aid_model_ghoulies_", ""), children=roots)
        # the skin's skeleton must be a common root of all joints
        g["skins"].append({"name": "skeleton", "joints": joints, "inverseBindMatrices": B.acc(ibm, "MAT4"),
                           "skeleton": roots[0] if len(roots) == 1 else armature})
        g["scenes"][0]["nodes"].append(armature)

    # walk the nd tree collecting primitives
    groups = {}  # key: id(vertex-source) -> {"prims": [...], "morph": [...]}

    def walk(nodes, ctx):
        for n in nodes:
            c = dict(ctx)
            if n.name == "ndVertexBuffer":
                c["vb"], c["morph"] = n, []
            elif n.name == "ndBlendShape":
                vbs = [gm.Node(mb, p) for p in n.data["vertex_buffers"]]
                c["vb"], c["morph"] = vbs[0], vbs[1:]
            elif n.name == "ndMtxArray":
                c["mtx"], c["mtx_mats"] = n.data["entries"], n.data["matrices"]
            elif n.name == "ndRigidSkinIdx":
                c["pal"] = n.data["palette"]
            elif n.name == "ndShaderParam2":
                c["tex"] = shader_material(mb, n)
            elif n.name in ("ndPushBuffer", "ndBGPushBuffer") and "vb" in c:
                key = c["vb"].off
                grp = groups.setdefault(key, {"vb": c["vb"], "morph": c.get("morph", []), "prims": []})
                for dr in n.data["draws"]:
                    idx = struct.unpack_from(f"<{dr['count']}H", mb, dr["ptr"])
                    grp["prims"].append({"tris": triangles(idx, dr["prim"]), "pal": c.get("pal"),
                                         "mtx": c.get("mtx"), "mtx_mats": c.get("mtx_mats", []),
                                         "tex": c.get("tex")})
            walk(n.children, c)

    walk(mesh0["roots"], {})

    mesh_nodes = []
    for gi, grp in enumerate(groups.values()):
        views = read_views(grp["vb"], res)
        mviews = [read_views(m, res) for m in grp["morph"]]
        prims = []
        for p in grp["prims"]:
            used = sorted({i for t in p["tris"] for i in t})
            if not used:
                continue
            remap = {v: k for k, v in enumerate(used)}
            raw_pos = [get_attr(res, views, 9, i, "<3f") for i in used]
            raw_nrm = [get_attr(res, views, 10, i, "<3f") for i in used] if 10 in views else None
            # Per-vertex pre-transform from the matrix palette (identity unless an entry carries a
            # stored matrix; flag 0/1 entries store vertices relative to a piece pivot).
            pre = [None] * len(used)
            skinned = skel and 0 in views and 8 in views and p["pal"] is not None and p["mtx"] is not None
            J, W = [], []
            if skinned:
                for k, i in enumerate(used):
                    s = get_attr(res, views, 0, i, "<2f")
                    w = get_attr(res, views, 8, i, "<2f")
                    jj, mats = [], []
                    for sv in s:
                        slot = int(round((sv - 24) / 3))
                        ent = p["mtx"][p["pal"][slot]] if 0 <= slot < len(p["pal"]) and p["pal"][slot] < len(p["mtx"]) else None
                        jj.append(ent["bone"] if ent and not ent["flag"] & 1 and ent["bone"] < len(bones) else 0)
                        mats.append(p["mtx_mats"][ent["matrix"]] if ent and not ent["flag"] & 2
                                    and ent["matrix"] < len(p["mtx_mats"]) else None)
                    w0, w1 = max(w[0], 0.0), max(w[1], 0.0)
                    if w0 + w1 <= 0:
                        w0 = 1.0
                    if any(mt is not None for mt in mats):
                        pre[k] = [(wv / (w0 + w1), mt) for wv, mt in zip((w0, w1), mats) if wv > 0]
            pos, nrm = [], []
            for k in range(len(used)):
                if pre[k] is None:
                    pos.append(mirror_v(raw_pos[k]))
                    if raw_nrm:
                        nrm.append(mirror_v(raw_nrm[k]))
                    continue
                pp, nn = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
                for wv, mt in pre[k]:
                    mt = mt or (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
                    v = raw_pos[k]
                    for c in range(3):  # D3D row vector: v' = [v,1] * M
                        pp[c] += wv * (v[0] * mt[c] + v[1] * mt[4 + c] + v[2] * mt[8 + c] + mt[12 + c])
                        if raw_nrm:
                            n = raw_nrm[k]
                            nn[c] += wv * (n[0] * mt[c] + n[1] * mt[4 + c] + n[2] * mt[8 + c])
                pos.append(mirror_v(pp))
                if raw_nrm:
                    ln = sum(c * c for c in nn) ** 0.5 or 1.0
                    nrm.append(mirror_v([c / ln for c in nn]))
            attrs = {"POSITION": B.acc(pos, "VEC3", minmax=True, target=34962)}
            if raw_nrm:
                attrs["NORMAL"] = B.acc(nrm, "VEC3", target=34962)
            if 13 in views:
                attrs["TEXCOORD_0"] = B.acc([get_attr(res, views, 13, i, "<2f") for i in used], "VEC2", target=34962)
            if skinned:
                for i in used:
                    s = get_attr(res, views, 0, i, "<2f")
                    w = get_attr(res, views, 8, i, "<2f")
                    jj = []
                    for sv in s:
                        slot = int(round((sv - 24) / 3))
                        ent = p["mtx"][p["pal"][slot]] if 0 <= slot < len(p["pal"]) and p["pal"][slot] < len(p["mtx"]) else None
                        jj.append(ent["bone"] if ent and not ent["flag"] & 1 and ent["bone"] < len(bones) else 0)
                    # merge both slots by bone, drop zero weights, renormalise
                    acc_w = {}
                    for jn, wv in zip(jj, (max(w[0], 0.0), max(w[1], 0.0))):
                        if wv > 0:
                            acc_w[jn] = acc_w.get(jn, 0.0) + wv
                    if not acc_w:
                        acc_w = {jj[0]: 1.0}
                    tot = sum(acc_w.values())
                    pairs_jw = sorted(acc_w.items(), key=lambda kv: -kv[1])
                    J.append([pj for pj, _ in pairs_jw] + [0] * (4 - len(pairs_jw)))
                    W.append([pw / tot for _, pw in pairs_jw] + [0.0] * (4 - len(pairs_jw)))
                attrs["JOINTS_0"] = B.acc(J, "VEC4", comp=5123, target=34962)
                attrs["WEIGHTS_0"] = B.acc(W, "VEC4", target=34962)
            prim = {"attributes": attrs, "mode": 4, "material": material(p["tex"]),
                    "indices": B.acc([remap[i] for t in p["tris"] for i in t], "SCALAR", comp=5125, target=34963)}
            if mviews:
                targets = []
                # blend-shape vertex buffers already hold per-vertex offsets from the base
                for mv in mviews:
                    tgt = {"POSITION": B.acc([mirror_v(get_attr(res, mv, 9, i, "<3f")) for i in used], "VEC3", minmax=True)}
                    if 10 in mv and 10 in views:
                        tgt["NORMAL"] = B.acc([mirror_v(get_attr(res, mv, 10, i, "<3f")) for i in used], "VEC3")
                    targets.append(tgt)
                prim["targets"] = targets
            prims.append(prim)
        if not prims:
            continue
        mesh = {"name": f"mesh{gi}{'_face' if mviews else ''}", "primitives": prims}
        if mviews:
            mesh["weights"] = [0.0] * len(mviews)
            mesh["extras"] = {"targetNames": [f"blend_{k + 1}" for k in range(len(mviews))]}
        g["meshes"].append(mesh)
        nd = B.node(name=mesh["name"], mesh=len(g["meshes"]) - 1)
        if skel:
            g["nodes"][nd]["skin"] = 0
        mesh_nodes.append(nd)
    g["scenes"][0]["nodes"].extend(mesh_nodes)

    # animations
    n_anim = 0
    if skel and anim_dirs:
        rest = [mirror_v(b["bind"]) for b in bones]
        tcache = {}

        def tacc(times):
            k = tuple(round(t, 6) for t in times)
            if k not in tcache:
                tcache[k] = B.acc(list(times), "SCALAR", minmax=True)
            return tcache[k]

        def chan(anim, node, path, vals, times):
            if all(max(abs(a - b) for a, b in zip(v, vals[0])) < 1e-6 for v in vals):
                vals, times = [vals[0], vals[0]], [times[0], max(times[-1], times[0] + 1 / 60)]
            if len(times) > 1 and any(t1 <= t0 for t0, t1 in zip(times, times[1:])):
                times = [i / 60 for i in range(len(times))]  # zero-duration anims: 60 fps
            anim["samplers"].append({"input": tacc(times), "output": B.acc(vals, "VEC4" if path == "rotation" else "VEC3"),
                                     "interpolation": "LINEAR"})
            anim["channels"].append({"sampler": len(anim["samplers"]) - 1, "target": {"node": node, "path": path}})

        seen = set()
        for ad in anim_dirs:
            descs = [ad / "descriptor"] if ad.name.startswith("Anim__") else sorted(ad.rglob("Anim__*/descriptor"))
            for d in descs:
                nm = d.parent.name.replace("Anim__aid_anim_ghoulies_", "")
                if nm in seen or flt not in nm:
                    continue
                try:
                    a = ghoul_anim.decode(d.read_bytes())
                except ghoul_anim.AnimFormatError:
                    continue
                if a["num_bones"] != len(bones):
                    continue
                seen.add(nm)
                frames = a["main"]["frames"]
                nk, dur = len(frames), a["duration"]
                if nk > 1 and round(dur * 60) == nk:
                    times = [i * dur / nk for i in range(nk + 1)]
                    frames = frames + [frames[0]]
                else:
                    times = [i * dur / max(nk - 1, 1) for i in range(nk)]
                anim = {"name": nm, "channels": [], "samplers": []}
                for j in range(len(bones)):
                    rots = [mirror_q(f[j][0]) for f in frames]
                    for k in range(1, len(rots)):
                        if sum(x * y for x, y in zip(rots[k], rots[k - 1])) < 0:
                            rots[k] = [-c for c in rots[k]]
                    chan(anim, joints[j], "rotation", rots, times)
                    chan(anim, joints[j], "translation",
                         [[r + o for r, o in zip(rest[j], mirror_v(f[j][1]) if f[j][1] else (0, 0, 0))] for f in frames], times)
                    chan(anim, joints[j], "scale", [list(f[j][2] or (1.0, 1.0, 1.0)) for f in frames], times)
                # Root motion (separate 1-bone stream the game uses to move the actor) goes on the
                # armature node; anims without it get identity keys so switching actions resets.
                rm = a["root_motion"] if root_motion else None
                if rm:
                    rf = rm["frames"]
                    rt = [i * dur / max(len(rf) - 1, 1) for i in range(len(rf))]
                    chan(anim, armature, "translation", [mirror_v(f[0][1] or (0.0, 0.0, 0.0)) for f in rf], rt)
                    chan(anim, armature, "rotation", [mirror_q(f[0][0]) for f in rf], rt)
                else:
                    chan(anim, armature, "translation", [[0.0, 0.0, 0.0]] * 2, [times[0], times[-1]])
                    chan(anim, armature, "rotation", [[0.0, 0.0, 0.0, 1.0]] * 2, [times[0], times[-1]])
                g["animations"].append(anim)
                n_anim += 1

    for k in [k for k, v in g.items() if v == []]:
        del g[k]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(B.glb())
    nprims = sum(len(m["primitives"]) for m in g.get("meshes", []))
    print(f"{out_path.name}: {len(bones)} bones ({len(names)} named), {len(g.get('meshes', []))} meshes, "
          f"{nprims} primitives, {len(g.get('materials', []))} materials, {n_anim} animations, {len(B.bin) / 1e6:.1f} MB")


main()
