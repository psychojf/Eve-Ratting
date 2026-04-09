# Eve Ratting

A lightweight desktop dashboard for **EVE Online** PvE pilots. Eve Ratting watches your client's gamelog and chatlog files in real time and turns them into a clean, themed overlay showing DPS, ISK/hour, bounties, taxes, loot value, missions, anomalies and EWAR alerts — without ever touching the game client.

The tool is a single Python script using Tkinter, designed to sit on a second monitor or as a small docked window beside the EVE client.

## Features

- **Live combat tracking** — outgoing/incoming DPS over a sliding 15-second window, total damage dealt and received, hits and misses
- **ISK metrics** — gross bounties, configurable tax rate, loot estimation, net ISK and ISK/hour
- **Mission tracker** — detects accepted missions from chatlogs, objective completion, mission counts and storyline progress
- **Anomaly tracker** — automatically segments ratting sites by combat gaps, tracks per-site time and ISK, computes averages and best site
- **EWAR alerts** — instant warnings for warp scramble and stasis web attempts
- **Standings tracker** — captures faction standing changes
- **Session history** — persistent JSON history of past sessions, browsable in a popup window
- **System tray** — minimize to tray (optional, requires `pystray` + `Pillow`)
- **Clipboard helpers** — paste killmails and other content (optional, requires `pyperclip`)
- **22+ themes** — EVE Online default plus faction palettes (Caldari, Minmatar, Amarr, Gallente, Guristas, Blood Raiders, Angel, Serpentis, Sansha, Triglavian, EDENCOM, ORE, CONCORD and more)
- **Detached widgets** — pop individual panels out into their own always-on-top windows
- **Single-file, no install** — one Python script, no database, no server, no account required

## How it works

Eve Ratting is a passive log reader. It tails the files EVE Online writes to:

```
%USERPROFILE%\Documents\EVE\logs\Gamelogs
%USERPROFILE%\Documents\EVE\logs\Chatlogs
```

It parses combat lines, bounty payouts, mission events and standings updates with regular expressions, then aggregates them into the dashboard. **No memory reading, no packet sniffing, no API keys, no client modification** — it only reads files the game itself writes to disk. This keeps it fully compliant with the EVE Online EULA.

## Requirements

- **Windows 10/11** (the default log paths assume Windows; the script itself is cross-platform aware but is only tested on Windows)
- **Python 3.9+** (uses `datetime.timezone`, f-strings, `deque(maxlen=)`, etc.)
- **Tkinter** (bundled with the standard Python.org installer)
- **EVE Online** client with gamelogs enabled (on by default)

Optional Python packages (the app runs without them, with reduced functionality):

- `pystray` — system tray icon
- `Pillow` — required by `pystray` and for the tray icon image
- `pyperclip` — clipboard paste support

See [requirements.txt](requirements.txt).

## Quick start

```bash
# 1. Clone
git clone https://github.com/psychojf/Eve-Ratting.git
cd Eve-Ratting

# 2. (optional) install optional dependencies
pip install -r requirements.txt

# 3. Run
python ratting.py
```

On first launch the app creates `ratting_config.json` next to the script and starts watching the default EVE log directory. Open **Settings** to change the log path, tax rate, theme, polling interval and tray behavior.

For a more detailed walkthrough see [HOW_TO.txt](HOW_TO.txt).

## Files the app creates

All written next to `ratting.py`:

| File | Purpose |
|---|---|
| `ratting_config.json` | User settings (theme, paths, tax %, etc.) |
| `ratting_history.json` | Past session records |
| `ratting_prices.json` | Cached item prices for loot estimation |
| `ratting_nameids.json` | Cached EVE typeID/name lookups |

None of these contain credentials or personal data beyond your in-game character name.

## Contributing

Pull requests, bug reports and theme submissions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Security

If you find a security issue, please follow the disclosure process in [SECURITY.md](SECURITY.md).

## Disclaimer

Eve Ratting only reads local log files written by the EVE Online client. It does not interact with the game client memory, network traffic, or the official EVE API. Use at your own risk.
