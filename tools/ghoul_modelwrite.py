"""Write new skinned geometry (and textures) into a Grabbed by the Ghoulies model by surgery on
an existing model (e.g. Cooper), keeping its skeleton, shaders, collision and materials.

How it works (all from default.xbe + the model data):
  * New data is appended to the end of the descriptor (nodes, palettes, index lists, texture
    records) and to a new last resource chunk (vertex streams, texture pixels). Nothing existing
    moves, so all original pointers stay valid; the old geometry is just left unreferenced.
  * Node pointers are relative to the MeshHeader; texture-list/record pointers are relative to the
    descriptor; resource offsets are relative to the start of the asset's concatenated resources.
  * Each node owns a slot in a per-instance runtime buffer (ndHeader +0x0C); MeshHeader +0 is its
    size. New ndRigidSkinIdx / ndPushBuffer nodes need 4 bytes each.
  * ndHeader: name*, u16 type, u16 flags, 0, runtime offset, 0, child*, sibling*, parent*.
  * A draw = ndRigidSkinIdx (palette of indices into the ndMtxArray entries) with one ndPushBuffer
    child (numDraws, then lists of index-data pointers / D3D primitive types / index counts;
    drawn with DrawIndexedVertices). Vertices store palette slots as float 24+3*slot.
  * Each ndShader2 has a rigid (1-bone) and a blend (2-bone) ndVertexShader variant; new geometry
    always goes under a blend variant's ndShaderParam2 (material).
"""
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import ghoul_dxt as dxt
import ghoul_model as gm

STREAMS = {9: ("pos", 12), 0: ("slots", 8), 8: ("weights", 8), 10: ("nrm", 12), 13: ("uv", 8), 11: ("col", 4)}
TRILIST = 5


def u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


@dataclass
class Vertex:
    pos: tuple
    nrm: tuple
    uv: tuple
    col: bytes          # 4 bytes as stored (D3DCOLOR)
    bones: tuple        # 1 or 2 skeleton bone indices
    weights: tuple      # matching weights
    deltas: tuple = ()  # face only: one position offset (x, y, z) per morph target


@dataclass
class Group:
    material: int                                # mesh-relative offset of the ndShaderParam2
    tris: list = field(default_factory=list)     # list of (Vertex, Vertex, Vertex)
    max_bones: int = 4                           # palette size limit per draw chunk


class Model:
    def __init__(self, descriptor: bytes, chunks: list):
        self.desc = bytearray(descriptor)
        self.chunks = [bytes(c) for c in chunks]
        self.res = b"".join(self.chunks)
        m = gm.read_model(bytes(self.desc))
        self.footer = m["footer"]
        self.mesh_off = m["meshes"][0]["offset"]
        self.mb = m["meshes"][0]["bytes"]
        self.roots = m["meshes"][0]["roots"]
        self.skel = self.roots[0]
        self.body_vb = next(c for c in self.skel.children if c.name == "ndVertexBuffer")
        self.mtx = next(c for c in self.body_vb.children if c.name == "ndMtxArray")
        # Each resource chunk is a separate XPhysicalAlloc at load time, so data must live in the
        # chunk its users address: vertex streams are offsets from the mesh base (chunk 0) and go
        # at the end of chunk 0; textures are located individually and go in a new last chunk.
        self.chunk0_extra = bytearray()
        self.new_chunk = bytearray()
        self.new_tex_fixups = []  # (descriptor offset of a texture record's offset field, local offset)

    # ---------------------------------------------------------------- helpers
    def mesh_ptr(self, data: bytes, align=4) -> int:
        """Append to the descriptor; return a MeshHeader-relative pointer."""
        while len(self.desc) % align:
            self.desc.append(0)
        p = len(self.desc)
        self.desc += data
        return p - self.mesh_off

    def desc_ptr(self, data: bytes, align=4) -> int:
        while len(self.desc) % align:
            self.desc.append(0)
        p = len(self.desc)
        self.desc += data
        return p

    def vertex_ptr(self, data: bytes, align=128) -> int:
        """Append vertex data to the end of chunk 0; return its resource-relative offset."""
        while len(self.chunk0_extra) % align:
            self.chunk0_extra.append(0)
        p = len(self.chunks[0]) + len(self.chunk0_extra)
        self.chunk0_extra += data
        return p

    def texture_local(self, data: bytes, align=4096) -> int:
        """Append texture data to the new last chunk; return its offset inside that chunk."""
        while len(self.new_chunk) % align:
            self.new_chunk.append(0)
        p = len(self.new_chunk)
        self.new_chunk += data
        return p

    def put(self, mesh_rel: int, fmt: str, *vals):
        struct.pack_into(fmt, self.desc, self.mesh_off + mesh_rel, *vals)

    def get(self, mesh_rel: int, fmt: str):
        return struct.unpack_from(fmt, self.desc, self.mesh_off + mesh_rel)

    def nodes(self, root=None):
        for r in ([root] if root else self.roots):
            for _, n in r.walk():
                yield n

    def materials(self):
        """(ndShader2 index, variant ('blend'/'rigid'), ndShaderParam2) for the body subtree."""
        out = []
        views = self.views()
        for si, sh2 in enumerate(self.mtx.children):
            for vs in sh2.children:
                two = 0
                for sp in vs.children:
                    for r in sp.children:
                        for pb in r.children:
                            for dr in pb.data["draws"]:
                                idx = set(struct.unpack_from(f"<{dr['count']}H", self.mb, dr["ptr"]))
                                two += sum(struct.unpack_from("<2f", self.res, views[8][0] + 8 * i)[1] > 0 for i in idx)
                for sp in vs.children:
                    out.append((si, "blend" if two else "rigid", sp))
        return out

    def views(self):
        out = {}
        for v in self.body_vb.data["views"]:
            if v["size"]:
                out[v["type"]] = (v["begin"], v["stride"], v["size"] // v["stride"])
        return out

    def texture_list(self):
        t7 = next(p for t, p in self.footer if t == 7)
        count, lst = struct.unpack_from("<II", self.desc, t7)
        return t7, count, lst

    # ---------------------------------------------------------------- decode
    def decode_groups(self):
        """Body geometry as Groups (one per ndShaderParam2 that draws something)."""
        views = self.views()
        entries = self.mtx.data["entries"]
        groups = []
        for _si, _var, sp in self.materials():
            g = Group(sp.off)
            biggest = 1
            for r in sp.children:
                pal = r.data["palette"]
                biggest = max(biggest, len(pal))
                for pb in r.children:
                    for dr in pb.data["draws"]:
                        idx = struct.unpack_from(f"<{dr['count']}H", self.mb, dr["ptr"])
                        cache = {}

                        def vert(i):
                            if i not in cache:
                                pos = struct.unpack_from("<3f", self.res, views[9][0] + 12 * i)
                                nrm = struct.unpack_from("<3f", self.res, views[10][0] + 12 * i) if 10 in views else (0, 1, 0)
                                uv = struct.unpack_from("<2f", self.res, views[13][0] + 8 * i) if 13 in views else (0, 0)
                                col = self.res[views[11][0] + 4 * i: views[11][0] + 4 * i + 4] if 11 in views else b"\xff" * 4
                                s = struct.unpack_from("<2f", self.res, views[0][0] + 8 * i)
                                w = struct.unpack_from("<2f", self.res, views[8][0] + 8 * i)
                                # the second slot is only meaningful when it carries weight
                                bones = [entries[pal[int(round((x - 24) / 3))]]["bone"]
                                         for x, wt in zip(s, (1.0, w[1])) if wt > 0]
                                if len(bones) == 2 and bones[1] != bones[0]:
                                    cache[i] = Vertex(pos, nrm, uv, col, (bones[0], bones[1]), (w[0], w[1]))
                                else:
                                    cache[i] = Vertex(pos, nrm, uv, col, (bones[0],), (1.0,))
                            return cache[i]

                        tris = triangles(idx, dr["prim"])
                        g.tris += [(vert(a), vert(b), vert(c)) for a, b, c in tris]
            g.max_bones = biggest
            if g.tris:
                groups.append(g)
        return groups

    # ---------------------------------------------------------------- textures
    def add_texture(self, rgba: np.ndarray, template_index: int) -> int:
        """Append a DXT1 texture (no mips); returns its index in the model's texture list."""
        h, w = rgba.shape[:2]
        t7, count, lst = self.texture_list()
        old_ptrs = [u32(self.desc, lst + 4 * i) for i in range(count)]
        rec = bytearray(self.desc[old_ptrs[template_index]: old_ptrs[template_index] + 0x40])
        data = dxt.encode_dxt1(rgba)
        local = self.texture_local(data)
        fmt, hs, _w, _h, flags = struct.unpack_from("<IIHHI", rec, 0)
        struct.pack_into("<IIHHI", rec, 0, 0x0C, hs, w, h, (flags & 0x00FFFFFF) | (1 << 24))
        struct.pack_into("<II", rec, 0x14, 0, len(data))  # offset patched in finish()
        rec_ptr = self.desc_ptr(bytes(rec), align=16)
        self.new_tex_fixups.append((rec_ptr + 0x14, local))
        new_list = self.desc_ptr(struct.pack(f"<{count + 1}I", *old_ptrs, rec_ptr), align=16)
        struct.pack_into("<II", self.desc, t7, count + 1, new_list)
        return count

    def replace_texture(self, index: int, rgba: np.ndarray):
        """Overwrite an existing single-level DXT1 texture in place (same size); no layout change."""
        _t7, count, lst = self.texture_list()
        rec = u32(self.desc, lst + 4 * index)
        fmt, _hs, w, h, flags = struct.unpack_from("<IIHHI", self.desc, rec)
        off, size = struct.unpack_from("<II", self.desc, rec + 0x14)
        if fmt != 0x0C or flags >> 24 != 1 or rgba.shape[:2] != (h, w):
            raise ValueError(f"texture {index}: need {w}x{h} single-level DXT1, got {rgba.shape[1]}x{rgba.shape[0]}")
        data = dxt.encode_dxt1(rgba)
        start = 0
        for k, c in enumerate(self.chunks):
            if off < start + len(c):
                local = off - start
                c = bytearray(c)
                c[local:local + size] = data[:size]
                self.chunks[k] = bytes(c)
                break
            start += len(c)
        self.res = b"".join(self.chunks)

    def hide_blend_shape(self):
        """Stop the blend-shape head drawing without touching the node tree (game code may look
        the node up): every index list becomes index 0 repeated, i.e. degenerate strips."""
        bs = next(c for c in self.skel.children if c.name == "ndBlendShape")
        for n in self.nodes(bs):
            if n.name == "ndPushBuffer":
                for dr in n.data["draws"]:
                    self.put(dr["ptr"], f"<{dr['count']}H", *([0] * dr["count"]))

    def set_material_texture(self, sp2_off: int, texture_index: int):
        """Point a material's 'colour0' texture slot at another model texture."""
        p = u32(self.mb, sp2_off + 0x20)
        tex_start, ntex = u32(self.mb, p + 8), u32(self.mb, p + 12)
        attr_start, nattr = u32(self.mb, p + 0x24), u32(self.mb, p + 0x28)
        for i in range(nattr):
            name_ptr, _v1, slot = struct.unpack_from("<III", self.mb, attr_start + 16 * i)
            if gm.cstr(self.mb, name_ptr) == "colour0" and slot < ntex:
                self.put(tex_start + 28 * slot, "<I", texture_index)
                return
        raise ValueError(f"material @ {sp2_off:#x} has no colour0 texture slot")

    # ---------------------------------------------------------------- geometry
    def face(self):
        """(ndBlendShape node, its vertex buffers: base first, then one per morph target)."""
        bs = next(c for c in self.skel.children if c.name == "ndBlendShape")
        return bs, [gm.Node(self.mb, p) for p in bs.data["vertex_buffers"]]

    def morph_target_names(self):
        return gm.morph_target_names(self.mb)

    def write_face(self, groups: list):
        """Replace the blend-shape head. Every vertex needs one delta per morph target
        (Vertex.deltas, same order as morph_target_names()); use (0, 0, 0) for no movement.
        Materials are ndShaderParam2s inside the ndBlendShape subtree."""
        bs, vbs = self.face()
        mtx = next(c for c in bs.children if c.name == "ndMtxArray")
        sps = [n for n in self.nodes(bs) if n.name == "ndShaderParam2"]
        return self.write_geometry(groups, vb=vbs[0], mtx=mtx, sps=sps, targets=vbs[1:])

    def write_geometry(self, groups: list, unlink_head=False, vb=None, mtx=None, sps=None, targets=()):
        # 1. chunk every group by bone budget, duplicating vertices per chunk
        chunks = []  # (material, palette(list of bones), local vertices, indices)
        for g in groups:
            cur_bones, cur_tris = [], []
            for tri in g.tris:
                need = {b for v in tri for b in v.bones}
                if len(set(cur_bones) | need) > g.max_bones and cur_tris:
                    chunks.append((g.material, cur_bones, cur_tris))
                    cur_bones, cur_tris = [], []
                for b in sorted(need):
                    if b not in cur_bones:
                        cur_bones.append(b)
                cur_tris.append(tri)
            if cur_tris:
                chunks.append((g.material, cur_bones, cur_tris))

        # 2. matrix-palette entries: one per used bone (flag 2 = bone matrix as-is)
        used = sorted({b for _m, pal, _t in chunks for b in pal})
        entry_of = {b: k for k, b in enumerate(used)}
        entries = b"".join(struct.pack("<HHBBBB", b, 0xFFFF, 0x7F, 2, 0xFF, 0) for b in used)
        vb = vb or self.body_vb
        mtx = mtx or self.mtx
        if sps is None:
            sps = [sp for _si, _var, sp in self.materials()]
        self.put(mtx.off + 0x20, "<II", self.mesh_ptr(entries), len(used))

        # 3. vertex streams
        P, N, UV, C, S, W, D, draws = [], [], [], [], [], [], [], []
        for mat, pal, tris in chunks:
            slot = {b: k for k, b in enumerate(pal)}
            local, index = {}, []
            for tri in tris:
                for v in tri:
                    key = id(v)
                    if key not in local:
                        local[key] = len(P)
                        P.append(v.pos)
                        N.append(v.nrm)
                        UV.append(v.uv)
                        C.append(v.col)
                        s = [24.0 + 3 * slot[b] for b in v.bones] + [0.0]
                        w = list(v.weights) + [0.0]
                        S.append((s[0], s[1] if len(v.bones) > 1 else 0.0))
                        W.append((w[0], w[1] if len(v.bones) > 1 else 0.0))
                        if targets:
                            if len(v.deltas) != len(targets):
                                raise ValueError(f"vertex has {len(v.deltas)} deltas, need {len(targets)}")
                            D.append(v.deltas)
                    index.append(local[key])
            draws.append((mat, [entry_of[b] for b in pal], index))
        if len(P) > 65535:
            raise ValueError(f"{len(P)} vertices: too many for 16-bit indices")
        stream_data = {
            9: np.asarray(P, "<f4").tobytes(), 10: np.asarray(N, "<f4").tobytes(),
            13: np.asarray(UV, "<f4").tobytes(), 11: b"".join(C),
            0: np.asarray(S, "<f4").tobytes(), 8: np.asarray(W, "<f4").tobytes(),
        }
        where = {}
        vp = u32(self.mb, vb.off + 0x20)
        for k, v in enumerate(vb.data["views"]):
            if v["type"] in stream_data:
                data = stream_data[v["type"]]
                where[v["type"]] = (self.vertex_ptr(data), len(data))
                self.put(vp + 0x18 * k + 0x10, "<II", *where[v["type"]])
        # morph targets: position offsets of their own, zero normal offsets, the rest shared
        zero_nrm = self.vertex_ptr(bytes(len(stream_data[10]))) if targets else None
        for t, tvb in enumerate(targets):
            tvp = u32(self.mb, tvb.off + 0x20)
            for k, v in enumerate(tvb.data["views"]):
                if not v["size"]:
                    continue
                if v["type"] == 9:
                    data = np.asarray([d[t] for d in D], "<f4").tobytes()
                    self.put(tvp + 0x18 * k + 0x10, "<II", self.vertex_ptr(data), len(data))
                elif v["type"] == 10:
                    self.put(tvp + 0x18 * k + 0x10, "<II", zero_nrm, len(stream_data[10]))
                elif v["type"] in where:
                    self.put(tvp + 0x18 * k + 0x10, "<II", *where[v["type"]])

        # 4. draw nodes under each material; detach every other material's draws
        tmpl_rsi = next(n for n in self.nodes(mtx) if n.name == "ndRigidSkinIdx")
        tmpl_pb = next(n for n in self.nodes(mtx) if n.name == "ndPushBuffer")
        rsi_hdr = bytes(self.mb[tmpl_rsi.off: tmpl_rsi.off + 0x28])
        pb_hdr = bytes(self.mb[tmpl_pb.off: tmpl_pb.off + 0x40])
        varsize = self.get(0, "<I")[0]
        by_mat = {}
        for mat, pal, index in draws:
            by_mat.setdefault(mat, []).append((pal, index))
        for sp in sps:
            if sp.off not in by_mat:
                self.put(sp.off + 0x14, "<I", 0)
        for mat, items in by_mat.items():
            rsi_offs = []
            for pal, index in items:
                idx_ptr = self.mesh_ptr(struct.pack(f"<{len(index)}H", *index))
                lists = self.mesh_ptr(struct.pack("<III", idx_ptr, TRILIST, len(index)))
                pal_ptr = self.mesh_ptr(bytes(pal))
                rsi = bytearray(rsi_hdr)
                pb = bytearray(pb_hdr)
                rsi_off = self.mesh_ptr(bytes(rsi))
                pb_off = self.mesh_ptr(bytes(pb))
                # header fields: runtime slot, child, sibling, parent
                self.put(rsi_off + 0x0C, "<I", varsize)
                self.put(pb_off + 0x0C, "<I", varsize + 4)
                varsize += 8
                self.put(rsi_off + 0x14, "<III", pb_off, 0, mat)
                self.put(rsi_off + 0x20, "<II", pal_ptr, len(pal))
                self.put(pb_off + 0x14, "<III", 0, 0, rsi_off)
                self.put(pb_off + 0x20, "<IIII", 1, 0, 0, 0)
                self.put(pb_off + 0x30, "<III", lists, lists + 4, lists + 8)
                rsi_offs.append(rsi_off)
            for a, b in zip(rsi_offs, rsi_offs[1:]):
                self.put(a + 0x18, "<I", b)
            self.put(mat + 0x14, "<I", rsi_offs[0])
        self.put(0, "<I", varsize)

        # 5. optionally drop the blend-shape head (Cooper's face)
        if unlink_head:
            self.put(self.body_vb.off + 0x18, "<I", 0)
        return {"chunks": len(chunks), "vertices": len(P), "triangles": sum(len(i) for _p, i in
                [(d[1], d[2]) for d in draws]) // 3, "bones": len(used)}

    def relocate_vertex_streams(self):
        """Test helper: copy the body VB's original streams to the end of chunk 0 and repoint
        the views, changing nothing else."""
        vp = u32(self.mb, self.body_vb.off + 0x20)
        for k, v in enumerate(self.body_vb.data["views"]):
            if v["size"]:
                data = self.res[v["begin"]: v["begin"] + v["size"]]
                self.put(vp + 0x18 * k + 0x10, "<II", self.vertex_ptr(data), len(data))

    def finish(self):
        """Return (descriptor, resource chunks)."""
        chunks = list(self.chunks)
        old0 = len(chunks[0])
        if self.chunk0_extra:
            while len(self.chunk0_extra) % 128:
                self.chunk0_extra.append(0)
            chunks[0] = chunks[0] + bytes(self.chunk0_extra)
        delta = len(chunks[0]) - old0
        # chunk 0 grew: shift every existing texture that lives in a later chunk
        t7, count, lst = self.texture_list()
        new_recs = {fix for fix, _ in self.new_tex_fixups}
        for i in range(count):
            rec = u32(self.desc, lst + 4 * i)
            off, size = struct.unpack_from("<II", self.desc, rec + 0x14)
            if rec + 0x14 not in new_recs and size and off >= old0:
                struct.pack_into("<I", self.desc, rec + 0x14, off + delta)
        if self.new_chunk:
            while len(self.new_chunk) % 128:
                self.new_chunk.append(0)
            base = sum(len(c) for c in chunks)
            for fix, local in self.new_tex_fixups:
                struct.pack_into("<I", self.desc, fix, base + local)
            chunks.append(bytes(self.new_chunk))
        return bytes(self.desc), chunks


def triangles(idx, prim):
    out = []
    if prim == 6:
        for i in range(len(idx) - 2):
            a, b, c = (idx[i], idx[i + 1], idx[i + 2]) if i % 2 == 0 else (idx[i + 1], idx[i], idx[i + 2])
            if a != b and b != c and a != c:
                out.append((a, b, c))
    elif prim == 5:
        out = [tuple(idx[i:i + 3]) for i in range(0, len(idx) - 2, 3)]
    return out
