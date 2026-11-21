"""Headless tests for Resource Safeguard.

Run (never inside your open Blender session):
    blender.exe -b --factory-startup --python tests/test_resource_safeguard.py
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)

import bpy
import addon_utils

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (("  -- " + detail) if (detail and not cond) else ""))


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class FakeShading:
    def __init__(self, t):
        self.type = t


class FakeSpace:
    _next = 1

    def __init__(self, t):
        self.shading = FakeShading(t)
        self._ptr = FakeSpace._next
        FakeSpace._next += 1

    def as_pointer(self):
        return self._ptr


# --------------------------------------------------------------- core logic
def test_core():
    from resource_safeguard import core

    clock = FakeClock()
    r1, r2, s1, m1 = FakeSpace('RENDERED'), FakeSpace('RENDERED'), FakeSpace('SOLID'), FakeSpace('MATERIAL')
    spaces = [r1, r2, s1, m1]
    vis = lambda: list(spaces)
    anim = {"playing": False, "stops": 0}

    def stop():
        anim["stops"] += 1
        anim["playing"] = False

    c = core.IdleController(clock=clock)

    def run(enabled=True, timeout=30, render=False, solid=True, pause_anim=True, hold=False):
        return c.tick(enabled, timeout, vis, render, switch_to_solid=solid, hold=hold,
                      animation_playing=anim["playing"], pause_animation=pause_anim,
                      stop_animation=stop)

    # Countdown with a Rendered viewport
    clock.advance(10)
    check("core: countdown status", run() == core.STATUS_COUNTDOWN)
    check("core: countdown text", c.status_text() == "Idle pause in 0:20", c.status_text())

    # Input resets idle
    c.note_input()
    clock.advance(25)
    check("core: input resets idle", run() == core.STATUS_COUNTDOWN and abs(c.remaining - 5) < 1e-6)

    # Timer end: only RENDERED spaces go to Solid
    clock.advance(5)
    check("core: pause at timeout", run() == core.STATUS_PAUSED)
    check("core: rendered -> solid", r1.shading.type == 'SOLID' and r2.shading.type == 'SOLID')
    check("core: other spaces untouched", s1.shading.type == 'SOLID' and m1.shading.type == 'MATERIAL')
    check("core: paused text", c.status_text() == "Paused (idle)")
    clock.advance(100)
    check("core: still paused", run() == core.STATUS_PAUSED)

    # Return: nothing is switched back; stays paused until something runs again
    c.note_input()
    check("core: no auto-restore", r1.shading.type == 'SOLID' and r2.shading.type == 'SOLID')
    check("core: paused after return while nothing runs", run() == core.STATUS_PAUSED)
    r1.shading.type = 'RENDERED'  # user switches back
    check("core: manual rendered restarts countdown", run() == core.STATUS_COUNTDOWN
          and abs(c.remaining - 30) < 1e-6)

    # Animation playing (no Rendered viewport) -> countdown, then stop playback
    r1.shading.type = 'SOLID'
    c = core.IdleController(clock=clock)
    anim["playing"] = True
    clock.advance(10)
    check("core: animation alone counts down", run() == core.STATUS_COUNTDOWN)
    clock.advance(20)
    check("core: animation paused at end", run() == core.STATUS_PAUSED and anim["stops"] == 1
          and not anim["playing"])

    # Both together: render -> solid AND animation stopped
    c = core.IdleController(clock=clock)
    anim["playing"] = True
    r1.shading.type = 'RENDERED'
    clock.advance(30)
    run()
    check("core: both actions", r1.shading.type == 'SOLID' and anim["stops"] == 2)

    # Pause Animation OFF: playback continues, viewport still goes to Solid
    c = core.IdleController(clock=clock)
    anim["playing"] = True
    r1.shading.type = 'RENDERED'
    clock.advance(30)
    check("core: anim off -> only solid", run(pause_anim=False) == core.STATUS_PAUSED
          and r1.shading.type == 'SOLID' and anim["playing"] and anim["stops"] == 2)
    clock.advance(5)
    check("core: stays paused until input", run(pause_anim=False) == core.STATUS_PAUSED)
    c.note_input()
    check("core: after input, still-playing anim counts again",
          run(pause_anim=False) == core.STATUS_COUNTDOWN)

    # Render -> Solid OFF: viewport keeps rendering, animation still stopped
    c = core.IdleController(clock=clock)
    anim["playing"] = True
    r1.shading.type = 'RENDERED'
    clock.advance(30)
    check("core: solid off -> only anim", run(solid=False) == core.STATUS_PAUSED
          and r1.shading.type == 'RENDERED' and anim["stops"] == 3)

    # Both OFF: reminder only (0:00)
    c = core.IdleController(clock=clock)
    anim["playing"] = True
    clock.advance(30)
    check("core: both off -> idle", run(solid=False, pause_anim=False) == core.STATUS_IDLE
          and r1.shading.type == 'RENDERED' and anim["playing"] and c.remaining == 0)
    anim["playing"] = False

    # Hold (timer pause button)
    c = core.IdleController(clock=clock)
    r1.shading.type = 'RENDERED'
    clock.advance(5)
    c.set_hold(True)
    clock.advance(500)
    check("core: hold freezes", run(hold=True) == core.STATUS_COUNTDOWN
          and abs(c.remaining - 25) < 1e-6 and r1.shading.type == 'RENDERED')
    c.note_input()
    run(hold=True)
    check("core: input while held -> full time", abs(c.remaining - 30) < 1e-6)
    c.set_hold(False)
    clock.advance(30)
    check("core: release continues", run() == core.STATUS_PAUSED)

    # Render job running: never act, idle reset
    c = core.IdleController(clock=clock)
    r1.shading.type = 'RENDERED'
    clock.advance(500)
    check("core: render job skip", run(render=True) == core.STATUS_RENDER_JOB
          and r1.shading.type == 'RENDERED')
    clock.advance(10)
    check("core: idle reset by render job", run() == core.STATUS_COUNTDOWN
          and abs(c.remaining - 20) < 1e-6)

    # Nothing running -> nothing happens
    r1.shading.type = 'SOLID'
    clock.advance(1000)
    check("core: nothing running", run() == core.STATUS_NO_RENDER and not c.acted)

    # OFF
    r1.shading.type = 'RENDERED'
    check("core: off", run(enabled=False) == core.STATUS_OFF and r1.shading.type == 'RENDERED')

    # Event filtering
    for et in ('TIMER', 'TIMER_REPORT', 'TIMERREGION', 'NONE', 'WINDOW_DEACTIVATE'):
        check("core: ignore " + et, not core.is_user_event(et))
    for et in ('MOUSEMOVE', 'LEFTMOUSE', 'A', 'WHEELUPMOUSE', 'TRACKPADPAN', 'NDOF_MOTION', 'SPACE'):
        check("core: user event " + et, core.is_user_event(et))
    check("core: format", core.format_seconds(125) == "2:05")



# --------------------------------------------------------------- add-on in Blender
class FakeLayout:
    def __init__(self, log):
        self.log = log
        self.active = True
        self.use_property_split = False
        self.use_property_decorate = False

    def row(self, **kw):
        return FakeLayout(self.log)

    column = row

    def label(self, text="", **kw):
        self.log.append(("label", text))

    def separator(self, **kw):
        pass

    def prop(self, data, prop, **kw):
        ok = prop in data.bl_rna.properties
        self.log.append(("prop", prop, ok))
        if not ok:
            raise AttributeError("missing property " + prop)

    def operator(self, idname, **kw):
        mod, name = idname.split(".")
        ok = hasattr(getattr(bpy.ops, mod), name) and hasattr(
            bpy.types, mod.upper() + "_OT_" + name)
        self.log.append(("operator", idname, ok, kw.get("icon")))
        if not ok:
            raise AttributeError("missing operator " + idname)

    def popover(self, panel, **kw):
        ok = hasattr(bpy.types, panel)
        self.log.append(("popover", panel, ok, kw.get("text")))
        if not ok:
            raise AttributeError("missing panel " + panel)


class FakeRegion:
    def __init__(self, alignment):
        self.alignment = alignment


class FakeContext:
    def __init__(self, alignment):
        self.region = FakeRegion(alignment)
        self.preferences = bpy.context.preferences


def real_spaces():
    out = []
    for screen in bpy.data.screens:
        for area in screen.areas:
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    out.append(space)
    return out


def test_addon():
    mod = addon_utils.enable("resource_safeguard", default_set=True, handle_error=None)
    check("addon: enabled", mod is not None)
    import resource_safeguard as rsg
    from resource_safeguard import core

    prefs = rsg.get_prefs()
    check("addon: prefs exist", prefs is not None)
    check("addon: timer registered", bpy.app.timers.is_registered(rsg.tick))
    check("addon: load_post handler", rsg._on_load_post in bpy.app.handlers.load_post)
    check("addon: render handlers", rsg._on_render_done in bpy.app.handlers.render_complete
          and rsg._on_render_done in bpy.app.handlers.render_cancel)
    draw_funcs = getattr(bpy.types.TOPBAR_HT_upper_bar.draw, "_draw_funcs", [])
    check("addon: topbar draw added", rsg.draw_topbar in draw_funcs)

    # Timeout presets
    prefs.timeout_preset = '120'
    check("addon: preset timeout", rsg.timeout_seconds(prefs) == 120)
    for key, secs in (('180', 180), ('240', 240)):
        prefs.timeout_preset = key
        check("addon: preset %s" % key, rsg.timeout_seconds(prefs) == secs)
    prefs.timeout_preset = 'CUSTOM'
    prefs.custom_seconds = 42
    check("addon: custom timeout", rsg.timeout_seconds(prefs) == 42)
    prefs.timeout_preset = '30'

    # Drive the real tick with real SpaceView3D objects and a fake clock
    spaces = real_spaces()
    check("addon: found 3D view spaces", len(spaces) >= 2, str(len(spaces)))
    for s in spaces:
        s.shading.type = 'SOLID'
    target = spaces[0]
    target.shading.type = 'RENDERED'

    clock = FakeClock()
    rsg._State.controller = core.IdleController(clock=clock)
    rsg.iter_visible_spaces = lambda: iter(spaces)
    render_flag = [False]
    rsg.is_render_running = lambda: render_flag[0]
    prefs.enabled = True

    clock.advance(10)
    rsg.tick()
    check("addon: countdown", rsg._State.controller.status == core.STATUS_COUNTDOWN,
          rsg._State.controller.status_text())
    render_flag[0] = True
    clock.advance(100)
    rsg.tick()
    check("addon: skipped during render job", target.shading.type == 'RENDERED')
    render_flag[0] = False
    rsg._on_render_done(None)  # handler resets idle
    clock.advance(29)
    rsg.tick()
    check("addon: render_complete resets idle", target.shading.type == 'RENDERED')
    clock.advance(2)
    rsg.tick()
    check("addon: paused real space", target.shading.type == 'SOLID')
    check("addon: others untouched", all(s.shading.type == 'SOLID' for s in spaces))
    check("addon: pause recorded", rsg._State.controller.acted)
    rsg.on_input()
    check("addon: input keeps it paused (always stay)", target.shading.type == 'SOLID')
    rsg.tick()
    check("addon: still paused after tick", rsg._State.controller.status == core.STATUS_PAUSED)
    check("addon: no on_return option", "on_return" not in prefs.bl_rna.properties)
    target.shading.type = 'RENDERED'  # user switches back
    rsg.tick()
    check("addon: manual switch back restarts countdown",
          rsg._State.controller.status == core.STATUS_COUNTDOWN)

    # Turning OFF forgets the pause
    prefs.enabled = False
    rsg.tick()
    check("addon: off status", rsg._State.controller.status == core.STATUS_OFF)
    prefs.enabled = True

    # Topbar draw with a fake layout: [timer] [dropdown]
    def draw_log(fn, alignment='RIGHT'):
        log = []
        header = type("H", (), {})()
        header.layout = FakeLayout(log)
        try:
            fn(header, FakeContext(alignment))
            return log, ""
        except Exception:
            return None, traceback.format_exc()

    for alignment, expect_draw in (('RIGHT', True), ('LEFT', False)):
        for enabled in (True, False):
            for show_timer in (True, False):
                for preset in ('60', 'CUSTOM'):
                    prefs.enabled = enabled
                    prefs.show_timer = show_timer
                    prefs.timeout_preset = preset
                    rsg.tick()  # a Rendered space exists -> countdown
                    log, err = draw_log(rsg.draw_topbar, alignment)
                    name = "draw %s on=%s timer=%s preset=%s" % (alignment, enabled, show_timer, preset)
                    check(name + " runs", log is not None, err)
                    if log is None:
                        continue
                    if not expect_draw:
                        check(name + " draws nothing", not log)
                        continue
                    pops = [e for e in log if e[0] == "popover"]
                    check(name + " one dropdown", len(pops) == 1 and pops[0][1] == "RSG_PT_idle_menu"
                          and pops[0][2], str(pops))
                    props = [e[1] for e in log if e[0] == "prop"]
                    check(name + " active toggle", props == ["enabled"], str(props))
                    ops = [e for e in log if e[0] == "operator"]
                    check(name + " pause button", len(ops) == 1
                          and ops[0][1] == "wm.rsg_toggle_timer_pause" and ops[0][2], str(ops))
                    check(name + " no loose labels", not any(e[0] == "label" for e in log))
                    order = [e[0] for e in log]
                    check(name + " order active|timer|pause",
                          order == ["prop", "popover", "operator"], str(order))
                    text = pops[0][3] if pops else None
                    if not enabled:
                        check(name + " timer says Off", text == "Off", repr(text))
                    elif show_timer:
                        check(name + " timer shows time", bool(text)
                              and all(ch.isdigit() or ch == ':' for ch in text), repr(text))
                    else:
                        check(name + " timer icon only", text == "", repr(text))
    prefs.enabled = True
    prefs.show_timer = True
    prefs.timeout_preset = '60'

    # Dropdown menu content
    for preset in ('60', 'CUSTOM'):
        prefs.timeout_preset = preset
        log, err = draw_log(bpy.types.RSG_PT_idle_menu.draw)
        check("menu %s draw runs" % preset, log is not None, err)
        if log is not None:
            props = [e[1] for e in log if e[0] == "prop"]
            check("menu %s items" % preset,
                  all(n in props for n in ("timeout_preset", "show_timer", "switch_to_solid", "pause_animation"))
                  and "enabled" not in props
                  and (("custom_seconds" in props) == (preset == 'CUSTOM')), str(props))
    prefs.timeout_preset = '60'

    # Preferences draw (layout is read-only; emulate with a proxy)
    log = []
    proxy = type("Proxy", (), {})()
    for attr in ("enabled", "timeout_preset", "custom_seconds", "show_timer", "switch_to_solid", "pause_animation", "bl_rna"):
        setattr(proxy, attr, getattr(prefs, attr))
    proxy.layout = FakeLayout(log)
    try:
        type(prefs).draw(proxy, bpy.context)
        check("preferences draw runs", True)
    except Exception:
        check("preferences draw runs", False, traceback.format_exc())

    # Timer pause button: freezes the countdown, nothing is switched
    for s_ in spaces:
        s_.shading.type = 'SOLID'
    target.shading.type = 'RENDERED'
    rsg._State.controller = core.IdleController(clock=clock)
    prefs.timeout_preset = '30'
    rsg._State.timer_held = False
    clock.advance(10)
    rsg.tick()
    bpy.ops.wm.rsg_toggle_timer_pause()
    check("pause button: held", rsg._State.timer_held)
    clock.advance(100)
    rsg.tick()
    check("pause button: no switch while held", target.shading.type == 'RENDERED')
    check("pause button: countdown frozen", abs(rsg._State.controller.remaining - 20) < 1e-6,
          str(rsg._State.controller.remaining))
    log, err = draw_log(rsg.draw_topbar)
    ops = [e for e in (log or []) if e[0] == "operator"]
    check("pause button: shows PLAY while held", ops and ops[0][3] == 'PLAY', str(ops) + err)
    bpy.ops.wm.rsg_toggle_timer_pause()
    check("pause button: continue", not rsg._State.timer_held)
    clock.advance(19)
    rsg.tick()
    check("pause button: continues from frozen time", target.shading.type == 'RENDERED'
          and abs(rsg._State.controller.remaining - 1) < 1e-6, str(rsg._State.controller.remaining))
    clock.advance(1)
    rsg.tick()
    check("pause button: switches after the rest", target.shading.type == 'SOLID')
    check("timer text after switch", rsg.timer_text(prefs) == "Paused", rsg.timer_text(prefs))
    for s_ in spaces:
        s_.shading.type = 'SOLID'
    rsg._State.controller = core.IdleController(clock=clock)
    rsg.tick()
    check("timer text no render = full time", rsg.timer_text(prefs) == "0:30", rsg.timer_text(prefs))
    prefs.timeout_preset = '60'

    # Render -> Solid OFF: timer runs out but the viewport keeps rendering
    for s in spaces:
        s.shading.type = 'SOLID'
    target.shading.type = 'RENDERED'
    rsg._State.controller = core.IdleController(clock=clock)
    prefs.timeout_preset = '30'
    prefs.switch_to_solid = False
    clock.advance(31)
    rsg.tick()
    check("switch off: stays rendered", target.shading.type == 'RENDERED')
    check("switch off: idle status", rsg._State.controller.status == core.STATUS_IDLE)
    log, err = draw_log(rsg.draw_topbar)
    check("switch off: timer shows 0:00", log is not None and any(e[0] == "popover" and e[3] == "0:00" for e in log), str(log) + err)
    prefs.switch_to_solid = True  # turning it back on resets the idle clock
    clock.advance(31)
    rsg.tick()
    check("switch on: pauses again", target.shading.type == 'SOLID')
    prefs.timeout_preset = '60'

    # Pause Animation through the add-on tick (playback state faked)
    for s_ in spaces:
        s_.shading.type = 'SOLID'
    play = {"on": True, "stops": 0}
    orig_play, orig_stop = rsg.is_animation_playing, rsg.stop_animation
    rsg.is_animation_playing = lambda: play["on"]
    def fake_stop():
        play["stops"] += 1
        play["on"] = False
    rsg.stop_animation = fake_stop
    try:
        rsg._State.controller = core.IdleController(clock=clock)
        prefs.timeout_preset = '30'
        prefs.pause_animation = True
        clock.advance(10)
        rsg.tick()
        check("addon: animation counts down", rsg._State.controller.status == core.STATUS_COUNTDOWN)
        clock.advance(20)
        rsg.tick()
        check("addon: animation stopped at end", play["stops"] == 1 and not play["on"])
        check("addon: timer says Paused", rsg.timer_text(prefs) == "Paused")
        prefs.pause_animation = False
        play["on"] = True
        rsg._State.controller = core.IdleController(clock=clock)
        clock.advance(31)
        rsg.tick()
        check("addon: pause animation off keeps playing", play["on"] and play["stops"] == 1)
        prefs.pause_animation = True
    finally:
        rsg.is_animation_playing, rsg.stop_animation = orig_play, orig_stop
    check("addon: real is_animation_playing headless", rsg.is_animation_playing() in (True, False))
    prefs.timeout_preset = '60'

    # Top bar area captured from draw context is used for redraw
    class FakeArea:
        n = 0
        def tag_redraw(self):
            FakeArea.n += 1
    class FakeWin:
        screen = None
        def as_pointer(self):
            return 4242
    ctx = FakeContext('RIGHT')
    ctx.window, ctx.area = FakeWin(), FakeArea()
    header = type("H", (), {})()
    header.layout = FakeLayout([])
    rsg.draw_topbar(header, ctx)
    check("topbar area remembered", rsg._State.topbar_areas.get(4242) is ctx.area)
    orig_windows = rsg._windows
    rsg._windows = lambda: [FakeWin()]
    try:
        rsg.redraw_topbars()
    finally:
        rsg._windows = orig_windows
    check("topbar area redrawn", FakeArea.n == 1)
    rsg.redraw_topbars()  # window gone -> pruned
    check("closed window pruned", 4242 not in rsg._State.topbar_areas)

    # Watcher helpers do not crash without windows (headless)
    try:
        rsg.ensure_watchers()
        check("addon: ensure_watchers headless", True)
    except Exception:
        check("addon: ensure_watchers headless", False, traceback.format_exc())

    # Clean unregister / re-enable cycle
    for cycle in range(2):
        addon_utils.disable("resource_safeguard", default_set=True, handle_error=None)
        check("unregister %d: timer removed" % cycle, not bpy.app.timers.is_registered(rsg.tick))
        check("unregister %d: handlers removed" % cycle,
              rsg._on_load_post not in bpy.app.handlers.load_post
              and rsg._on_render_done not in bpy.app.handlers.render_complete
              and rsg._on_render_done not in bpy.app.handlers.render_cancel)
        draw_funcs = getattr(bpy.types.TOPBAR_HT_upper_bar.draw, "_draw_funcs", [])
        check("unregister %d: topbar draw removed" % cycle, rsg.draw_topbar not in draw_funcs)
        check("unregister %d: classes removed" % cycle,
              not hasattr(bpy.types, "WM_OT_rsg_input_watcher")
              and not hasattr(bpy.types, "RSG_PT_idle_menu")
              and not hasattr(bpy.types, "WM_OT_rsg_toggle_timer_pause"))
        check("unregister %d: shutdown flag" % cycle, rsg._State.shutdown)
        mod = addon_utils.enable("resource_safeguard", default_set=True, handle_error=None)
        import resource_safeguard as rsg  # module may be reloaded
        check("re-enable %d: timer back" % cycle, bpy.app.timers.is_registered(rsg.tick))
        draw_funcs = getattr(bpy.types.TOPBAR_HT_upper_bar.draw, "_draw_funcs", [])
        check("re-enable %d: single topbar draw" % cycle,
              sum(1 for f in draw_funcs if getattr(f, "__name__", "") == "draw_topbar") == 1)
    addon_utils.disable("resource_safeguard", default_set=True, handle_error=None)


def main():
    try:
        test_core()
    except Exception:
        check("core tests crashed", False, traceback.format_exc())
    try:
        test_addon()
    except Exception:
        check("addon tests crashed", False, traceback.format_exc())
    failed = [r for r in RESULTS if not r[1]]
    print("\n%d checks, %d failed" % (len(RESULTS), len(failed)))
    for name, _, detail in failed:
        print("FAILED:", name, detail)
    sys.stdout.flush()
    os._exit(1 if failed else 0)


main()
