"""Blender headless: import glTF, sample world-space joint positions for each action.
usage: blender -b --python bl_sample.py -- <in.gltf> <out.json> [frames_per_action]
"""
import json
import sys

import bpy

args = sys.argv[sys.argv.index("--") + 1:]
src, dst = args[0], args[1]
nsamp = int(args[2]) if len(args) > 2 else 6

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)

arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
out = {
    "actions": [],
    "bones": [b.name for b in arm.data.bones],
    "parents": [b.parent.name if b.parent else None for b in arm.data.bones],
    "mesh_count": len(meshes),
    "mesh_parented_to_armature": sum(1 for m in meshes if m.parent == arm or any(md.type == "ARMATURE" for md in m.modifiers)),
}
scene = bpy.context.scene
arm.animation_data_create()
for act in bpy.data.actions:
    arm.animation_data.action = act
    # Blender 4.4+ slotted actions
    if hasattr(arm.animation_data, "action_slot") and act.slots:
        arm.animation_data.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    frames = [round(f0 + (f1 - f0) * i / max(nsamp - 1, 1)) for i in range(nsamp)]
    poses = []
    for f in frames:
        scene.frame_set(f)
        poses.append([list(arm.matrix_world @ pb.head) for pb in arm.pose.bones])
    out["actions"].append({"name": act.name, "frames": frames, "range": [f0, f1], "poses": poses})

json.dump(out, open(dst, "w"))
print("SAMPLED", len(out["actions"]), "actions,", len(out["bones"]), "bones,", out["mesh_count"], "meshes")
