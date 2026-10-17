"""Blender headless: import a .glb, render front/side views of an action at several frames.
usage: blender -b --python bl_render.py -- <in.glb> <out_prefix> [action_substring] [n_frames]
Writes <out_prefix>_<action>_<frame>_<view>.png and prints import stats.
"""
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, prefix = args[0], args[1]
want = args[2] if len(args) > 2 else ""
nframes = int(args[3]) if len(args) > 3 else 4

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
scene = bpy.context.scene
arm = next((o for o in scene.objects if o.type == "ARMATURE"), None)
meshes = [o for o in scene.objects if o.type == "MESH"]
print("IMPORT armature:", arm.name if arm else None, "bones:", len(arm.data.bones) if arm else 0,
      "meshes:", len(meshes), "actions:", len(bpy.data.actions),
      "skinned:", sum(1 for m in meshes if any(md.type == "ARMATURE" for md in m.modifiers)),
      "shape keys:", sum(len(m.data.shape_keys.key_blocks) - 1 for m in meshes if m.data.shape_keys))

scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = 360
scene.render.resolution_y = 480
scene.render.film_transparent = False
scene.world = bpy.data.worlds.new("w") if not scene.world else scene.world

cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


def bounds():
    pts = []
    dg = bpy.context.evaluated_depsgraph_get()
    for m in meshes:
        e = m.evaluated_get(dg)
        pts += [e.matrix_world @ Vector(c) for c in e.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def shoot(path, view):
    lo, hi = bounds()
    c = (lo + hi) / 2
    size = max(hi - lo) * 1.15
    cam_data.ortho_scale = size
    d = size * 3
    cam_data.clip_start = size * 0.01
    cam_data.clip_end = d * 4  # default 100 units clips large level models
    if view == "top":
        cam.location = (c.x, c.y, c.z + d)
        cam.rotation_euler = (0, 0, 0)
    elif view == "front":  # glTF +Z (front) maps to Blender -Y
        cam.location = (c.x, c.y - d, c.z)
        cam.rotation_euler = (math.radians(90), 0, 0)
    else:  # side: look from +X
        cam.location = (c.x + d, c.y, c.z)
        cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


actions = [a for a in bpy.data.actions if want in a.name] if arm else []
if not actions:
    # true rest pose: the importer otherwise leaves the first animation applied
    if arm and arm.animation_data:
        arm.animation_data.action = None
    if arm:
        for pb in arm.pose.bones:
            pb.matrix_basis.identity()
        arm.location = (0, 0, 0)
        arm.rotation_quaternion = (1, 0, 0, 0)
    for m in meshes:
        if m.data.shape_keys and m.data.shape_keys.animation_data:
            m.data.shape_keys.animation_data.action = None
    bpy.context.view_layer.update()
    shoot(f"{prefix}_rest_front.png", "front")
    shoot(f"{prefix}_rest_side.png", "side")
    if not arm:  # static scenery: a plan view shows the room layout
        shoot(f"{prefix}_rest_top.png", "top")
for act in actions[:2]:
    arm.animation_data_create()
    arm.animation_data.action = act
    if hasattr(arm.animation_data, "action_slot") and act.slots:
        arm.animation_data.action_slot = act.slots[0]
    f0, f1 = act.frame_range
    for i in range(nframes):
        f = round(f0 + (f1 - f0) * i / max(nframes - 1, 1))
        scene.frame_set(f)
        safe = act.name.replace("/", "_")[:40]
        for view in ("front", "side"):
            shoot(f"{prefix}_{safe}_{f:03d}_{view}.png", view)
print("RENDER DONE")
