# Contributing to Resource Safeguard

Thanks for helping! Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or suggesting a feature

Open an [issue](https://github.com/mttfntn/resource-safeguard-blender/issues/new/choose) and pick a form:

- **Bug report:** say which Blender version, add-on version and render engine you use, your settings, and the steps to reproduce.
- **Feature request:** describe what you're trying to do, not only the solution you have in mind.

First, check whether someone has already opened an issue for the same thing, and read the README's [known limits](https://github.com/mttfntn/resource-safeguard-blender#known-limits).

## Changing the code

[HANDOVER.md](HANDOVER.md) explains how the add-on is organised and the pitfalls already found. Read it before a larger change.

1. **Fork** the repository and create a branch for your change.
2. You need **Blender 5.3** (the only supported version). Python 3 is needed only for `tools/build_package.py`.
3. Run the headless tests from the repo root. `--factory-startup` keeps your own add-ons and preferences out of the test:

   ```
   blender -b --factory-startup --python-exit-code 1 --python tests/test_resource_safeguard.py
   ```

   Expected result: `174 checks, 0 failed` (or more). Never run the tests inside the Blender session you work in.
4. **If you touch windows, input, the top bar or playback,** also run the windowed checks (HANDOVER.md, "How to run the tests"). They open a Blender window for a few seconds.
5. **If you fix a bug,** add a check to `tests/test_resource_safeguard.py` that fails without your fix.
6. **Open a pull request.** The template has a short checklist. CI runs the headless tests, builds the extension and installs the built zip on Blender 5.3.

### Style

- Logic that doesn't need `bpy` goes in `resource_safeguard/core.py` and is tested with the fake clock. `__init__.py` is the Blender side.
- **Operators and panels:** their docstrings become tooltips, so use `#` comments for internal notes. (The pause button's docstring is its tooltip on purpose.)
- Draw code must not change data.
- Keep commits small, with messages that explain what changed and how you checked it.

## License

Resource Safeguard is GPL-3.0-or-later. By contributing, you agree that your contribution is released under the same license.
