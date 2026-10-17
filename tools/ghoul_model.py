"""Grabbed by the Ghoulies model (nd tree) reader, using struct layouts from the
ghoulies-decomp Ghidra project.

Model descriptor: u32 footer_ptr, u32 num_footer; footer = (u32 type, u32 offset)*.
  type 0 = mesh list (u32 ptrs, 0-terminated) -> MeshHeader; nd offsets inside a mesh are
  relative to the MeshHeader start. type 9 = rigid bone indices (u8[]). type 5 = matrices.
ndHeader (0x20): name*, u16 type, u16 drawMask, ?, matrixList, ctx, child*, sibling*, prev*.
"""
import struct

ND_TYPES = {0x1: "ndGroup", 0x2: "ndSkeleton", 0xB: "ndRigidSkinIdx", 0xC: "ndMtxArray",
            0x11: "ndShader2", 0x12: "ndShaderParam2", 0x13: "ndVertexBuffer", 0x14: "ndPushBuffer",
            0x15: "ndVertexShader", 0x16: "ndBGPushBuffer", 0x17: "ndBlendShape"}


def u32(d, o):
    return struct.unpack_from("<I", d, o)[0]


def cstr(d, o):
    e = d.index(b"\0", o)
    return d[o:e].decode("latin-1")


class Node:
    def __init__(self, mesh, off):
        d = mesh
        self.off = off
        self.name = cstr(d, u32(d, off))
        self.type, self.draw_mask = struct.unpack_from("<HH", d, off + 4)
        self.child_ptr, self.sibling_ptr = u32(d, off + 0x14), u32(d, off + 0x18)
        self.children = []
        self.data = {}
        t = self.name
        if t == "ndSkeleton":
            n, p = u32(d, off + 0x20), u32(d, off + 0x24)
            bones = []
            for i in range(n):
                par, bid = struct.unpack_from("<HH", d, p + i * 0x20)
                bind = struct.unpack_from("<3f", d, p + i * 0x20 + 4)
                glob = struct.unpack_from("<3f", d, p + i * 0x20 + 0x10)
                bones.append({"parent": par, "id": bid, "bind": bind, "global": glob})
            self.data["bones"] = bones
        elif t == "ndMtxArray":
            sp, sn = u32(d, off + 0x20), u32(d, off + 0x24)
            mp, mn = u32(d, off + 0x2C), u32(d, off + 0x30)
            ents = []
            for i in range(sn):
                idx, _u, _a, flag, mi, _b = struct.unpack_from("<HHBBBB", d, sp + i * 8)
                ents.append({"bone": idx, "flag": flag, "matrix": mi})
            mats = [struct.unpack_from("<16f", d, mp + i * 64) for i in range(mn)] if mp else []
            self.data.update(entries=ents, matrices=mats)
        elif t == "ndRigidSkinIdx":
            ip, n = u32(d, off + 0x20), u32(d, off + 0x24)
            self.data["palette"] = list(d[ip:ip + n])
        elif t == "ndVertexBuffer":
            vp, n = u32(d, off + 0x20), u32(d, off + 0x24)
            views = []
            for i in range(n):
                stride, rtype, ident, _r, u1, u2, begin, size = struct.unpack_from("<BBHIIIII", d, vp + i * 0x18)
                views.append({"stride": stride, "type": rtype, "id": ident, "u1": u1, "u2": u2, "begin": begin, "size": size})
            self.data["views"] = views
        elif t in ("ndPushBuffer", "ndBGPushBuffer"):
            n = u32(d, off + 0x20)
            dp, tp, cp = u32(d, off + 0x30), u32(d, off + 0x34), u32(d, off + 0x38)
            draws = []
            for i in range(n):
                draws.append({"ptr": u32(d, dp + 4 * i), "prim": u32(d, tp + 4 * i), "count": u32(d, cp + 4 * i)})
            self.data["draws"] = draws
        elif t == "ndBlendShape":
            vp, n = u32(d, off + 0x20), u32(d, off + 0x24)
            self.data["vertex_buffers"] = [u32(d, vp + 4 * i) for i in range(n)]
        elif t == "ndVertexShader":
            sp, n = u32(d, off + 0x20), u32(d, off + 0x24)
            self.data["streams"] = [struct.unpack_from("<BBH", d, sp + i * 0x18) for i in range(n)] if sp else []
            self.data["raw"] = d[off + 0x20: off + 0x68].hex()

    def walk(self, depth=0):
        yield depth, self
        for c in self.children:
            yield from c.walk(depth + 1)


def build(mesh, off, seen):
    nodes = []
    while off and off not in seen:
        seen.add(off)
        n = Node(mesh, off)
        n.children = build(mesh, n.child_ptr, seen)
        nodes.append(n)
        off = n.sibling_ptr
    return nodes


def read_model(desc):
    footer_ptr, nfoot = u32(desc, 0), u32(desc, 4)
    footer = [struct.unpack_from("<II", desc, footer_ptr + 8 * i) for i in range(nfoot)]
    meshes, rigid_bones = [], None
    for typ, ptr in footer:
        if typ == 0:
            p = ptr
            while u32(desc, p):
                mstart = u32(desc, p)
                mesh = desc[mstart:]
                prim_start, prim_count = u32(mesh, 8), u32(mesh, 12)
                roots = []
                seen = set()
                for i in range(prim_count):
                    roots += build(mesh, u32(mesh, prim_start + 4 * i), seen)
                meshes.append({"offset": mstart, "roots": roots, "bytes": mesh})
                p += 4
        elif typ == 9:
            rigid_bones = ptr
    return {"footer": footer, "meshes": meshes, "rigid_bones_ptr": rigid_bones}
