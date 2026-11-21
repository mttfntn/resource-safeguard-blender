"""Windowed check in a SEPARATE Blender process (never your open session).

blender.exe --factory-startup --enable-event-simulate --python tests/check_topbar_redraw.py
Verifies the top bar countdown is redrawn every second with no user input.
"""
import os
import sys

import bpy
import addon_utils

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("RSG_OUT", "rsg_topbar.txt")
addon_utils.enable("resource_safeguard", default_set=True)
import resource_safeguard as rsg

drawn = []
_orig = rsg.core.format_seconds


def spy(seconds):
    text = _orig(seconds)
    drawn.append(text)
    return text


def start():
    p = rsg.get_prefs()
    p.enabled = True
    p.show_timer = True
    p.timeout_preset = '30'
    bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    for a in bpy.context.window_manager.windows[0].screen.areas:
        if a.type == 'VIEW_3D':
            a.spaces.active.shading.type = 'RENDERED'
    rsg.core.format_seconds = spy
    bpy.app.timers.register(finish, first_interval=6.0)


def finish():
    rsg.core.format_seconds = _orig
    with open(OUT, "w") as f:
        f.write("topbar_areas=%s\n" % [a.type for a in rsg._State.topbar_areas.values()])
        f.write("drawn=%s\n" % drawn)
        f.write("distinct=%d\n" % len(set(drawn)))
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(start, first_interval=2.0)
