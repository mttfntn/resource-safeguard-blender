# Handover: Resource Safeguard

## What it is

A Blender add-on (packaged as a Blender extension) that frees the GPU when the
user leaves Blender alone. A countdown runs while a visible 3D viewport is in
Rendered shading or an animation is playing. When nobody touches Blender for
the chosen time, it can stop the animation playback and switch Rendered
viewports to Solid. It never switches back by itself. It uses no
render-engine API, so it works with Octane, Cycles, EEVEE and Workbench.

The UI is one section on the right of the top bar: `[⏻ power][🕒 timer ▾][⏸ pause]`.
The timer button opens a menu with the idle time, *Show Timer*, and the two
end-of-timer actions (*Pause Animation*, *Render → Solid*).

The repository is public: https://github.com/mttfntn/resource-safeguard-blender
(not a fork; there is no upstream project).

## What you need

- **Blender 5.3** (the only supported version; the manifest allows 5.3.x and
  refuses 5.4+). On the development machine it is at
  `C:\Program Files\Blender Foundation\Blender 5.3\blender.exe`.
- Python 3.9+ on PATH only for `tools/build_package.py` (it just copies files
  and calls Blender).
- `git` and, for releases, push access to the GitHub repo.

## How the code is organized

| Path | What it is |
| --- | --- |
| `resource_safeguard/__init__.py` | Blender side: preferences, top bar section, dropdown panel, pause operator, per-window input watcher (modal operator), the 1 s timer `tick()`, handlers, `register()`/`unregister()`. |
| `resource_safeguard/core.py` | Pure logic, no `bpy`: `IdleController` (idle clock, countdown, end-of-timer actions, pause/hold), event filter, `m:ss` formatting. Tested with a fake clock. |
| `resource_safeguard/blender_manifest.toml` | Extension manifest: id, version, supported Blender versions (5.3.0 to <5.4.0), license. |
| `tests/test_resource_safeguard.py` | Main headless test suite (174 checks): core logic, add-on with real `SpaceView3D` objects, top bar draw with a fake layout, menu, preferences, register/unregister cycles. |
| `tests/check_windowed.py` | Real window: watcher starts, pause after idle, input does not restore, unregister is safe while events arrive. |
| `tests/check_animation_pause.py` | Real window: playback + Rendered viewport, timer ends, playback stops and viewport goes to Solid. Optional screenshots (`RSG_SHOT`). |
| `tests/check_topbar_redraw.py` | Real window: the countdown redraws every second with no input. |
| `tests/check_installed_package.py` | After installing the built zip into a scratch profile: enabled, registered, LICENSE included. |
| `tools/build_package.py` | Builds `dist/resource_safeguard-<version>.zip` (adds the repo LICENSE, validates, uses Blender's `extension build`). |
| `.github/workflows/ci.yml` | CI: tests + build + install check on every push; a `vX.Y.Z` tag also publishes a release. |
| `README.md`, `LICENSE`, `HANDOVER.md`, `AGENTS.md` | Docs. Only `LICENSE` goes into the package. |
| `CONTRIBUTING.md`, `SECURITY.md` | How to contribute; how to report security problems privately. |
| `.github/ISSUE_TEMPLATE/`, `.github/pull_request_template.md` | Issue forms (bug report, feature request; blank issues off) and the pull-request checklist. |

## How the main feature works

1. **Input watcher** (`WM_OT_rsg_input_watcher`): one modal operator per window.
   Every event is passed through (`PASS_THROUGH`). Real input (`core.is_user_event`,
   plus mouse moves that really move) calls `on_input()` → `IdleController.note_input()`.
2. **Timer** (`tick()`, `bpy.app.timers`, every 1.0 s):
   - `ensure_watchers()` starts a watcher in any window that has none
     (checked with `window.modal_operators`), e.g. new windows or after a file load.
   - Calls `IdleController.tick()` with the settings and Blender state: visible
     Rendered spaces, `bpy.app.is_job_running('RENDER')`, animation playing, hold.
   - Redraws the top bar while counting, or when the status changed.
3. **IdleController.tick()** decides:
   - off → `OFF`; final render running → `RENDER_JOB` (clock reset);
   - after an action → `PAUSED` until there was input **and** something runs again;
   - nothing rendering or playing → `NO_RENDER`;
   - idle < timeout → `COUNTDOWN` (`remaining`);
   - idle ≥ timeout → run the enabled actions → `PAUSED`, or `IDLE` (`0:00`)
     if no action applied.
4. **Top bar** (`draw_topbar`, prepended to `TOPBAR_HT_upper_bar`, right
   region only): power toggle (`enabled`), timer popover (`RSG_PT_idle_menu`,
   text from `timer_text()`), pause button (`wm.rsg_toggle_timer_pause`).
   In Blender 5.3 the top bar is a *global* area, not in `window.screen.areas`,
   so `draw_topbar` remembers `context.area` per window and `redraw_topbars()`
   tags those areas.

## How to make a change

1. Edit the code. Put logic that does not need `bpy` in `core.py`, and test it there.
2. Run the headless suite (below). Add checks for the new behaviour.
3. For anything about real windows, events, the top bar or playback, run the
   windowed checks too. They open a Blender window for a few seconds.
4. Never test inside the Blender session you work in. All test commands use
   `--factory-startup` (and the package check uses a scratch profile).
5. To try it in your own Blender, build the zip and install it (README).

## How to run the tests

From the repo root (Windows paths shown; on Linux use `blender`):

```
"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" -b --factory-startup --python-exit-code 1 --python tests/test_resource_safeguard.py
"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --factory-startup --enable-event-simulate --python tests/check_windowed.py
"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --factory-startup --enable-event-simulate --python tests/check_animation_pause.py
"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe" --factory-startup --enable-event-simulate --python tests/check_topbar_redraw.py
```

- The headless suite prints `N checks, 0 failed` and exits 1 on any failure.
- The windowed checks write their result to `RSG_OUT` (default: a `rsg_*.txt`
  file in the current folder) and quit by themselves.
  `--enable-event-simulate` makes Blender ignore your real mouse and keyboard,
  so moving the mouse over the test window cannot reset the timer.
- CI runs the headless suite, the build and the installed-package check on
  Linux. The windowed checks are local only (they need a display and GPU).

## How to make a release

1. Bump the version in **both** `resource_safeguard/blender_manifest.toml`
   (`version`) and `resource_safeguard/__init__.py` (`bl_info["version"]`).
2. The README badges are live (shields.io, GitHub): never hard-code a version
   in them.
3. Run the tests, commit, push to `main`, wait for green CI.
4. Create an **annotated** tag; its message becomes the release notes:
   `git tag -a v1.2.3 -m "Resource Safeguard 1.2.3" -m "- what changed"` then
   `git push origin v1.2.3`.
5. CI checks that the tag matches the manifest version, tests, builds and
   publishes the GitHub release with the zip attached.
6. Install the new zip in your Blender (README → Install).

## Bringing in updates from the original project

Not applicable: this project is not a fork. If Blender changes its API, the
places most likely to need work are listed under *Things to know*.

## Things to know

- The working name was *Idle Render Pause* (extension id `idle_render_pause`,
  operators `wm.irp_*`, classes `IRP_*`). It was renamed to Resource Safeguard
  (`resource_safeguard`, `wm.rsg_*`, `RSG_*`) before the 1.0.0 release, which
  was then published again under the new name. Do not change the id again, or
  installed copies stop upgrading in place and lose their preferences.
- The top bar is a global area in 5.3 (see above). `TOPBAR` never appears in
  `window.screen.areas`.
- Extensions do not expose `bl_info` on the installed module; read the version
  from `blender_manifest.toml`.
- Unregistering the add-on frees the watchers' modal handlers. Right after,
  `window.modal_operators` can show a `None` entry until the next event; that is
  Blender's cleanup and is harmless (tested in `check_windowed.py`).
- Clicking the pause button is input, so it freezes the timer at the full time.
- The paused state (pause button) is runtime only; all other settings are add-on
  preferences, saved with the user's Preferences.
- CI uploads no artifacts on purpose: the GitHub account's artifact storage quota
  was full and made the first CI run fail. The tag build publishes the release
  from the same job. Old artifacts in other repos fill that quota.
- Running `blender --command ...` without `--factory-startup` loads the user's
  real add-ons. Always add `--factory-startup` or a scratch profile.

## Known limits

- Another modal tool that keeps the input to itself (long sculpt stroke, grab)
  hides input from the watcher.
- Only viewports shown in a window are switched (the only ones that render).
- Nothing is switched back automatically by design.
- Tested only on Windows 11 with Blender 5.3.0 (locally) and Linux (CI,
  headless). macOS is untested.
