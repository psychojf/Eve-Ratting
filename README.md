# Eve Ratting

A lightweight desktop dashboard for **EVE Online** PvE pilots. Eve Ratting watches your client's gamelog and chatlog files in real time and turns them into a clean, themed overlay showing DPS, ISK/hour, bounties, taxes, loot value, missions, anomalies and EWAR alerts — without ever touching the game client.

The tool is a single Python script (or standalone `.exe`) using Tkinter. A **fleet overview window** acts as the hub and automatically spawns a separate dashboard for every character whose gamelog it finds, making it usable across multiple accounts simultaneously.

## Features

- **Fleet overview** — one hub window lists every detected character with live gross ISK/hr, net ISK/hr and session time; new characters appear automatically every 10 seconds
- **Per-character dashboards** — each pilot gets its own always-on-top, resizable, draggable window
- **Live combat tracking** — outgoing/incoming DPS over a sliding 15-second window, total damage dealt and received, hits and misses, peak DPS
- **ISK metrics** — gross bounties, configurable tax rate, loot estimation, net ISK and ISK/hour with a collapsible breakdown panel
- **Bounty backfill** — on Play, the last 15 minutes of the log are replayed so recent bounties are never missed
- **Mission tracker** — reads agent chatlogs for accepted missions, objective completion, mission counts and storyline progress (every 16 missions)
- **Anomaly tracker** — automatically segments ratting into discrete sites by combat gap, tracks per-site time and ISK, computes averages and best site; configurable gap threshold
- **EWAR alerts** — instant warnings for warp scramble and stasis web attempts, escalation and dreadnought spawn notifications, with a visual flash
- **Loot clipboard** — paste an EVE cargo/loot window (Ctrl+A, Ctrl+C) while running; prices are looked up via ESI (Jita sell for faction/deadspace items, universe average for everything else, with an offline fallback table)
- **Standings tracker** — captures faction standing changes from the gamelog
- **Session history** — persistent JSON history with lifetime totals; browsable per-character in a scrollable popup
- **Detached panels** — pop any section (ISK, DPS, Missions, Anomalies, Alerts) out into its own always-on-top resizable window; positions remembered between sessions
- **Collapsible sections** — each panel can be collapsed to its header bar to save screen space; the whole window can be collapsed to just its title bar with a double-click
- **22+ themes** — EVE Online default plus faction palettes (Caldari, Minmatar, Amarr, Gallente, Guristas, Blood Raiders, Angel Cartel, Serpentis, Sansha's Nation, Triglavian, EDENCOM, Intaki Syndicate, ORE, Mordu's Legion, Thukker Tribe, CONCORD, Society of Conscious Thought and more); applied live with no flicker, saved per character
- **Configurable opacity** — set window transparency from 20 % to 100 % (default 85 %)
- **System tray** — minimize to tray (optional, requires `pystray` + `Pillow`)
- **Standalone executable** — a pre-built `Eve Ratting.exe` is included; no Python required to run it

## How it works

Eve Ratting is a passive log reader. It tails the files EVE Online writes to:

```
%USERPROFILE%\Documents\EVE\logs\Gamelogs
%USERPROFILE%\Documents\EVE\logs\Chatlogs
```

It parses combat lines, bounty payouts, mission events, EWAR attempts and standings updates with regular expressions, then aggregates them into per-character dashboards. **No memory reading, no packet sniffing, no API keys, no client modification** — it only reads files the game itself writes to disk. This keeps it fully compliant with the EVE Online EULA.

## Requirements

- **Windows 10/11** or **Linux** (native client, Steam, or Proton — log paths are auto-detected)
- **Python 3.9+** (uses `datetime.timezone`, f-strings, `deque`, etc.) — *or* use the included `Eve Ratting.exe`
- **Tkinter** (bundled with the standard Python.org installer)
- **EVE Online** client with gamelogs enabled (on by default)

Optional Python packages (the app runs without them, with reduced functionality):

| Package | Purpose |
|---|---|
| `pystray` | System tray icon |
| `Pillow` | Required by `pystray` for the tray image |
| `pyperclip` | Clipboard paste support for loot estimation |

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

Or just double-click **Eve Ratting.exe**.

On first launch the app creates `ratting_config.json` next to the script, auto-detects your EVE log directories and opens the fleet overview plus one dashboard per character. Open **Settings** (⚙ in the overview header) to change log paths, tax rate, theme, polling interval, opacity or site gap.

For a full walkthrough see [HOW_TO.txt](HOW_TO.txt).

## Controls

| Button | Action |
|---|---|
| ▶ Play | Start the session timer; back-fills the last 15 min of bounties |
| ⏸ Pause | Freeze the timer; parsing continues in the background |
| ■ Stop | Save session to history and halt |
| RESET | Save session and immediately start a fresh new session |
| NEXT SITE | Close the current anomaly, save session data, and reset |

## Files the app creates

All written next to `ratting.py` (or the `.exe`):

| File | Purpose |
|---|---|
| `ratting_config.json` | User settings (paths, tax, opacity, theme per character, etc.) |
| `ratting_history.json` | Past session records |
| `ratting_prices.json` | ESI market price cache (refreshed every 24 h) |
| `ratting_nameids.json` | EVE item name → type ID cache for loot lookups |

None of these contain credentials or personal data beyond your in-game character name.

## Contributing

Pull requests, bug reports and theme submissions are welcome. Open an issue or PR on GitHub.

## Disclaimer

Eve Ratting only reads local log files written by the EVE Online client. It does not interact with the game client memory, network traffic, or the official EVE API beyond fetching public market prices from ESI. Use at your own risk.
