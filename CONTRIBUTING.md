# Contributing to Eve Ratting

Thanks for taking the time to contribute! Eve Ratting is a small,
community-driven tool for EVE Online PvE pilots. Bug reports, feature
suggestions, theme submissions and pull requests are all welcome.

By participating in this project you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Ground rules

- **Stay within the EVE Online EULA.** This project only reads files the
  client writes to disk. Contributions must not introduce client memory
  reading, packet inspection, automation/botting, or anything else that
  violates CCP's Terms of Service.
- **Keep it single-file friendly.** Eve Ratting is intentionally one Python
  script with no build step. New features should fit that model unless there
  is a strong reason to split things.
- **No telemetry, no network calls without consent.** Any new outbound HTTP
  request must be opt-in and clearly documented.

## Reporting bugs

Open a GitHub issue and include:

1. **What happened** vs. **what you expected to happen**
2. **Steps to reproduce** — ideally with a small snippet of the gamelog or
   chatlog line that triggered the problem (redact your character name if you
   prefer)
3. **Your environment** — OS version, Python version (`python --version`),
   installed optional packages
4. **A traceback** if the app crashed (Eve Ratting prints to stdout when run
   from a terminal)

Please **do not** post full unredacted log files; one or two relevant lines
are usually enough.

## Suggesting features

Open an issue describing:

- The use case ("As a Sansha incursion runner I want…")
- Why the existing UI/metrics don't already cover it
- A rough idea of where it would live in the dashboard

Small, focused features are more likely to be merged than sweeping
restructures.

## Submitting a pull request

1. **Fork** the repo and create a topic branch:
   ```bash
   git checkout -b fix/dps-window-trim
   ```
2. **Make your change.** Match the existing style — French inline comments
   on helper methods, hex colors at the top of the file, regex patterns
   grouped by purpose.
3. **Smoke-test the app** by running `python ratting.py` and exercising the
   panels affected by your change.
4. **Keep diffs small.** One concern per PR. Reformatting unrelated code
   makes review hard.
5. **Write a clear PR description** explaining *why*, not just *what*.
6. **Open the PR** against `main`.

## Code style

- Python 3.9+ syntax
- 4-space indentation, no tabs
- Prefer standard-library only; new third-party dependencies must be
  optional and gracefully degrade if missing (see how `pystray`, `Pillow`
  and `pyperclip` are imported at the top of `ratting.py`)
- Keep regex patterns documented with a short comment explaining what they
  match
- Don't introduce blocking calls on the Tk main thread — use `threading` or
  `root.after(...)` like the rest of the code

## Adding a theme

Themes live in the `THEMES` dict near the top of `ratting.py`. To add one:

1. Pick a base color and an accent color (hex).
2. Add an entry like:
   ```python
   "My Faction": _gen_theme("#101418", "#5b8fa8"),
   ```
3. Run the app, open Settings → Theme, and verify it looks right against
   every panel (combat, mission, anomaly, history).
4. Submit a PR with a screenshot.

## Adding a parser pattern

If a new gamelog or chatlog line should be recognized:

1. Add a `RE_*` constant in the regex section, with a one-line French
   comment describing what it matches.
2. Wire it into the appropriate parser method on `App` (combat, bounty,
   mission, EWAR, …).
3. Add a sample log line (or a link to one) in the PR description so a
   reviewer can sanity-check it.

## License of contributions

By submitting a pull request you agree that your contribution will be
released under the same terms as the rest of the project.
