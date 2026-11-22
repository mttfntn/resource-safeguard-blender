# AGENTS.md: Resource Safeguard

Blender 5.3 extension. A countdown runs while a visible viewport is Rendered or
an animation plays. At the end it stops playback and/or sets Rendered → Solid.
It never restores. There is no engine API. Humans: see HANDOVER.md.

## Commands (repo root, Windows; Linux: `blender`)

```
B="C:/Program Files/Blender Foundation/Blender 5.3/blender.exe"
"$B" -b --factory-startup --python-exit-code 1 --python tests/test_resource_safeguard.py   # 174 checks, must end "0 failed"
"$B" --factory-startup --enable-event-simulate --python tests/check_windowed.py          # opens a window ~10 s
"$B" --factory-startup --enable-event-simulate --python tests/check_animation_pause.py
"$B" --factory-startup --enable-event-simulate --python tests/check_topbar_redraw.py
python tools/build_package.py --blender "$B"                                              # -> dist/resource_safeguard-<ver>.zip
# scratch-profile install check:
export BLENDER_USER_RESOURCES=<tmp>/p BLENDER_USER_CONFIG=<tmp>/p/config BLENDER_USER_SCRIPTS=<tmp>/p/scripts BLENDER_USER_EXTENSIONS=<tmp>/p/extensions
"$B" -b --command extension install-file --repo user_default --enable dist/resource_safeguard-*.zip
"$B" -b --python-exit-code 1 --python tests/check_installed_package.py
```

## Architecture

- `resource_safeguard/core.py`: `IdleController` (no bpy).
  - `tick(enabled, timeout, visible_spaces, render_running, switch_to_solid, hold, animation_playing, pause_animation, stop_animation)`
    returns one of the statuses OFF, RENDER_JOB, PAUSED, NO_RENDER, COUNTDOWN or IDLE.
  - Also `note_input()`, `set_hold()`, `reset()`, `forget()`.
- `resource_safeguard/__init__.py`:
  - `WM_OT_rsg_input_watcher`: modal, one per window, PASS_THROUGH. It calls `on_input()` on real input.
  - `tick()`: a `bpy.app.timers` callback every 1 s. It runs `ensure_watchers()`, then `controller.tick(...)`, then `redraw_topbars()`.
  - `draw_topbar`: prepended to `TOPBAR_HT_upper_bar`, RIGHT region only. It draws `[prop enabled QUIT][popover RSG_PT_idle_menu text=timer_text()][op wm.rsg_toggle_timer_pause]`.
  - `RSG_AddonPreferences` holds `enabled`, `show_timer`, `pause_animation`, `switch_to_solid`, `timeout_preset`, `custom_seconds`.
  - Handlers: `load_pre` / `load_post` (forget windows and areas), `render_complete` / `render_cancel` (reset the clock).
- Data flow: an event goes to the watcher, then `note_input` updates `last_input`. The timer then runs `controller.tick` and acts on the spaces or playback. `controller.status`/`remaining` then feed `timer_text()`, and the top bar draw shows it.

## Rules

- Never run anything in the user's open Blender. Always use `--factory-startup` and a scratch `BLENDER_USER_*` profile.
  `blender --command` without these loads the real add-ons.
- Windowed checks need `--enable-event-simulate`; otherwise the user's mouse resets the timer and the checks fail at random.
- Keep `bl_info["version"]` == manifest `version`. CI refuses a tag that does not match the manifest.
- Supported: Blender 5.3 only (manifest min 5.3.0, max 5.4.0). CI downloads exactly `BLENDER_VERSION` in `ci.yml`.
- Operator and panel docstrings become tooltips. Use `#` comments for internal notes there.
  `WM_OT_rsg_toggle_timer_pause`'s docstring is intentionally the button tooltip.
- Put new logic in `core.py` and test it with the fake clock in `tests/test_resource_safeguard.py`.

## Pitfalls found in this project

- In 5.3 the top bar is a global area, not in `screen.areas`. Redraws must use the area captured in `draw_topbar` (`_State.topbar_areas`).
- `TOPBAR_HT_upper_bar` draws twice, once per region. Append/prepend functions must check `context.region.alignment == 'RIGHT'`.
- The installed extension module has no `bl_info`.
- After unregister, `window.modal_operators` may hold a `None` entry until the next event. This is harmless.
- The pause button click is itself input, so hold freezes at the full time. `set_hold()` captures the idle time at click time, not at the next tick.
- CI stores no artifacts: the account-wide artifact storage quota was full (first CI run failed on upload-artifact). The release is published from the test job itself.
- In background mode, `ensure_watchers()` must not invoke the modal operator (it would log "Invalid operator call").

## How changes were verified (wrap-up, 2026-11-21)

- Baseline before the cleanup: 177/177 headless checks. After: 174/174. The difference is the 3 checks for the deleted `_preset_label`.
- Old vs new trace: 400 seeded random scenarios, 24 000 steps. It recorded status, remaining time, texts, shading, playback, hold and draw calls. Result: 0 differences.
- Windowed checks gave identical results on old and new. `tick()` went from 10.4 to 9.2 µs and `redraw_topbars()` from 2.3 to 1.2 µs.
- Built the zip and installed it in a scratch profile. `check_installed_package.py` reported no problems.

## Release checklist

1. Bump the version in the manifest and in `bl_info`. README badges are live: never hard-code versions in them. The download-size badge reads `release-size.json` on the `badges` branch, which CI force-pushes at each release: don't delete that branch.
2. Run the tests. Commit and push `main`. Wait for green CI.
3. `git tag -a vX.Y.Z -m "<title>" -m "<notes>"`, then `git push origin vX.Y.Z`. CI tests, builds and publishes the release with the zip. The notes come from the tag message.

## Naming

- The working name was *Idle Render Pause* (`idle_render_pause`, `wm.irp_*`, `IRP_*`). Before the 1.0.0 release it was renamed to **Resource Safeguard**: id and package `resource_safeguard`, operators `wm.rsg_*`, classes `RSG_*`/`WM_OT_rsg_*`, env vars `RSG_OUT`/`RSG_SHOT`. Never change the id again: installed copies would stop upgrading in place and lose their preferences.

## Git

- Remote: `origin` https://github.com/mttfntn/resource-safeguard-blender.git (private, not a fork).
- Branch: `main`. Tags: `vX.Y.Z` (annotated).
- Ignored: `__pycache__/`, `dist/`, `*.zip`, `tests/rsg_*.txt`.
