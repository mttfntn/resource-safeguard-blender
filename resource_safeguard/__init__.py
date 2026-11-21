# SPDX-License-Identifier: GPL-3.0-or-later
"""Resource Safeguard: free the GPU when Blender is idle.

A countdown runs while a visible 3D viewport is in Rendered shading or an
animation is playing. When nobody touches Blender for the chosen time, it can
stop the animation playback and switch Rendered viewports to Solid. Nothing is
switched back automatically. Works with any render engine (Octane, Cycles,
EEVEE, ...) because it only changes SpaceView3D.shading.type and stops playback.

How the pieces fit together:
  * WM_OT_rsg_input_watcher: one modal operator per window. It returns
    PASS_THROUGH for every event and only records the time of real user input.
  * tick(): a bpy.app.timers callback, about once per second. It keeps one
    watcher per window, feeds the current state to core.IdleController and
    redraws the top bar.
  * core.IdleController (core.py, no bpy): the idle clock and the decision of
    when to act. It is tested with a fake clock.
  * draw_topbar() + RSG_PT_idle_menu: the [power][timer v][pause] section on
    the right of the top bar and the dropdown menu with the options.
  * RSG_AddonPreferences: the saved settings.
"""

bl_info = {
    "name": "Resource Safeguard",
    "author": "Matteo Fontana",
    "version": (2, 0, 0),
    "blender": (5, 3, 0),
    "location": "Top bar (right side) / Preferences > Add-ons",
    "description": "Pause animation and switch Rendered viewports to Solid after an idle time",
    "category": "3D View",
}

import itertools
import math

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, IntProperty

from . import core

ADDON_ID = __name__
WATCHER_IDNAME = "wm.rsg_input_watcher"
WATCHER_IDNAMES = {WATCHER_IDNAME, "WM_OT_rsg_input_watcher"}
TICK_INTERVAL = 1.0

TIMEOUT_ITEMS = (
    ('15', "15 s", "Pause after 15 seconds of inactivity"),
    ('30', "30 s", "Pause after 30 seconds of inactivity"),
    ('60', "1 min", "Pause after 1 minute of inactivity"),
    ('120', "2 min", "Pause after 2 minutes of inactivity"),
    ('180', "3 min", "Pause after 3 minutes of inactivity"),
    ('240', "4 min", "Pause after 4 minutes of inactivity"),
    ('300', "5 min", "Pause after 5 minutes of inactivity"),
    ('600', "10 min", "Pause after 10 minutes of inactivity"),
    ('CUSTOM', "Custom", "Use a custom number of seconds"),
)

class _State:
    # Runtime state for this Blender session (nothing here is saved).
    controller = core.IdleController()
    watchers = {}            # window pointer -> watcher token
    token_counter = itertools.count(1)
    shutdown = False
    timer_held = False       # timer pause button (session only)
    topbar_areas = {}        # window pointer -> top bar Area (global area)
    last_status_text = ""


# ---------------------------------------------------------------- helpers
def get_prefs(context=None):
    """Return this add-on's AddonPreferences, or None while it is not enabled."""
    ctx = context if context is not None else bpy.context
    addon = ctx.preferences.addons.get(ADDON_ID)
    return addon.preferences if addon is not None else None


def timeout_seconds(prefs):
    """Idle time in seconds from the preset (or the Custom field)."""
    if prefs.timeout_preset == 'CUSTOM':
        return max(1, prefs.custom_seconds)
    return int(prefs.timeout_preset)


def _windows():
    """All open Blender windows (empty when there is no window manager)."""
    wm = bpy.context.window_manager
    return list(wm.windows) if wm is not None else []


def iter_visible_spaces():
    """3D viewports of the screens shown in Blender windows (the ones that render)."""
    for window in _windows():
        screen = window.screen
        if screen is None:
            continue
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    yield space


def is_render_running():
    """True while an F12 / animation render job runs (the add-on then does nothing)."""
    try:
        return bpy.app.is_job_running('RENDER')
    except Exception:
        return False


def is_animation_playing():
    """True while animation playback runs in any window."""
    for window in _windows():
        screen = window.screen
        if screen is not None and screen.is_animation_playing:
            return True
    return False


def stop_animation():
    """Stop animation playback at the current frame (like pressing Space)."""
    for window in _windows():
        screen = window.screen
        if screen is None or not screen.is_animation_playing:
            continue
        try:
            with bpy.context.temp_override(window=window, screen=screen):
                bpy.ops.screen.animation_cancel(restore_frame=False)
        except Exception as ex:
            print("Resource Safeguard: could not stop animation:", ex)
        return


def redraw_topbars():
    """Tag the top bar of every window for redraw.

    In recent Blender versions the top bar is a *global* area that is not in
    window.screen.areas, so the area is captured in the draw callback
    (context.area) and remembered per window.
    """
    windows = _windows()
    live = {w.as_pointer() for w in windows}
    for ptr in list(_State.topbar_areas):
        if ptr not in live:
            del _State.topbar_areas[ptr]
    for ptr, area in list(_State.topbar_areas.items()):
        try:
            area.tag_redraw()
        except Exception:
            _State.topbar_areas.pop(ptr, None)


# ---------------------------------------------------------------- input watcher
# One per window. Every event passes through; real user input (not timers or
# window events, not mouse moves that do not move) restarts the idle clock.
# A token lets a newer watcher replace an older one in the same window.
class WM_OT_rsg_input_watcher(bpy.types.Operator):
    bl_idname = WATCHER_IDNAME
    bl_label = "Resource Safeguard Input Watcher"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        window = context.window
        if window is None or _State.shutdown:
            return {'CANCELLED'}
        self._win_ptr = window.as_pointer()
        self._token = next(_State.token_counter)
        self._last_xy = None
        _State.watchers[self._win_ptr] = self._token
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if _State.shutdown or _State.watchers.get(self._win_ptr) != self._token:
            return {'CANCELLED'}
        etype = event.type
        if not core.is_user_event(etype):
            return {'PASS_THROUGH'}
        if etype in core.MOUSE_MOVE_EVENTS:
            # Ignore synthetic mouse-move events that do not actually move.
            xy = (event.mouse_x, event.mouse_y)
            if xy == self._last_xy:
                return {'PASS_THROUGH'}
            self._last_xy = xy
        on_input()
        return {'PASS_THROUGH'}

    def cancel(self, context):
        if _State.watchers.get(getattr(self, "_win_ptr", None)) == getattr(self, "_token", None):
            del _State.watchers[self._win_ptr]


def on_input():
    """Real user input in any window: restart the idle clock.

    Nothing is switched back here; the user resumes rendering/playback.
    """
    _State.controller.note_input()


def _watcher_alive(window):
    """True if this window already runs our input watcher (modal operator)."""
    for op in window.modal_operators:
        if op is not None and op.bl_idname in WATCHER_IDNAMES:
            return True
    return False


def ensure_watchers():
    """Start one watcher per window; forget windows that were closed."""
    if _State.shutdown or bpy.app.background:
        return  # no real windows / events in background mode
    windows = _windows()
    live = {w.as_pointer() for w in windows}
    for ptr in list(_State.watchers):
        if ptr not in live:
            del _State.watchers[ptr]
    for window in windows:
        if _watcher_alive(window):
            continue
        # A stale entry (handlers freed on file load) would block the new
        # watcher; drop it so the old one, if somehow alive, cancels itself.
        _State.watchers.pop(window.as_pointer(), None)
        try:
            with bpy.context.temp_override(window=window, screen=window.screen):
                bpy.ops.wm.rsg_input_watcher('INVOKE_DEFAULT')
        except Exception as ex:  # never break the timer
            print("Resource Safeguard: could not start input watcher:", ex)


# ---------------------------------------------------------------- timer
def tick():
    """Timer callback, about once per second.

    Starts missing watchers, runs one IdleController step with the current
    settings and Blender state, and redraws the top bar while the timer is
    counting (or when the state changed). Returns the next interval.
    """
    if _State.shutdown:
        return None
    try:
        ensure_watchers()
        prefs = get_prefs()
        if prefs is None:
            return TICK_INTERVAL
        ctrl = _State.controller
        ctrl.tick(
            enabled=prefs.enabled,
            timeout=timeout_seconds(prefs),
            visible_spaces=iter_visible_spaces,
            render_running=is_render_running(),
            switch_to_solid=prefs.switch_to_solid,
            hold=_State.timer_held,
            animation_playing=is_animation_playing(),
            pause_animation=prefs.pause_animation,
            stop_animation=stop_animation,
        )
        text = ctrl.status_text()
        # Redraw the top bar about once per second while the timer is shown
        # and counting, plus once whenever the state changes.
        counting = prefs.enabled and prefs.show_timer and ctrl.status == core.STATUS_COUNTDOWN
        if counting or text != _State.last_status_text:
            redraw_topbars()
        _State.last_status_text = text
    except Exception as ex:
        print("Resource Safeguard: tick error:", ex)
    return TICK_INTERVAL


# ---------------------------------------------------------------- handlers
@persistent
def _on_load_pre(*_args):
    """Before a file load: forget top bar areas, they may be freed by the load."""
    _State.topbar_areas.clear()


@persistent
def _on_load_post(*_args):
    """After a file load: windows and their modal handlers may be new.

    Forget the watchers (the next tick starts new ones) and restart the clock.
    """
    _State.watchers.clear()
    _State.topbar_areas.clear()
    _State.controller.forget()
    _State.controller.reset()
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=0.1, persistent=True)


@persistent
def _on_render_done(*_args):
    """A final render finished or was cancelled: restart the idle clock."""
    _State.controller.reset()


_HANDLERS = (
    (bpy.app.handlers.load_pre, _on_load_pre),
    (bpy.app.handlers.load_post, _on_load_post),
    (bpy.app.handlers.render_complete, _on_render_done),
    (bpy.app.handlers.render_cancel, _on_render_done),
)


# ---------------------------------------------------------------- preferences
def _on_settings_changed(self, context):
    """Any setting changed: restart the clock; turning off clears the paused state."""
    _State.controller.reset()
    if not self.enabled:
        _State.controller.forget()
    try:
        redraw_topbars()
    except Exception:
        pass


# Saved settings (Preferences > Add-ons). Kept across files and restarts once
# the Preferences are saved.
class RSG_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    enabled: BoolProperty(
        name="Active",
        description="Active: the idle timer runs and the end-of-timer actions happen. "
                    "Off: no timer at all",
        default=True,
        update=_on_settings_changed,
    )
    show_timer: BoolProperty(
        name="Show Timer",
        description="Show the idle countdown in the top bar",
        default=True,
        update=_on_settings_changed,
    )
    switch_to_solid: BoolProperty(
        name="Render \u2192 Solid",
        description="When the timer ends, switch Rendered viewports to Solid. "
                    "Off: the viewports keep rendering",
        default=True,
        update=_on_settings_changed,
    )
    pause_animation: BoolProperty(
        name="Pause Animation",
        description="When the timer ends, stop the animation playback (at the current frame). "
                    "Off: the animation keeps playing",
        default=True,
        update=_on_settings_changed,
    )
    timeout_preset: EnumProperty(
        name="Idle Time",
        description="Idle time before the animation is paused and/or Rendered viewports "
                    "are switched to Solid",
        items=TIMEOUT_ITEMS,
        default='60',
        update=_on_settings_changed,
    )
    custom_seconds: IntProperty(
        name="Seconds",
        description="Custom idle time in seconds",
        default=90, min=1, soft_max=3600,
        update=_on_settings_changed,
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        col = layout.column()
        col.prop(self, "timeout_preset")
        if self.timeout_preset == 'CUSTOM':
            col.prop(self, "custom_seconds")
        col.prop(self, "enabled")
        col.prop(self, "show_timer")
        col.label(text="At the end of the timer:")
        col.prop(self, "pause_animation")
        col.prop(self, "switch_to_solid")
        col.label(text="Settings are saved with your Preferences (auto-save or Save Preferences).",
                  icon='INFO')


# The pause button in the top bar. Its docstring is the button's tooltip.
class WM_OT_rsg_toggle_timer_pause(bpy.types.Operator):
    """Pause or continue the idle timer. While paused, nothing is paused or switched"""
    bl_idname = "wm.rsg_toggle_timer_pause"
    bl_label = "Pause Idle Timer"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        _State.timer_held = not _State.timer_held
        _State.controller.set_hold(_State.timer_held)
        redraw_topbars()
        return {'FINISHED'}


# The dropdown menu opened from the timer button (idle time and options).
# No docstring: Blender would show it as the tooltip.
class RSG_PT_idle_menu(bpy.types.Panel):
    bl_label = "Resource Safeguard"
    bl_space_type = 'TOPBAR'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 11

    def draw(self, context):
        prefs = get_prefs(context)
        if prefs is None:
            return
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        row = layout.row(align=True)
        row.label(text="Idle time:")
        row.prop(prefs, "timeout_preset", text="")
        if prefs.timeout_preset == 'CUSTOM':
            layout.prop(prefs, "custom_seconds")
        layout.prop(prefs, "show_timer")
        layout.separator()
        layout.label(text="At the end of the timer:")
        layout.prop(prefs, "pause_animation")
        layout.prop(prefs, "switch_to_solid")


def draw_topbar(self, context):
    """Draw [power][timer v][pause] in the right part of the top bar.

    Prepended to TOPBAR_HT_upper_bar. It also remembers each window's top bar
    area, because in Blender 5.3 the top bar is a global area that is not in
    window.screen.areas and redraw_topbars() needs it.
    """
    region = context.region
    if region is not None and region.alignment != 'RIGHT':
        return  # only in the right part of the top bar
    prefs = get_prefs(context)
    if prefs is None:
        return
    # Remember this window's top bar so the timer can redraw it.
    window = getattr(context, "window", None)
    area = getattr(context, "area", None)
    if window is not None and area is not None:
        _State.topbar_areas[window.as_pointer()] = area

    # One section, like the other top bar widgets:
    #   [Power] [ (clock) 0:42 v ] [Pause]
    # The timer is the dropdown button; the idle time is chosen inside it.
    layout = self.layout
    row = layout.row(align=True)
    # Power button, joined to the rest of the section (blue when active).
    row.prop(prefs, "enabled", text="", icon='QUIT', toggle=True)

    timer = row.row(align=True)
    timer.active = prefs.enabled
    text = timer_text(prefs)
    if text:
        timer.ui_units_x = 4.0  # fixed width: the bar does not jump while counting
    timer.popover(panel="RSG_PT_idle_menu", text=text, icon='TIME')

    held = _State.timer_held
    pause = row.row(align=True)
    pause.enabled = prefs.enabled
    pause.operator("wm.rsg_toggle_timer_pause", text="",
                   icon='PLAY' if held else 'PAUSE', depress=held)
    layout.separator()


def timer_text(prefs):
    """Text of the timer button in the top bar."""
    if not prefs.enabled:
        return "Off"
    if not prefs.show_timer:
        return ""
    ctrl = _State.controller
    if ctrl.status == core.STATUS_COUNTDOWN:
        return core.format_seconds(math.ceil(ctrl.remaining))
    if ctrl.status == core.STATUS_IDLE:
        return core.format_seconds(0)
    if ctrl.status == core.STATUS_PAUSED:
        return "Paused"
    # No Rendered viewport (or a final render is running): show the full time.
    return core.format_seconds(timeout_seconds(prefs))


# ---------------------------------------------------------------- register
_classes = (
    RSG_AddonPreferences,
    RSG_PT_idle_menu,
    WM_OT_rsg_toggle_timer_pause,
    WM_OT_rsg_input_watcher,
)


def register():
    """Register classes, the top bar section, the handlers and the timer."""
    _State.shutdown = False
    _State.watchers.clear()
    _State.topbar_areas.clear()
    _State.timer_held = False
    _State.controller = core.IdleController()
    _State.last_status_text = ""
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_HT_upper_bar.prepend(draw_topbar)
    for handler_list, fn in _HANDLERS:
        if fn not in handler_list:
            handler_list.append(fn)
    if not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick, first_interval=0.1, persistent=True)


def unregister():
    """Undo register(); also stops the input watchers (their class is removed)."""
    _State.shutdown = True
    if bpy.app.timers.is_registered(tick):
        bpy.app.timers.unregister(tick)
    for handler_list, fn in _HANDLERS:
        while fn in handler_list:
            handler_list.remove(fn)
    try:
        bpy.types.TOPBAR_HT_upper_bar.remove(draw_topbar)
    except Exception:
        pass
    # Unregistering the operator class also frees its running modal handlers.
    for cls in reversed(_classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            pass
    _State.watchers.clear()
    _State.controller.forget()
    try:
        redraw_topbars()
    except Exception:
        pass
    _State.topbar_areas.clear()
