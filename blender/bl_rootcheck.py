"""Blender headless: report armature object location over an action (root motion check)."""
import sys
import bpy
args = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=args[0])
arm = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")
act = next(a for a in bpy.data.actions if args[1] in a.name)
arm.animation_data.action = act
if hasattr(arm.animation_data, "action_slot") and act.slots:
    arm.animation_data.action_slot = act.slots[0]
f0, f1 = act.frame_range
for f in (f0, (f0 + f1) / 2, f1):
    bpy.context.scene.frame_set(int(f))
    print("ROOT frame", int(f), "armature location", tuple(round(c, 3) for c in arm.matrix_world.translation))
