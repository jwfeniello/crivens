"""Blender: dump a skinned Collada character (Sonic Unleashed rip) to an .npz for sonic_build.py.

usage: blender -b --python bl_sonic_export.py -- <in.dae> <out.npz> <part suffix,...>
Writes per triangle corner: position, normal, uv, material texture name, 4 strongest bone weights;
plus bone names and rest head positions (all in the file's own space, Y-up, +Z forward).
"""
import sys

import bmesh
import bpy
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
dae, out, keep = args[0], args[1], args[2].split(",")
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.collada_import(filepath=dae)
arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
bone_names = [b.name for b in arm.data.bones]
heads = np.array([list(arm.matrix_world @ b.head_local) for b in arm.data.bones], "f4")
parents = [bone_names.index(b.parent.name) if b.parent else -1 for b in arm.data.bones]

P, N, UV, MAT, BI, BW, PART = [], [], [], [], [], [], []
tex_names = []
dg = bpy.context.evaluated_depsgraph_get()
max_shift = 0.0
for o in bpy.data.objects:
    if o.type != "MESH" or not any(o.name.endswith(k) for k in keep):
        continue
    # rest-pose geometry must equal the bind geometry (else the rig's rest != bind)
    ev = o.evaluated_get(dg).to_mesh()
    a = np.array([list(o.matrix_world @ v.co) for v in o.data.vertices])
    b = np.array([list(o.matrix_world @ v.co) for v in ev.vertices])
    max_shift = max(max_shift, float(np.abs(a - b).max()))
    o.evaluated_get(dg).to_mesh_clear()

    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    uvl = bm.loops.layers.uv.active
    dl = bm.verts.layers.deform.active
    groups = {g.index: g.name for g in o.vertex_groups}
    nm = o.matrix_world.to_3x3().inverted().transposed()
    mats = []
    for slot in o.material_slots:
        img = None
        if slot.material and slot.material.use_nodes:
            img = next((n.image.name for n in slot.material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
        mats.append(img or (slot.material.name if slot.material else "none"))
    for f in bm.faces:
        tname = mats[f.material_index] if mats else "none"
        if tname not in tex_names:
            tex_names.append(tname)
        for loop in f.loops:
            v = loop.vert
            P.append(list(o.matrix_world @ v.co))
            n = (nm @ (v.normal if not f.smooth else v.normal)).normalized()
            N.append(list(n))
            UV.append(list(loop[uvl].uv) if uvl else [0, 0])
            MAT.append(tex_names.index(tname))
            ws = sorted(((w, bone_names.index(groups[g])) for g, w in (v[dl].items() if dl else [])
                         if groups.get(g) in bone_names and w > 0), reverse=True)[:4]
            ws += [(0.0, 0)] * (4 - len(ws))
            BI.append([i for _w, i in ws])
            BW.append([w for w, _i in ws])
            PART.append(o.name)
    bm.free()

print("max rest-vs-bind vertex shift:", max_shift)
print("materials:", tex_names, "corners:", len(P))
np.savez(out, pos=np.array(P, "f4"), nrm=np.array(N, "f4"), uv=np.array(UV, "f4"), mat=np.array(MAT, "i4"),
         bi=np.array(BI, "i4"), bw=np.array(BW, "f4"), part=np.array(PART), tex_names=np.array(tex_names),
         bone_names=np.array(bone_names), heads=heads, parents=np.array(parents, "i4"))
print("saved", out)
