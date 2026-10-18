"""Blender: make a .blend for sculpting a character's facial expressions as shape keys.

usage: blender -b --python bl_face_template.py -- <in.dae> <out.blend> <part suffix,...> [names]
Imports the Collada file, keeps the listed parts and gives each one a Basis key plus one empty
shape key per expression. names defaults to Cooper's twelve morph targets; sculpt any of them, save,
and export with bl_sonic_export.py (give it the .blend). Keys left untouched don't move anything.
"""
import sys

import bpy

TARGETS = ["BLINK", "ANGRY", "ANGRY1", "HIT", "MOUTH_OPEN", "SMILE", "HIT1", "HIT2", "HAIR_SPIKE",
           "SCARED", "RAISE_BROW", "CHEEK_BLOW"]

args = sys.argv[sys.argv.index("--") + 1:]
dae, out, keep = args[0], args[1], args[2].split(",")
names = args[3].split(",") if len(args) > 3 else TARGETS
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.collada_import(filepath=dae)
for o in list(bpy.data.objects):
    if o.type == "MESH" and not any(o.name.endswith(k) for k in keep):
        bpy.data.objects.remove(o, do_unlink=True)
for o in bpy.data.objects:
    if o.type == "MESH":
        o.shape_key_add(name="Basis", from_mix=False)
        for n in names:
            o.shape_key_add(name=n, from_mix=False)
bpy.ops.wm.save_as_mainfile(filepath=out)
print("saved", out, "with shape keys", names)
