"""Windowed check in a SEPARATE Blender process (never your open session).

blender.exe --factory-startup --enable-event-simulate --python tests/check_animation_pause.py
Plays the animation in a Rendered viewport and checks that, at the end of the
timer, playback stops and the viewport goes to Solid. Optional screenshots of
the top bar go to IRP_SHOT (a folder) when set.
"""
import os
import sys

import bpy
import addon_utils

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("IRP_OUT", "irp_anim.txt")
SHOT = os.environ.get("IRP_SHOT")
addon_utils.enable("idle_render_pause", default_set=True)
import idle_render_pause as irp

lines = []


def win():
    return bpy.context.window_manager.windows[0]


def v3d():
    for a in win().screen.areas:
        if a.type == 'VIEW_3D':
            return a.spaces.active


def shoot(name):
    if not SHOT:
        return
    w = win()
    with bpy.context.temp_override(window=w, screen=w.screen, area=w.screen.areas[0]):
        bpy.ops.screen.screenshot(filepath=os.path.join(SHOT, name), check_existing=False)


def start():
    p = irp.get_prefs()
    p.enabled = True
    p.show_timer = True
    p.pause_animation = True
    p.switch_to_solid = True
    p.timeout_preset = 'CUSTOM'
    p.custom_seconds = 4
    bpy.context.scene.render.engine = 'BLENDER_WORKBENCH'
    bpy.context.scene.frame_end = 100000
    v3d().shading.type = 'RENDERED'
    w = win()
    with bpy.context.temp_override(window=w, screen=w.screen):
        bpy.ops.screen.animation_play()
    irp._State.controller.reset()
    bpy.app.timers.register(during, first_interval=1.6)


def during():
    lines.append("during: playing=%s shading=%s text=%s" % (
        win().screen.is_animation_playing, v3d().shading.type, irp.timer_text(irp.get_prefs())))
    shoot("tb_running.png")
    bpy.app.timers.register(after, first_interval=4.0)


def after():
    lines.append("after: playing=%s shading=%s text=%s frame=%d" % (
        win().screen.is_animation_playing, v3d().shading.type,
        irp.timer_text(irp.get_prefs()), bpy.context.scene.frame_current))
    shoot("tb_paused.png")
    if SHOT:
        w = win()
        with bpy.context.temp_override(window=w, screen=w.screen):
            bpy.ops.wm.call_panel(name="IRP_PT_idle_menu", keep_open=True)
    bpy.app.timers.register(menu, first_interval=1.0)


def menu():
    shoot("tb_menu.png")
    irp.get_prefs().enabled = False
    bpy.app.timers.register(off, first_interval=1.0)


def off():
    shoot("tb_off.png")
    with open(OUT, "w") as f:
        f.write("\n".join(lines))
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(start, first_interval=2.0)
