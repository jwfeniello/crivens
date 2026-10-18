"""Blender headless: render a front head close-up for every shape key of the face mesh.
usage: blender -b --python bl_face_targets.py -- <in.glb> <out_prefix>
Writes <out_prefix>_00.png (no key) and <out_prefix>_NN.png (key NN at 1.0).
"""
import math
import sys

import bpy
from mathutils import Vector

src, prefix = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == "ARMATURE")
scene.render.engine = "BLENDER_WORKBENCH"
scene.display.shading.light = "STUDIO"
scene.display.shading.color_type = "TEXTURE"
scene.render.resolution_x = scene.render.resolution_y = 360
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam_data.ortho_scale = 6
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
head = arm.pose.bones.get("HEAD")
hpos = arm.matrix_world @ head.head if head else Vector((0, 0, 14))
cam.location = hpos + Vector((0, -40, 1.8))
cam.rotation_euler = (math.radians(90), 0, 0)
face = next(m for m in scene.objects if m.type == "MESH" and m.data.shape_keys)
keys = face.data.shape_keys.key_blocks
for k in range(len(keys)):
    for kb in keys[1:]:
        kb.value = 0.0
    if k:
        keys[k].value = 1.0
    scene.render.filepath = f"{prefix}_{k:02d}.png"
    bpy.ops.render.render(write_still=True)
print("FACE TARGETS DONE", len(keys) - 1)
