"""Windowed check in a SEPARATE Blender process (never your open session).

blender.exe --factory-startup --enable-event-simulate --python tests/check_windowed.py
Simulated events: real modal watcher -> pause -> resume, unregister safety.
"""
import os, sys, bpy, addon_utils
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("RSG_OUT", "rsg_windowed.txt")
lines = []
addon_utils.enable("resource_safeguard", default_set=True)
import resource_safeguard as rsg

def win():
    return bpy.context.window_manager.windows[0]

def ops():
    return [(op.bl_idname if op is not None else "None") for op in win().modal_operators]

def move(x):
    win().event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=300)

def v3d():
    for a in win().screen.areas:
        if a.type == 'VIEW_3D':
            return a.spaces.active

def finish():
    with open(OUT, "w") as f: f.write("\n".join(lines))
    bpy.ops.wm.quit_blender()

def s5():
    lines.append("after_disable_events_ok ops=%s" % ops())
    finish()

def s4():
    lines.append("after_return=%s status=%s" % (v3d().shading.type, rsg._State.controller.status_text()))
    addon_utils.disable("resource_safeguard", default_set=True)
    lines.append("disabled ops=%s" % ops())
    for i in range(5): move(400 + i)   # events after unregister must not crash
    bpy.app.timers.register(s5, first_interval=1.0)

def s3():
    lines.append("after_idle=%s status=%s acted=%s" % (v3d().shading.type, rsg._State.controller.status_text(), rsg._State.controller.acted))
    move(350)   # user comes back
    bpy.app.timers.register(s4, first_interval=0.5)

def s2():
    move(310)
    lines.append("countdown=%s" % rsg._State.controller.status_text())
    bpy.app.timers.register(s3, first_interval=3.5)

def s1():
    lines.append("ops=%s watchers=%d" % (ops(), len(rsg._State.watchers)))
    bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    p = rsg.get_prefs()
    p.enabled = True; p.timeout_preset = 'CUSTOM'; p.custom_seconds = 2
    v3d().shading.type = 'RENDERED'
    move(300)
    bpy.app.timers.register(s2, first_interval=1.2)

bpy.app.timers.register(s1, first_interval=2.0)
