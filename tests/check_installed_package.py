"""Check the built extension after installing it into a SCRATCH profile.

Install, then run (with BLENDER_USER_* pointing to the scratch profile):
    blender -b --command extension install-file --repo user_default --enable dist/resource_safeguard-X.Y.Z.zip
    blender -b --python-exit-code 1 --python tests/check_installed_package.py
Exits 1 if the installed extension is missing, disabled or broken.
"""
import os
import sys

import bpy

MOD = "bl_ext.user_default.resource_safeguard"
problems = []
addon = bpy.context.preferences.addons.get(MOD)
if addon is None:
    problems.append("extension not enabled: " + MOD)
else:
    rsg = sys.modules[MOD]
    prefs = addon.preferences
    for name in ("enabled", "show_timer", "pause_animation", "switch_to_solid",
                 "timeout_preset", "custom_seconds"):
        if name not in prefs.bl_rna.properties:
            problems.append("missing preference " + name)
    if not bpy.app.timers.is_registered(rsg.tick):
        problems.append("timer not registered")
    if rsg.draw_topbar not in bpy.types.TOPBAR_HT_upper_bar.draw._draw_funcs:
        problems.append("top bar section not added")
    for cls in ("RSG_PT_idle_menu", "WM_OT_rsg_toggle_timer_pause", "WM_OT_rsg_input_watcher"):
        if not hasattr(bpy.types, cls):
            problems.append("class not registered: " + cls)
    rsg.tick()  # one real step must not raise
    pkg_dir = os.path.dirname(rsg.__file__)
    if not os.path.isfile(os.path.join(pkg_dir, "LICENSE")):
        problems.append("LICENSE missing from installed package")
    import tomllib
    with open(os.path.join(pkg_dir, "blender_manifest.toml"), "rb") as f:
        manifest = tomllib.load(f)
    print("installed at", pkg_dir, "version", manifest["version"])

print("PROBLEMS:", problems or "none")
sys.stdout.flush()
os._exit(1 if problems else 0)
