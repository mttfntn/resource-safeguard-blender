# Resource Safeguard

[![Blender](https://img.shields.io/badge/Blender-5.3-orange?logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/badge/release-v1.0.0-blue)](https://github.com/mttfntn/resource-safeguard-blender/releases)
[![tests](https://github.com/mttfntn/resource-safeguard-blender/actions/workflows/ci.yml/badge.svg)](https://github.com/mttfntn/resource-safeguard-blender/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE)
[![Python](https://img.shields.io/badge/language-Python-3776AB?logo=python&logoColor=white)](resource_safeguard/)

A Blender 5.3 add-on that frees your GPU when you leave Blender alone. A
viewport in **Rendered** shading or a playing animation keeps the GPU busy even
when you are away or in another app. Resource Safeguard runs a countdown, like
KeyShot's "pause real-time render". When it ends, it can **pause the
animation** and switch Rendered viewports to **Solid**. Nothing is switched back
automatically; you continue yourself when you need it.

It works with any render engine (Octane, Cycles, EEVEE, Workbench...) because
it only changes the viewport shading type and stops playback. It uses no
engine-specific API.

For maintainers: [HANDOVER.md](HANDOVER.md) (people) and [AGENTS.md](AGENTS.md)
(AI assistants).

## Top bar

One joined section on the right side of the top bar (every workspace), next to
the Scene selector:

`[⏻] [🕒 0:42 ▾] [⏸]`

- **⏻ Power** (left): turns the timer on (blue) or off. When off, the section
  greys out and shows `Off`.
- **🕒 Timer** (middle): the countdown. It shows the full idle time while nothing
  runs, `Paused` after an action, and `0:00` when the time is up but both actions
  are off. Click it to open the menu.
- **⏸ Pause** (right): freezes the timer, so nothing happens while you need the
  render. It turns into a blue ▶ while paused; click it again to continue.
  It resets to "running" when Blender restarts.
- **Menu** (from the timer):
  - **Idle time**: 15 s, 30 s, 1 min, 2 min, 3 min, 4 min, 5 min, 10 min,
    or Custom (shows a seconds field).
  - **Show Timer**: show or hide the numbers (the clock icon stays).
  - **At the end of the timer**:
    - **Pause Animation**: on = stop playback; off = keep playing.
    - **Render → Solid**: on = switch Rendered viewports to Solid; off = keep rendering.

## How it works

- One small watcher per Blender window records the time of your last input
  (mouse move, click, key, scroll, trackpad). Timer and window events are ignored.
  Time spent in other apps counts as idle.
- One timer runs about once per second. The countdown runs while a visible
  viewport is in Rendered mode or an animation is playing.
- At the end of the timer, the actions that are on run: playback stops at the
  current frame, and every visible Rendered viewport switches to Solid.
- After that the timer shows `Paused` until you are back and something runs
  again (a Rendered viewport or playback); then the countdown starts over.
- It never acts during F12 or animation renders, and the idle clock restarts
  when a render finishes or is cancelled.
- If nothing is rendering or playing, it does nothing.

## Install

Requires **Blender 5.3**.

1. Download `resource_safeguard-<version>.zip` from the
   [latest release](https://github.com/mttfntn/resource-safeguard-blender/releases/latest).
2. In Blender: Edit > Preferences > Get Extensions > ▾ (top right) >
   **Install from Disk...**, pick the zip. It is enabled right away.

### Upgrading from Idle Render Pause 1.0.0

Until version 1.0.0 this add-on was called **Idle Render Pause**. Version 2.0.0
is the same add-on under its new name, but Blender sees it as a different
extension, so it does not replace the old one:

1. Uninstall *Idle Render Pause* first (Preferences > Get Extensions, ▾ >
   **Uninstall**). Also remove any older copy in
   `scripts\addons\idle_render_pause`. Only one copy should be loaded, or you
   get two top bar sections.
2. Install Resource Safeguard as above.
3. Your old settings are not carried over: set the idle time and options again
   from the timer menu.

## Settings

The power button and all menu options are add-on preferences. They apply to
every file and are kept after a restart once your Preferences are saved
(Auto-save Preferences does this; otherwise use *Save Preferences*). You can
also change them under Preferences > Add-ons > Resource Safeguard.

## Uninstall

Preferences > Get Extensions (or Add-ons), find Resource Safeguard, ▾ >
**Uninstall**. Disabling removes the timer, handlers, top bar section and input
watchers.

## Known limits

- While another modal tool keeps the input to itself (for example a very long
  sculpt stroke or grab), the watcher may not see your input. Keep the idle time
  longer than any single stroke.
- Only viewports in screens shown in a window are switched. Those are the only
  ones that render.
- Clicking the pause button is itself input, so a paused timer holds the full
  idle time.

## Development

See [HANDOVER.md](HANDOVER.md) for the code layout, tests and releases.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). © 2026 Matteo Fontana.
