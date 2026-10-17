import bpy, sys, math
from mathutils import Vector
a = sys.argv[sys.argv.index("--")+1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=a[0], forward_axis='Y', up_axis='NEGATIVE_Z')
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light='STUDIO'; sc.display.shading.color_type='TEXTURE'
sc.render.resolution_x = sc.render.resolution_y = 300
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type='ORTHO'
objs=[o for o in sc.objects if o.type=="MESH"]
for o in objs:
    for p in objs: p.hide_render = p is not o
    bb=[o.matrix_world@Vector(c) for c in o.bound_box]
    lo=Vector([min(v[i] for v in bb) for i in range(3)]); hi=Vector([max(v[i] for v in bb) for i in range(3)])
    c=(lo+hi)/2; size=max(hi-lo)*1.2
    for view,rot,off in (("front",(math.radians(90),0,0),Vector((0,-5,0))),("side",(math.radians(90),0,math.radians(90)),Vector((5,0,0)))):
        cam.location=c+off; cam.rotation_euler=rot; cam.data.ortho_scale=size
        sc.render.filepath=f"{a[1]}/{o.name[-5:]}_{view}.png"; bpy.ops.render.render(write_still=True)
