# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine-agnostic idle logic for Resource Safeguard.

This module does not import bpy, so it can be tested with a fake clock and
fake viewport spaces. Anything with ``.shading.type`` counts as a "space".
__init__.py calls IdleController.tick() once per second and note_input() on
every real user input.
"""

import math
import time

RENDERED = 'RENDERED'
SOLID = 'SOLID'

# Event types that are not user input and must never reset the idle timer.
NON_USER_EVENTS = frozenset({
    'NONE',
    'TIMER', 'TIMER0', 'TIMER1', 'TIMER2',
    'TIMER_JOBS', 'TIMER_AUTOSAVE', 'TIMER_REPORT', 'TIMERREGION',
    'WINDOW_DEACTIVATE',
    'ACTIONZONE_AREA', 'ACTIONZONE_REGION', 'ACTIONZONE_FULLSCREEN',
    'XR_ACTION',
})

MOUSE_MOVE_EVENTS = frozenset({'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'})

# Status codes used by the top bar label.
STATUS_OFF = 'OFF'
STATUS_NO_RENDER = 'NO_RENDER'
STATUS_COUNTDOWN = 'COUNTDOWN'
STATUS_PAUSED = 'PAUSED'
STATUS_RENDER_JOB = 'RENDER_JOB'
STATUS_IDLE = 'IDLE'          # time is up but no action applied (reminder only)


def is_user_event(event_type):
    """True for real input (keys, mouse, trackpad, NDOF), False for timers etc."""
    return event_type not in NON_USER_EVENTS


def format_seconds(seconds):
    """Format seconds as m:ss (e.g. 125 -> "2:05")."""
    seconds = max(0, int(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


class IdleController:
    """Keeps the idle clock and runs the end-of-timer actions.

    Actions (each can be turned off):
      * Render -> Solid: visible Rendered viewports are switched to Solid.
      * Pause animation: animation playback is stopped.
    Nothing is switched back automatically; after an action the status stays
    PAUSED until the user is back (input) and something runs again.
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.last_input = clock()
        self.acted = False       # an end-of-timer action happened
        self.acted_at = 0.0
        self.status = STATUS_OFF
        self.remaining = 0.0
        self._held_idle = None   # idle time frozen by the timer pause button

    # ------------------------------------------------------------------ input
    def reset(self):
        """Restart the idle clock (render finished, setting changed, ...)."""
        self.last_input = self.clock()

    def forget(self):
        self.acted = False

    def note_input(self):
        """Called on every real user input."""
        self.last_input = self.clock()
        if self._held_idle is not None:
            self._held_idle = 0.0  # input restarts a frozen timer at full time

    def set_hold(self, hold):
        """Freeze (or release) the countdown at the current idle time."""
        if hold:
            self._held_idle = self.clock() - self.last_input
        else:
            if self._held_idle is not None:
                self.last_input = self.clock() - self._held_idle
            self._held_idle = None

    # ---------------------------------------------------------------- actions
    def pause(self, rendered_spaces):
        """Switch the given Rendered spaces to Solid. Returns how many changed."""
        count = 0
        for space in rendered_spaces:
            if space.shading.type == RENDERED:
                space.shading.type = SOLID
                count += 1
        return count

    # ------------------------------------------------------------------- tick
    def tick(self, enabled, timeout, visible_spaces, render_running=False,
             switch_to_solid=True, hold=False, animation_playing=False,
             pause_animation=False, stop_animation=None):
        """Run once per second. Returns the new status code.

        The countdown runs while a visible viewport is Rendered or an animation
        is playing. hold=True freezes it (the timer pause button).
        """
        now = self.clock()

        if not enabled:
            self.forget()
            self._held_idle = None
            self.status = STATUS_OFF
            return self.status

        if hold:
            if self._held_idle is None:
                self.set_hold(True)
            self.last_input = now - self._held_idle
        else:
            self._held_idle = None

        if render_running:
            # Never touch anything during F12 / animation renders.
            self.last_input = now
            self.status = STATUS_RENDER_JOB
            return self.status

        rendered = [s for s in visible_spaces() if s.shading.type == RENDERED]
        running = bool(rendered) or animation_playing

        if self.acted:
            # Stay "paused" until the user is back and something runs again.
            if self.last_input >= self.acted_at and running:
                self.forget()
            else:
                self.status = STATUS_PAUSED
                return self.status

        if not running:
            self.status = STATUS_NO_RENDER
            return self.status

        idle = now - self.last_input
        if idle < timeout:
            self.remaining = timeout - idle
            self.status = STATUS_COUNTDOWN
            return self.status

        did = 0
        if switch_to_solid and rendered:
            did += self.pause(rendered)
        if pause_animation and animation_playing and stop_animation is not None:
            stop_animation()
            did += 1
        if did:
            self.acted = True
            self.acted_at = now
            self.status = STATUS_PAUSED
        else:
            # Time is up but both actions are off (or do not apply): reminder only.
            self.remaining = 0.0
            self.status = STATUS_IDLE
        return self.status

    def status_text(self):
        """Short description of the status (logs, and change detection in tick)."""
        if self.status == STATUS_OFF:
            return "Idle pause off"
        if self.status == STATUS_PAUSED:
            return "Paused (idle)"
        if self.status == STATUS_NO_RENDER:
            return "Idle pause: nothing running"
        if self.status == STATUS_IDLE:
            return "Idle (time is up)"
        if self.status == STATUS_RENDER_JOB:
            return "Idle pause: rendering"
        return "Idle pause in " + format_seconds(math.ceil(self.remaining))
