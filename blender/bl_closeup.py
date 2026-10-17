"""Blender headless: rest-pose head close-ups from -Y (glTF front), +Y (back), and with shape keys.
usage: blender -b --python bl_closeup.py -- <in.glb> <out_prefix>
"""
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
src, prefix = args[0], args[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
meshes = [o for o in scene.objects if o.type == "MESH"]
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "FLAT"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 420
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

head = arm.pose.bones.get("HEAD")
hpos = arm.matrix_world @ head.head if head else Vector((0, 0, 14))
cam_data.ortho_scale = 9
for name, loc, rot in (("front", (0, -40, 0), (90, 0, 0)), ("back", (0, 40, 0), (90, 0, 180)),
                       ("left", (40, 0, 0), (90, 0, 90))):
    cam.location = hpos + Vector(loc) + Vector((0, 0, 1.5))
    cam.rotation_euler = [math.radians(a) for a in rot]
    scene.render.filepath = f"{prefix}_{name}.png"
    bpy.ops.render.render(write_still=True)

face = next((m for m in meshes if m.data.shape_keys), None)
cam.location = hpos + Vector((0, -40, 1.5))
cam.rotation_euler = (math.radians(90), 0, 0)
if face:
    keys = face.data.shape_keys.key_blocks
    print("SHAPE KEYS", [k.name for k in keys])
    for k in (1, 4, 8, 12):
        if k < len(keys):
            for kb in keys[1:]:
                kb.value = 0.0
            keys[k].value = 1.0
            scene.render.filepath = f"{prefix}_shape{k}.png"
            bpy.ops.render.render(write_still=True)
print("CLOSEUP DONE")
