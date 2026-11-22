## What this changes

<!-- What does the pull request do, and why? Link the issue it fixes, e.g. "Fixes #12". -->

## How it was tested

- [ ] Headless suite passes in an isolated Blender 5.3 (`tests/test_resource_safeguard.py`, ends with `0 failed`)
- [ ] For a bug fix: a new check that fails without the fix
- [ ] Windowed checks run if it touches windows, input, the top bar or playback (see HANDOVER.md, "How to run the tests")
- [ ] Tried by hand in Blender if it changes the top bar or the timer menu

## Checklist

- [ ] New logic that doesn't need `bpy` is in `core.py`, tested with the fake clock
- [ ] Comments match the code (operator and panel docstrings are tooltips: use `#` comments there)
- [ ] README updated if users will notice the change
