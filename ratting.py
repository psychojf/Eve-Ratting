# -*- coding: utf-8 -*-
import sys
import tkinter as tk
from tkinter import ttk, font as tkfont
import os, re, json, time, threading, urllib.request, traceback
from datetime import datetime, timedelta, timezone
from collections import deque

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding='utf-8')

# -- Dependency Check with Logging --
_TRAY_OK  = False
_CLIP_OK  = False
_LOOT_SPIN = ("◐", "◓", "◑", "◒")   # spinner frames for clipboard loading indicator

try:
    import pyperclip
    _CLIP_OK = True
except ImportError:
    pass

try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk
    _TRAY_OK = True
except ImportError as e:
    pass

# Optional: event-driven log watching. Falls back to timer polling when absent,
# so the pre-built .exe (no watchdog bundled) behaves exactly as before.
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_OK = True
except ImportError:
    _WATCHDOG_OK = False
    Observer = None
    class FileSystemEventHandler:   # fallback base so _LogEventHandler still defines
        pass

# Optional: audio EWAR alerts (winsound is Windows-only stdlib)
try:
    import winsound
    _SND_OK = True
except ImportError:
    _SND_OK = False

# ── Colors ───────────────────────────────────────────────────────────
BG       = "#080808"    # Main background (deep carbon)
BG_P     = "#121212"    # Panel background
BG_H     = "#1a1a1a"    # Header background
BG_C     = "#080808"    # Combobox/field background
BG_POP   = "#121212"    # Popup background
BD       = "#2a2a2a"    # Standard border
BDG      = "#333333"    # Highlight border
T0       = "#8b9fa9"    # Primary text highlight (EVE UI blue/grey)
T1       = "#6a7a85"    # Secondary text highlight
TB       = "#e5e5e5"    # Base text
TD       = "#777777"    # Dim text
CD       = "#8b9fa9"    # DPS / generic highlight
CR       = "#cc3325"    # Red / DPS In
CG       = "#d4b45d"    # Gold / Bounties / Kills
CI       = "#55a34f"    # Green / Net ISK
CT       = "#c45b47"    # Taxes
CK       = "#896a9e"    # Pending
CW       = "#c48b47"    # Warning
CM       = "#777777"    # Muted
CA       = "#55a34f"    # Active / Play
CP       = "#b89645"    # Paused
CS       = "#cc3325"    # Stop / Clear
CH       = "#5c7b8c"    # History
C_DETACH = "#8b9fa9"    # Detach button
C_MSN    = "#5b9bd5"    # Mission tracker accent
C_ALERT  = "#e07040"    # Alert / danger accent
C_ESCAL  = "#d4b45d"    # Escalation highlight
C_ANOM   = "#5b8fa8"    # Anomaly tracker accent
C_EWAR   = "#ff6b6b"    # EWAR alert (scram/web) — soft red

# ── Themes ───────────────────────────────────────────────────────────
# Éclaircit une couleur hex en ajoutant amt à chaque canal
def _lighten(hx, amt):
    h = hx.lstrip('#')
    r = min(255, int(h[0:2], 16) + amt)
    g = min(255, int(h[2:4], 16) + amt)
    b = min(255, int(h[4:6], 16) + amt)
    return f"#{r:02x}{g:02x}{b:02x}"

# Assombrit une couleur hex par facteur multiplicatif
def _dim(hx, factor=0.6):
    h = hx.lstrip('#')
    r = int(int(h[0:2], 16) * factor)
    g = int(int(h[2:4], 16) * factor)
    b = int(int(h[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

# Mélange deux couleurs hex avec interpolation linéaire
def _blend(h1, h2, t=0.5):
    a = h1.lstrip('#')
    b = h2.lstrip('#')
    r = int(int(a[0:2], 16) * (1 - t) + int(b[0:2], 16) * t)
    g = int(int(a[2:4], 16) * (1 - t) + int(b[2:4], 16) * t)
    bl = int(int(a[4:6], 16) * (1 - t) + int(b[4:6], 16) * t)
    return f"#{min(255,r):02x}{min(255,g):02x}{min(255,bl):02x}"

# Génère une palette complète depuis une couleur de base et un accent
def _gen_theme(base, accent):
    return {
        "BG": base, "BG_P": _lighten(base, 10), "BG_H": _lighten(base, 18),
        "BG_C": base, "BG_POP": _lighten(base, 10),
        "BD": _lighten(base, 30), "BDG": _lighten(base, 42),
        "T0": accent, "T1": _dim(accent, 0.7),
        "TB": "#e5e5e5", "TD": "#777777",
        "CD": accent, "CR": "#cc3325", "CG": "#d4b45d", "CI": "#55a34f",
        "CT": "#c45b47", "CK": "#896a9e", "CW": "#c48b47", "CM": "#777777",
        "CA": "#55a34f", "CP": "#b89645", "CS": "#cc3325",
        "CH": _blend(accent, "#5c7b8c"), "C_DETACH": accent,
        "C_MSN": _blend(accent, "#5b9bd5"), "C_ALERT": "#e07040",
        "C_EWAR": "#ff6b6b", "C_ESCAL": "#d4b45d", "C_ANOM": _blend(accent, "#5b8fa8"),
    }

THEME_DEFAULT = "EVE Online (Default)"

THEMES = {
    THEME_DEFAULT: {
        "BG": "#080808", "BG_P": "#121212", "BG_H": "#1a1a1a",
        "BG_C": "#080808", "BG_POP": "#121212",
        "BD": "#2a2a2a", "BDG": "#333333",
        "T0": "#8b9fa9", "T1": "#6a7a85",
        "TB": "#e5e5e5", "TD": "#777777",
        "CD": "#8b9fa9", "CR": "#cc3325", "CG": "#d4b45d", "CI": "#55a34f",
        "CT": "#c45b47", "CK": "#896a9e", "CW": "#c48b47", "CM": "#777777",
        "CA": "#55a34f", "CP": "#b89645", "CS": "#cc3325",
        "CH": "#5c7b8c", "C_DETACH": "#8b9fa9",
        "C_MSN": "#5b9bd5", "C_ALERT": "#e07040", "C_EWAR": "#ff6b6b",
        "C_ESCAL": "#d4b45d", "C_ANOM": "#5b8fa8",
    },
    "Caldari":                  _gen_theme("#191919", "#3C5F73"),
    "Caldari II":               _gen_theme("#0F1114", "#8A8F9A"),
    "Minmatar":                 _gen_theme("#161414", "#5A3737"),
    "Minmatar II":              _gen_theme("#140D0F", "#8C5055"),
    "Amarr":                    _gen_theme("#191714", "#BBA183"),
    "Amarr II":                 _gen_theme("#12110A", "#9A6928"),
    "Gallente":                 _gen_theme("#0F1414", "#576866"),
    "Gallente II":              _gen_theme("#0A0F0F", "#9EAE95"),
    "Guristas Pirates":         _gen_theme("#261500", "#FF9100"),
    "Blood Raiders":            _gen_theme("#260505", "#BE0000"),
    "Angel Cartel":             _gen_theme("#26110E", "#FF4D00"),
    "Serpentis":                _gen_theme("#060A0C", "#BBC400"),
    "Sansha's Nation":          _gen_theme("#0a0a0a", "#218000"),
    "Triglavian Collective":    _gen_theme("#262218", "#DE1400"),
    "Sisters of EVE":           _gen_theme("#262626", "#B60000"),
    "EDENCOM":                  _gen_theme("#001926", "#039DFF"),
    "Intaki Syndicate":         _gen_theme("#060A0C", "#393780"),
    "ORE":                      _gen_theme("#1A1A1A", "#D9A600"),
    "Mordu's Legion":           _gen_theme("#1A1F22", "#4B6B78"),
    "Thukker Tribe":            _gen_theme("#1F1A17", "#B35900"),
    "CONCORD":                  _gen_theme("#0A1428", "#0088FF"),
    "Society of Conscious Thought": _gen_theme("#0A111A", "#00E8FF"),
}

THEME_NAMES = list(THEMES.keys())

# Applique un thème nommé aux variables globales de couleur
def apply_theme_colors(name):
    global BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG
    global T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM
    global CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR
    t = THEMES.get(name, THEMES[THEME_DEFAULT])
    BG = t["BG"]
    BG_P = t["BG_P"]
    BG_H = t["BG_H"]
    BG_C = t["BG_C"]
    BG_POP = t["BG_POP"]
    BD = t["BD"]
    BDG = t["BDG"]
    T0 = t["T0"]
    T1 = t["T1"]
    TB = t["TB"]
    TD = t["TD"]
    CD = t["CD"]
    CR = t["CR"]
    CG = t["CG"]
    CI = t["CI"]
    CT = t["CT"]
    CK = t["CK"]
    CW = t["CW"]
    CM = t["CM"]
    CA = t["CA"]
    CP = t["CP"]
    CS = t["CS"]
    CH = t["CH"]
    C_DETACH = t["C_DETACH"]
    C_MSN = t["C_MSN"]
    C_EWAR = t["C_EWAR"]
    C_ALERT = t["C_ALERT"]
    C_ESCAL = t["C_ESCAL"]
    C_ANOM = t["C_ANOM"]

# ── Paths & defaults ─────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE  = os.path.join(_BASE, "ratting_config.json")
HISTORY_FILE = os.path.join(_BASE, "ratting_history.json")
PRICE_CACHE  = os.path.join(_BASE, "ratting_prices.json")
NAMEID_CACHE = os.path.join(_BASE, "ratting_nameids.json")

# ESI politely requests a descriptive User-Agent; anonymous requests get throttled/blocked.
_ESI_UA = "Eve-Ratting/1.0 (+https://github.com/psychojf/Eve-Ratting)"

# Serializes the shared market-price cache download/write across all CharacterWindows,
# so only one thread fetches ESI and writes ratting_prices.json (the rest load what it wrote).
_PRICE_LOCK = threading.Lock()
# Guards the shared name→type_id cache file against concurrent loot-thread writes.
_NAMEID_LOCK = threading.Lock()

def _find_eve_log_path(subdir):
    """Return the first existing EVE log path across Windows, Linux native, and Linux/Proton."""
    candidates = [
        # Windows / macOS native
        os.path.join(os.path.expanduser("~"), "Documents", "EVE", "logs", subdir),
        # Linux native client
        os.path.join(os.path.expanduser("~"), ".eve", "sharedcache", "tq", "logs", subdir),
        # Linux Steam / Proton (default Steam library)
        os.path.join(os.path.expanduser("~"), ".local", "share", "Steam",
                     "steamapps", "compatdata", "8500", "pfx", "drive_c",
                     "users", "steamuser", "My Documents", "EVE", "logs", subdir),
        # Linux Steam with custom library on second drive
        os.path.join("/mnt", "ssd", "SteamLibrary", "steamapps", "compatdata",
                     "8500", "pfx", "drive_c", "users", "steamuser",
                     "My Documents", "EVE", "logs", subdir),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return candidates[0]  # fall back to Windows default even if missing

DEF_PATH     = _find_eve_log_path("Gamelogs")
DEF_CHAT     = _find_eve_log_path("Chatlogs")
DEF_POLL     = 250
DEF_TAX      = 12.5
DEF_ALPHA    = 0.85  # Default set to 85%
DPS_W        = 15
WIN_W        = 290
MAX_ALERTS   = 5     # Max mission/alert feed entries to display
ANOM_GAP     = 45    # Seconds of no combat = site boundary (warp gap)
BACKFILL_MINS = 15   # On Play, scan gamelog for bounties from last N minutes
DPS_GRAPH_W  = 120   # Fenêtre du graphique d'historique DPS (en secondes)
DPS_GRAPH_H  = 50    # Hauteur du graphique intégré en pixels

# ── DPS overlay transparency ─────────────────────────────────────────
# Color-key: any widget painted this exact color renders fully transparent
# under Windows -transparentcolor, so only text/graph lines show over EVE.
# Dark so anti-alias fringe on text edges blends into EVE's space backdrop.
OVERLAY_KEY     = "#010101"
# Solid backdrop shown ONLY while repositioning (move mode) so the whole
# frame is grabbable in every view; reverts to OVERLAY_KEY once placed.
OVERLAY_MOVE_BG = "#0d0d12"

# ── Log filename / header patterns ───────────────────────────────────
RE_CF = re.compile(r'^(\d{8})_(\d{6})_(\d+)\.txt$')           # combat log filename
RE_LI = re.compile(r'Listener:\s*(.+)',              re.I)     # character name header
RE_TS = re.compile(r'\[\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]')  # timestamp
RE_SS = re.compile(r'Session\s+Started:\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', re.I)

# ── Combat regex patterns ────────────────────────────────────────────
# HTML groups 1-3, plain groups 4-6: amt, name, suffix

RE_TO = re.compile(                                            # outgoing damage
    r'\(combat\)\s*(?:<[^>]+>)*<b>(\d+)</b>.*?\bto\b'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+?)</b>.*?-\s*(.+)$'
    r'|\(combat\)\s+(\d+)\s+to\s+([\w\s\'-]+?)\s+-\s+(.+)$',
    re.I
)
RE_FR = re.compile(                                            # incoming damage
    r'\(combat\)\s*(?:<[^>]+>)*<b>(\d+)</b>.*?\bfrom\b'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+?)</b>.*?-\s*(.+)$'
    r'|\(combat\)\s+(\d+)\s+from\s+([\w\s\'-]+?)\s+-\s+(.+)$',
    re.I
)
RE_NM = re.compile(r'\(combat\)\s*([\w\s\'-]+?)\s+misses\s+you\s+completely',   re.I)  # NPC miss
RE_DM = re.compile(r'\(combat\)\s+Your\s+(.+?)\s+misses\s+([\w\s\'-]+?)\s+completely', re.I)  # drone miss

# ── Bounty payout pattern ────────────────────────────────────────────
# Handles both plain and HTML-tagged bounty lines
RE_BT = re.compile(r'\(bounty\)\s*(?:<[^>]+>)*([\d\s,.]+)\s*ISK.*?added\s+to\s+next\s+bounty\s+payout', re.I)

# ── Faction/loot keyword pattern ─────────────────────────────────────
RE_FACTION_ITEM = re.compile(
    r'\b(Shadow|Dread|True|Dark|Sentient|Infested|'
    r'Caldari Navy|Amarr Navy|Federation Navy|Republic Fleet|'
    r'Pith|Gist|Corpus|Core|C-Type|B-Type|A-Type|X-Type)\b',
    re.I
)

# ── Mission/alert patterns (gamelog) ─────────────────────────────────
RE_OBJ_MET  = re.compile(r'Objective accomplished\.\s*You may now return to your agent\.', re.I)
RE_MSN_COMP = re.compile(r'You completed mission\s+(\d+)',                                 re.I)
RE_STAND    = re.compile(r'Your standings with\s+(.*?)\s+have increased by\s+([\d.]+)',    re.I)
RE_FACTION  = re.compile(r'\(combat\).*?\b(Shadow|Dread|True|Dark|Sentient|Infested|Caldari Navy|Amarr Navy)\b\s+([\w\s]+?)\s*-\s*Hits', re.I)
RE_DREAD    = re.compile(r'\(notify\)\s+(.*?)\s*Dreadnought detected',                    re.I)
RE_ESCAL    = re.compile(r'A portion of the\s+(.*?)\s+database reveals the potential location', re.I)

# ── EWAR patterns (scram/web) ────────────────────────────────────────
# Group 1=HTML attacker, 2=plain attacker
RE_SCRAM = re.compile(
    r'\(combat\)\s*(?:<[^>]+>)*(?:<b>)?Warp\s+scramble\s+attempt(?:</b>)?'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+)</b>'
    r'|\(combat\)\s+Warp\s+scramble\s+attempt\s+from\s+([\w\s\'-]+?)\s+to\s+you',
    re.I
)
RE_WEB = re.compile(r'\(notify\)\s*.*?([\w\s\'-]+?)\s+has started webifying you', re.I)

# ── Chatlog patterns (agent convos) ──────────────────────────────────
RE_MSN_ACCEPT = re.compile(r'You have accepted the mission\s+"(.*?)"', re.I)
RE_CHATLOG_FN = re.compile(r'^Agent_.*\.txt$',                         re.I)

# ── Utility functions ────────────────────────────────────────────────
# Supprime les balises HTML d'une chaîne
def shtml(t): return re.sub(r'<[^>]+>', '', t).strip()

# Parse un entier en ignorant les espaces (ex: "1 234 567" → 1234567)
def pnum(s):
    cleaned = re.sub(r'[\s,.]+', '', s.strip())
    return int(cleaned) if cleaned else 0

# Formate un montant ISK en notation courte (K/M/B)
def fisk(v):
    if v >= 1e9: return f"{v/1e9:.2f}B"
    if v >= 1e6: return f"{v/1e6:.2f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"

# Formate un montant ISK avec séparateurs d'espaces
def fiskf(v): return f"{int(v):,}".replace(",", " ")

# Formate des secondes en durée lisible (HH:MM:SS)
def fdur(s):
    s = max(0, int(s))
    h, r = divmod(s, 3600)
    m, s2 = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s2:02d}"

# Extrait l'arme et le type de coup depuis une chaîne de combat
def ptail(t):
    t = shtml(t)
    p = [x.strip() for x in t.split(" - ") if x.strip()]
    if len(p) >= 2: return p[0], p[-1]
    return ("Unknown", p[0]) if p else ("Unknown", "Hits")


# Dessine les polylignes d'historique DPS (OUT/IN) sur un Canvas Tk.
# Partagé par le panneau DPS détaché et l'overlay DPS autonome.
def draw_dps_graph(canvas, hist, *, is_detached=False):
    """Draw OUT/IN DPS history polylines onto `canvas` from a deque of
    (monotonic_ts, dps_out, dps_in). Caller guarantees canvas exists/viewable."""
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 10 or h < 10:
        return
    canvas.delete("all")
    if len(hist) < 2:
        return
    now = time.monotonic()
    cutoff = now - DPS_GRAPH_W
    pts = [(t, do, di) for t, do, di in hist if t >= cutoff]
    if len(pts) < 2:
        return
    max_dps = max(max(do for _, do, _ in pts), max(di for _, _, di in pts), 100)
    y_max = max_dps * 1.1
    pad_x, pad_y = 2, 3
    gw = w - pad_x * 2
    gh = h - pad_y * 2
    t_start = cutoff
    t_span = DPS_GRAPH_W
    def _px(t, v):
        x = pad_x + ((t - t_start) / t_span) * gw
        y = pad_y + gh - (v / y_max) * gh
        return x, y
    for frac in (0.25, 0.50, 0.75):
        gy = pad_y + gh - frac * gh
        canvas.create_line(pad_x, gy, w - pad_x, gy, fill=BD, dash=(2, 4), tags="grid")
    coords_out = []
    coords_in = []
    for t, do, di in pts:
        ox, oy = _px(t, do)
        ix, iy = _px(t, di)
        coords_out.extend([ox, oy])
        coords_in.extend([ix, iy])
    if any(v > 0 for _, _, v in pts):
        canvas.create_line(*coords_in, fill=_dim(CR, 0.4), width=1, smooth=True, tags="line_in")
    if any(v > 0 for _, v, _ in pts):
        canvas.create_line(*coords_out, fill=CD, width=2 if is_detached else 1, smooth=True, tags="line_out")
    if is_detached and h > 40:
        canvas.create_text(pad_x + 2, pad_y + 2, text=f"{max_dps:,.0f}",
                           font=("Consolas", 7), fill=TD, anchor="nw", tags="label")

# Lit le nom du personnage dans l'en-tête du fichier log
def rlisten(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            for i, l in enumerate(f):
                if i > 15: break
                m = RE_LI.search(l)
                if m: return m.group(1).strip()
    except Exception:
        pass
    return None

# Scanne récursivement le dossier pour trouver les logs de combat par personnage
def scan_logs(base):
    r = {}          # char_id → newest log path
    mt = {}         # char_id → that path's mtime (avoids re-stat'ing on each compare)
    if not os.path.isdir(base): return r
    for dp, dn, fns in os.walk(base):
        for fn in fns:
            m = RE_CF.match(fn)
            if m:
                c = m.group(3)
                fp = os.path.join(dp, fn)
                fmt = os.path.getmtime(fp)
                if c not in r or fmt > mt[c]:
                    r[c] = fp
                    mt[c] = fmt
    return r

# Charge la configuration JSON depuis le disque
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# Sauvegarde la configuration JSON sur le disque
def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# Charge l'historique des sessions depuis le disque
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

# Sauvegarde l'historique des sessions sur le disque
def save_history(entries):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

# Sauvegarde les données de la session courante dans l'historique
def save_session(data, char_name, tax_pct):
    if data.bg <= 0 and data.dd <= 0 and data.loot_val <= 0:
        return
    entry = {
        "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        "character":  char_name or "Unknown",
        "duration_s": int(data.secs()),
        "gross_isk":  data.bg,
        "net_isk":    int(data.bg * (1 - data.tax)) + int(data.loot_val),
        "loot_val":   int(data.loot_val),
        "tax_pct":    tax_pct,
        "isk_hr":     int(data.isk()) if data.secs() >= 60 else 0,
        "kills":      data.bc,
        "dmg_dealt":  data.dd,
        "dmg_recv":   data.dr,
        "hits":       data.hd,
        "misses":     data.md,
        "peak_dps_d": int(data.pkd),
        "peak_dps_r": int(data.pkr),
        "missions_done": data.missions_done,
        "last_mission":  data.mission_name or "",
        "sites_cleared": len(data.anom_completed),
        "avg_site_time": int(sum(
            max(0, (a["end"] - a["start"]).total_seconds())
            for a in data.anom_completed if a["end"] and a["start"]
        ) / max(len(data.anom_completed), 1)),
        "avg_site_isk":  int(sum(a["isk"] for a in data.anom_completed)
                             / max(len(data.anom_completed), 1)),
        "best_site_isk": max((a["isk"] for a in data.anom_completed), default=0),
    }
    hist = load_history()
    hist.append(entry)
    save_history(hist)


# ── Tooltip helpers ──────────────────────────────────────────────────
# Infobulle statique affichée au survol d'un widget
class Tooltip:

    # Initialise et lie les événements de survol
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    # Affiche l'infobulle sous le widget
    def _show(self, e):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.attributes("-alpha", 0.85)  # EVE UI glass effect
        self.tip.geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text, bg=BG_H, fg=T0,
                       font=tkfont.Font(family="Consolas", size=8),
                       bd=1, relief="solid", highlightbackground=BDG,
                       padx=4, pady=1)
        lbl.pack()

    # Détruit l'infobulle
    def _hide(self, e):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# Infobulle dynamique dont le texte est généré par une fonction
class DynamicTooltip:
    # Initialise avec une fonction génératrice de texte
    def __init__(self, widget, text_fn):
        self.widget = widget
        self.text_fn = text_fn
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    # Génère et affiche le texte dynamique
    def _show(self, e):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.attributes("-alpha", 0.85)  # EVE UI glass effect
        self.tip.geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text_fn(), bg=BG_H, fg=CT,
                       font=tkfont.Font(family="Consolas", size=8),
                       bd=1, relief="solid", highlightbackground=BDG,
                       padx=4, pady=1)
        lbl.pack()

    # Détruit l'infobulle
    def _hide(self, e):
        if self.tip:
            self.tip.destroy()
            self.tip = None

# Résout le chemin d'une ressource (compatible PyInstaller)
def _get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # Try next to exe/script first, then current working directory
    p = os.path.join(_BASE, relative_path)
    if os.path.exists(p):
        return p
    return os.path.join(os.path.abspath("."), relative_path)

# ── Session data model ───────────────────────────────────────────────
# Conteneur de données de session (DPS, ISK, kills, anomalies, missions)
class Data:

    # Initialise et réinitialise les données
    def __init__(self): self.reset()

    # Remet toutes les données à zéro
    def reset(self):
        self.t0 = None
        self.acc_sec = 0.0
        self.dd = self.dr = 0
        self.hd = self.md = 0           # Coups réussis sortants / coups manqués sortants
        self.bg = 0                     # Bounties brutes accumulées
        self.tax = DEF_TAX / 100
        self.bc = 0                     # Compteur de kills (bounties reçues)
        self.loot_val = 0               # Valeur totale estimée du loot
        self.pkd = self.pkr = 0         # Pics DPS sortants / entrants

        # Suivi de mission
        self.mission_name = None        # Nom de la mission en cours (chatlog)
        self.mission_obj_met = False    # Drapeau « objectif accompli »
        self.missions_done = 0          # Missions terminées cette session
        self.alerts = deque(maxlen=MAX_ALERTS)  # [(timestamp_str, type, text), ...]

        # Suivi des anomalies
        self.anom_current = None         # dict de l'anomalie active (ou None)
        self.anom_completed = []         # liste des anomalies terminées
        self.anom_last_combat = None     # datetime du dernier événement de combat (UTC)

        # Deque + somme glissante pour calcul DPS en O(1)
        self.ed = deque(maxlen=1000)     # (ts, dmg) sortant
        self.er = deque(maxlen=1000)     # (ts, dmg) entrant
        self.ed_sum = 0
        self.er_sum = 0

        # Historique DPS pour le graphique (échantillonné à chaque tick)
        # Chaque entrée : (monotonic_ts, dps_out, dps_in)
        self.dps_hist = deque(maxlen=int(DPS_GRAPH_W * 1000 / DEF_POLL) + 1)

    # Retourne le nombre de secondes totales de la session
    def secs(self):
        base = self.acc_sec
        if self.t0:
            base += (datetime.now(timezone.utc) - self.t0).total_seconds()
        return base

    # Calcule le DPS en O(1) sur la fenêtre glissante DPS_W
    def dps(self, is_out=True):

        # O(1) DPS — trims old entries live, no full list scan
        # Uses time.monotonic() so PC/EVE server clock drift and NTP jumps can't
        # cause entries to expire the instant they're added.
        now = time.monotonic()
        cutoff = now - DPS_W
        deq = self.ed if is_out else self.er
        total = self.ed_sum if is_out else self.er_sum
        while deq and deq[0][0] < cutoff:
            total -= deq.popleft()[1]
        if is_out:
            self.ed_sum = total
        else:
            self.er_sum = total
        return total / DPS_W if deq else 0

    # Enregistre un coup sortant et met à jour les totaux
    def add_dmg_out(self, ts, dmg):
        # If the deque is full, append() silently evicts ed[0]; subtract it from
        # the running sum first so ed_sum stays == sum(dmg in ed) (O(1) invariant).
        if len(self.ed) == self.ed.maxlen:
            self.ed_sum -= self.ed[0][1]
        self.ed.append((time.monotonic(), dmg))
        self.ed_sum += dmg
        self.dd += dmg
        self.hd += 1

    # Enregistre un coup reçu et met à jour les totaux
    def add_dmg_in(self, ts, dmg):
        if len(self.er) == self.er.maxlen:
            self.er_sum -= self.er[0][1]
        self.er.append((time.monotonic(), dmg))
        self.er_sum += dmg
        self.dr += dmg

    # Calcule l'ISK/heure nette (bounties - taxes + loot)
    def isk(self):
        s = self.secs()
        return ((self.bg * (1 - self.tax) + self.loot_val) / s * 3600) if s >= 60 else 0


# ── History window ───────────────────────────────────────────────────
# Fenêtre popup affichant l'historique des sessions passées
class HistoryWindow:
    # Columns: (header, json key, width, color)
    COLS = [
        ("DATE",    "date",       17, TB),
        ("CHAR",    "character",  13, T1),
        ("TIME",    "duration_s", 8,  TD),
        ("NET ISK", "net_isk",    10, CI),
        ("ISK/H",   "isk_hr",    9,  CP),
        ("KILLS",   "kills",     5,  CG),
        ("SITES",   "sites_cleared", 5, C_ANOM),
        ("MSN",     "missions_done", 4, C_MSN),
    ]

    # Construit la fenêtre avec en-tête, stats globales et grille de données
    def __init__(self, parent, app, char_name=None):
        self.app = app
        self.char_name = char_name
        self.w = tk.Toplevel(parent)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", app.alpha)  # Dynamically use app opacity

        saved = app.cfg.get("history_pos")
        if saved:
            self.w.geometry(f"580x400{saved}")
        else:
            self.w.geometry(f"580x400+{parent.winfo_x() + 30}+{parent.winfo_y() + 40}")

        self._dx = self._dy = 0

        hdr = tk.Frame(self.w, bg=BG_H, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>", lambda e: (setattr(self, '_dx', e.x), setattr(self, '_dy', e.y)))
        hdr.bind("<B1-Motion>", lambda e: self.w.geometry(
            f"+{self.w.winfo_x() + e.x - self._dx}+{self.w.winfo_y() + e.y - self._dy}"))
        hdr.bind("<ButtonRelease-1>", lambda e: self._save_geo())

        tk.Frame(hdr, bg=CH, width=3).pack(side="left", fill="y")
        _title = f"  \u25C8 {char_name.upper()} HISTORY" if char_name else "  \u25C8 SESSION HISTORY"
        tk.Label(hdr, text=_title,
                 font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                 bg=BG_H, fg=CH).pack(side="left")

        xb = tk.Label(hdr, text="\u2715",
                      font=tkfont.Font(family="Consolas", size=12, weight="bold"),
                      bg=BG_H, fg=TD, padx=8, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self._close())
        xb.bind("<Enter>", lambda e: xb.config(fg=CR))
        xb.bind("<Leave>", lambda e: xb.config(fg=TD))

        tk.Frame(self.w, bg=BDG, height=1).pack(fill="x")

        hist = load_history()
        if char_name:
            hist = [e for e in hist if e.get("character", "").lower() == char_name.lower()]
        sumf = tk.Frame(self.w, bg=BG_P)
        sumf.pack(fill="x", padx=8, pady=6)
        F9   = tkfont.Font(family="Consolas", size=9)
        F11B = tkfont.Font(family="Consolas", size=11, weight="bold")

        total_isk   = sum(e.get("net_isk", 0)  for e in hist)
        total_kills = sum(e.get("kills", 0)    for e in hist)
        total_sites = sum(e.get("sites_cleared", 0) for e in hist)
        avg_isk     = int(sum(e.get("isk_hr", 0) for e in hist) / max(len(hist), 1))

        for lbl, val, c in [("SESSIONS", str(len(hist)), T0),
                              ("TOTAL NET", fisk(total_isk), CI),
                              ("KILLS", str(total_kills), CG),
                              ("SITES", str(total_sites), C_ANOM),
                              ("AVG ISK/H", fisk(avg_isk), CP)]:
            cf = tk.Frame(sumf, bg=BG_P)
            cf.pack(side="left", expand=True, fill="x")
            tk.Label(cf, text=lbl, font=F9, bg=BG_P, fg=TD).pack(anchor="w")
            tk.Label(cf, text=val, font=F11B, bg=BG_P, fg=c).pack(anchor="w")

        tk.Frame(self.w, bg=BD, height=1).pack(fill="x", padx=8)

        container = tk.Frame(self.w, bg=BG)
        container.pack(fill="both", expand=True, padx=4, pady=4)
        canvas    = tk.Canvas(container, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview,
                                  bg=BG_H, troughcolor=BG, activebackground=T1)
        self._sf  = tk.Frame(canvas, bg=BG)
        self._sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._canvas_win = canvas.create_window((0, 0), window=self._sf, anchor="nw")

        # Stretch inner frame to fill canvas width
        def _on_canvas_resize(e):
            canvas.itemconfig(self._canvas_win, width=e.width)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Safe scroll handler that checks if canvas still exists
        def _safe_scroll(e):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            except Exception:
                pass
        
        # Scope the global wheel hijack to when the cursor is actually over the
        # history list (matches FleetManager's Enter/Leave pattern), so opening
        # or closing History can't clobber other windows' scroll handling.
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _safe_scroll))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._canvas = canvas  # Store reference for cleanup

        F8  = tkfont.Font(family="Consolas", size=8)
        F9  = tkfont.Font(family="Consolas", size=9)
        F9B = tkfont.Font(family="Consolas", size=9, weight="bold")

        # ── Unified grid for header + data rows (proper alignment) ────
        # Configure columns with minimum sizes and weights for proportional fill
        COL_PX     = [112, 78, 48, 64, 64, 40, 40, 30]
        COL_WEIGHT = [  3,  2,  1,  2,  2,  1,  1,  1]
        for i, (px, wt) in enumerate(zip(COL_PX, COL_WEIGHT)):
            self._sf.grid_columnconfigure(i, minsize=px, weight=wt)

        # Header row
        grid_row = 0
        for i, (txt, key, wc, _) in enumerate(self.COLS):
            tk.Label(self._sf, text=txt, font=F8, bg=BG_H, fg=T1,
                     anchor="w", padx=3).grid(row=grid_row, column=i, sticky="ew")
        grid_row += 1

        # ── Data rows ─────────────────────────────────────────────────
        for entry in reversed(hist[-100:]):
            for i, (_, key, wc, c) in enumerate(self.COLS):
                raw = entry.get(key, "?")
                if key == "date":
                    txt = str(raw)[:16]
                elif key == "character":
                    txt = str(raw)[:12]
                elif key == "duration_s":
                    txt = fdur(raw)
                elif key in ("net_isk", "isk_hr"):
                    txt = fisk(raw)
                else:
                    txt = str(raw)
                tk.Label(self._sf, text=txt, font=F9, bg=BG_P, fg=c,
                         anchor="w", padx=3, pady=1).grid(
                    row=grid_row, column=i, sticky="ew")
            grid_row += 1

        if not hist:
            tk.Label(self._sf, text="  No sessions recorded yet. Start ratting!",
                     font=F9, bg=BG, fg=TD).grid(
                row=1, column=0, columnspan=len(self.COLS), sticky="w", pady=20)

        foot = tk.Frame(self.w, bg=BG)
        foot.pack(fill="x", padx=8, pady=6)
        clr = tk.Label(foot, text="\u2716 CLEAR HISTORY",
                       font=tkfont.Font(family="Consolas", size=9, weight="bold"),
                       bg=BG, fg=CS, cursor="hand2")
        clr.pack(side="right")
        clr.bind("<Button-1>", lambda e: self._clear_history())
        clr.bind("<Enter>", lambda e: clr.config(bg=BDG))
        clr.bind("<Leave>", lambda e: clr.config(bg=BG))

    # Sauvegarde la position de la fenêtre dans la config
    def _save_geo(self):
        try:
            self.app.cfg["history_pos"] = f"+{self.w.winfo_x()}+{self.w.winfo_y()}"
            save_config(self.app.cfg)
        except Exception:
            pass

    # Vide l'historique et ferme la fenêtre
    def _clear_history(self):
        if self.char_name:
            hist = load_history()
            hist = [e for e in hist if e.get("character", "").lower() != self.char_name.lower()]
            save_history(hist)
        else:
            save_history([])
        self._close()

    # Sauvegarde la position et ferme la fenêtre
    def _close(self):
        self._save_geo()
        # Unbind the global scroll handler to prevent errors after close
        try:
            if hasattr(self, '_canvas') and self._canvas:
                self._canvas.unbind_all("<MouseWheel>")
        except Exception:
            pass
        self.w.destroy()


# ── Settings window ──────────────────────────────────────────────────
# Fenêtre de paramètres (chemins, intervalle, opacité, taxe, thème)
class Settings:

    # Construit le formulaire de paramètres
    def __init__(self, parent, app):
        self.app = app
        self.w = tk.Toplevel(parent)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", app.alpha)  # Dynamically use app opacity

        saved = app.char_cfg.get("settings_pos")
        saved_geo = app.char_cfg.get("settings_geo")
        if saved_geo and saved:
            self.w.geometry(f"{saved_geo}{saved}")
        elif saved:
            self.w.geometry(f"340x340{saved}")
        else:
            self.w.geometry(f"340x340+{parent.winfo_x() + 30}+{parent.winfo_y() + 40}")

        self._dx = self._dy = 0

        hdr = tk.Frame(self.w, bg=BG_H, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>", lambda e: (setattr(self, '_dx', e.x), setattr(self, '_dy', e.y)))
        hdr.bind("<B1-Motion>", lambda e: self.w.geometry(
            f"+{self.w.winfo_x() + e.x - self._dx}+{self.w.winfo_y() + e.y - self._dy}"))
        hdr.bind("<ButtonRelease-1>", lambda e: self._save_geo())

        tk.Frame(hdr, bg=T0, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="  \u2699 SETTINGS",
                 font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                 bg=BG_H, fg=T0).pack(side="left")
        xb = tk.Label(hdr, text="\u2715",
                      font=tkfont.Font(family="Consolas", size=12, weight="bold"),
                      bg=BG_H, fg=TD, padx=8, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self._close())
        xb.bind("<Enter>", lambda e: xb.config(fg=CR))
        xb.bind("<Leave>", lambda e: xb.config(fg=TD))
        tk.Frame(self.w, bg=BDG, height=1).pack(fill="x")

        # Resize grip — pack BEFORE body so it claims bottom space
        btm = tk.Frame(self.w, bg=BG, height=14)
        btm.pack(fill="x", side="bottom")
        btm.pack_propagate(False)
        grip_f = tk.Frame(btm, bg=BDG, width=14, height=14, cursor="bottom_right_corner")
        grip_f.pack(side="right", padx=1, pady=1)
        grip_f.pack_propagate(False)
        grip_l = tk.Label(grip_f, text="\u2921", font=tkfont.Font(family="Consolas", size=9),
                          bg=BDG, fg=T1, cursor="bottom_right_corner")
        grip_l.pack(expand=True)
        for w in (grip_f, grip_l):
            w.bind("<Button-1>", self._resize_start)
            w.bind("<B1-Motion>", self._resize_drag)
            w.bind("<ButtonRelease-1>", self._resize_end)

        body = tk.Frame(self.w, bg=BG_POP)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        lf = tkfont.Font(family="Consolas", size=9)
        ek = dict(font=tkfont.Font(family="Consolas", size=10), bg=BG_C, fg=TB,
                  insertbackground=TB, relief="flat", bd=0,
                  highlightthickness=1, highlightbackground=BD, highlightcolor=BDG)

        tk.Label(body, text="GAMELOGS PATH", font=lf, bg=BG_POP, fg=TD).pack(anchor="w", pady=(0, 2))
        self.pv = tk.StringVar(value=app.log_path)
        tk.Entry(body, textvariable=self.pv, width=36, **ek).pack(fill="x", pady=(0, 4))

        tk.Label(body, text="CHATLOGS PATH", font=lf, bg=BG_POP, fg=TD).pack(anchor="w", pady=(0, 2))
        self.cpv = tk.StringVar(value=app.chat_path)
        tk.Entry(body, textvariable=self.cpv, width=36, **ek).pack(fill="x", pady=(0, 8))

        for lbl, attr, default in [("UPDATE INTERVAL (ms)", "iv", str(app.poll_ms)),
                                     ("OPACITY %",           "av", str(int(app.alpha * 100))),
                                     ("CORP TAX %",          "tv", app.tax_var.get()),
                                     ("SITE GAP (sec)",      "gv", str(app.anom_gap))]:
            r = tk.Frame(body, bg=BG_POP)
            r.pack(fill="x", pady=(0, 6))
            tk.Label(r, text=lbl, font=lf, bg=BG_POP, fg=TD).pack(side="left")
            sv = tk.StringVar(value=default)
            setattr(self, attr, sv)
            tk.Entry(r, textvariable=sv, width=8, **ek).pack(side="right")

        # Theme selector
        tk.Label(body, text="THEME", font=lf, bg=BG_POP, fg=TD).pack(anchor="w", pady=(0, 2))
        self._theme_var = tk.StringVar(value=app._current_theme)
        self._theme_cb = ttk.Combobox(body, textvariable=self._theme_var, state="readonly",
                                       style="E.TCombobox", font=tkfont.Font(family="Consolas", size=9),
                                       values=THEME_NAMES)
        self._theme_cb.pack(fill="x", pady=(0, 8))

        ap = tk.Label(body, text="\u2714 APPLY",
                      font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                      bg=BG_POP, fg=CA, cursor="hand2", padx=12)
        ap.pack(side="right", pady=(6, 0))
        ap.bind("<Button-1>", lambda e: self._apply())
        ap.bind("<Enter>", lambda e: ap.config(bg=BDG))
        ap.bind("<Leave>", lambda e: ap.config(bg=BG_POP))

    # Démarre le redimensionnement par glisser
    def _resize_start(self, e):
        self._rw = self.w.winfo_width()
        self._rh = self.w.winfo_height()
        self._rx = e.x_root
        self._ry = e.y_root
        self._wx = self.w.winfo_x()
        self._wy = self.w.winfo_y()

    # Applique le redimensionnement en cours de glisser
    def _resize_drag(self, e):
        nw = max(300, self._rw + (e.x_root - self._rx))
        nh = max(200, self._rh + (e.y_root - self._ry))
        self.w.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    # Termine le redimensionnement et sauvegarde
    def _resize_end(self, e): self._save_geo()

    # Sauvegarde la géométrie de la fenêtre
    def _save_geo(self):
        try:
            w = self.w.winfo_width()
            h = self.w.winfo_height()
            self.app.char_cfg["settings_geo"] = f"{w}x{h}"
            self.app.char_cfg["settings_pos"] = f"+{self.w.winfo_x()}+{self.w.winfo_y()}"
            save_config(self.app.cfg)
        except Exception:
            pass

    # Applique les paramètres modifiés et reconstruit l'UI si le thème change
    def _apply(self):
        a = self.app
        a.log_path = self.pv.get().strip()
        a.cfg["log_path"] = a.log_path
        a.chat_path = self.cpv.get().strip()
        a.cfg["chat_path"] = a.chat_path
        try:
            a.poll_ms = max(100, int(self.iv.get()))
            a.cfg["poll_ms"] = a.poll_ms
        except Exception:
            pass
        try:
            v = max(20, min(100, int(self.av.get())))
            a.alpha = v / 100
            a.cfg["alpha"] = a.alpha
            a.root.attributes("-alpha", a.alpha)
            
            # Apply opacity to any active detached windows
            if a._isk_window and a._isk_window.w.winfo_exists():
                a._isk_window.w.attributes("-alpha", a.alpha)
            if a._msn_window and a._msn_window.w.winfo_exists():
                a._msn_window.w.attributes("-alpha", a.alpha)
            if a._anom_window and a._anom_window.w.winfo_exists():
                a._anom_window.w.attributes("-alpha", a.alpha)
            if a._alert_window and a._alert_window.w.winfo_exists():
                a._alert_window.w.attributes("-alpha", a.alpha)
            
            # Apply opacity to History if it happens to be open
            if a._hw and a._hw.w.winfo_exists():
                a._hw.w.attributes("-alpha", a.alpha)
                
        except Exception:
            pass
        a.tax_var.set(self.tv.get())
        a.cfg["tax"] = self.tv.get()
        try:
            g = max(10, min(120, int(self.gv.get())))
            a.anom_gap = g
            a.cfg["anom_gap"] = g
        except Exception:
            pass

        new_theme = self._theme_var.get()
        theme_changed = (new_theme != a._current_theme)
        if theme_changed:
            a._current_theme = new_theme
            a.char_cfg["theme"] = new_theme

        save_config(a.cfg)

        if theme_changed:
            a._apply_theme_live()   # recolour in-place — no flicker, window stays open

    # Sauvegarde et ferme la fenêtre de paramètres
    def _close(self):
        self._save_geo()
        self.w.destroy()


# ── Detached panel window ────────────────────────────────────────────
# Fenêtre flottante détachable pour n'importe quelle section
class DetachedWindow:
    # Construit la fenêtre avec en-tête de glisser, grip de redimensionnement et contenu
    def __init__(self, parent, app, title, accent, section_key, build_fn, char_name: str = ""):
        self.app = app
        self.section_key = section_key
        self.w = tk.Toplevel(parent)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", app.alpha)

        pos_key = f"{section_key}_detach_pos"
        saved = app.char_cfg.get(pos_key)
        if saved:
            self.w.geometry(saved)
        else:
            self.w.geometry(f"+{parent.winfo_x() + 30}+{parent.winfo_y() + 60}")

        self._dx = self._dy = 0
        self._resizing = False
        self._rw = self._rh = 0

        # Header with drag + reattach (X)
        hdr = tk.Frame(self.w, bg=BG_H, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>", lambda e: (setattr(self, '_dx', e.x), setattr(self, '_dy', e.y)))
        hdr.bind("<B1-Motion>", lambda e: self.w.geometry(
            f"+{self.w.winfo_x() + e.x - self._dx}+{self.w.winfo_y() + e.y - self._dy}"))
        hdr.bind("<ButtonRelease-1>", lambda e: self._save_geometry())

        tk.Frame(hdr, bg=accent, width=3).pack(side="left", fill="y")
        _title_text = f"  {title}  —  {char_name.upper()}" if char_name else f"  {title}"
        lbl = tk.Label(hdr, text=_title_text,
                       font=tkfont.Font(family="Consolas", size=9, weight="bold"),
                       bg=BG_H, fg=accent)
        lbl.pack(side="left")
        lbl.bind("<Button-1>", lambda e: (setattr(self, '_dx', e.x_root - self.w.winfo_x()),
                                           setattr(self, '_dy', e.y_root - self.w.winfo_y())))
        lbl.bind("<B1-Motion>", lambda e: self.w.geometry(
            f"+{e.x_root - self._dx}+{e.y_root - self._dy}"))
        lbl.bind("<ButtonRelease-1>", lambda e: self._save_geometry())

        # X button = reattach (rightmost)
        xb = tk.Label(hdr, text="\u2715",
                      font=tkfont.Font(family="Consolas", size=11, weight="bold"),
                      bg=BG_H, fg=TD, padx=6, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self._reattach())
        xb.bind("<Enter>", lambda e: xb.config(fg=CR))
        xb.bind("<Leave>", lambda e: xb.config(fg=TD))
        Tooltip(xb, "Re-attach")

        tk.Frame(self.w, bg=BDG, height=1).pack(fill="x")

        # Bottom bar with resize grip — pack BEFORE body so it claims space
        btm = tk.Frame(self.w, bg=BG, height=14)
        btm.pack(fill="x", side="bottom")
        btm.pack_propagate(False)
        self._grip = tk.Frame(btm, bg=BDG, width=14, height=14, cursor="bottom_right_corner")
        self._grip.pack(side="right", padx=1, pady=1)
        self._grip.pack_propagate(False)
        tk.Label(self._grip, text="\u2921", font=tkfont.Font(family="Consolas", size=9),
                 bg=BDG, fg=T1, cursor="bottom_right_corner").pack(expand=True)
        self._grip.bind("<Button-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_drag)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)
        for child in self._grip.winfo_children():
            child.bind("<Button-1>", self._resize_start)
            child.bind("<B1-Motion>", self._resize_drag)
            child.bind("<ButtonRelease-1>", self._resize_end)

        # Build the section content
        self.body = tk.Frame(self.w, bg=BG)
        self.body.pack(fill="both", expand=True, padx=3, pady=3)
        build_fn(self.body, detached=True)

        # Fit to content
        self.w.update_idletasks()
        
        # Prevent layout locking by relying on content width instead of hardcoded minimums
        req_w = max(self.body.winfo_reqwidth() + 10, 60)
        req_h = self.body.winfo_reqheight() + 40
        
        if saved:
            geo_key = f"{section_key}_detach_geo"
            saved_geo = app.char_cfg.get(geo_key)
            if saved_geo:
                # Restaure la taille exacte sauvegardée + la position
                self.w.geometry(f"{saved_geo}{saved}")
            else:
                # Première ouverture : taille calculée depuis le contenu
                self.w.geometry(f"{req_w}x{req_h}{saved}")
        else:
            self.w.geometry(f"{req_w}x{req_h}")

    # Démarre le redimensionnement de la fenêtre flottante
    def _resize_start(self, e):
        self._resizing = True
        self._rw = self.w.winfo_width()
        self._rh = self.w.winfo_height()
        self._rx = e.x_root
        self._ry = e.y_root
        self._wx = self.w.winfo_x()
        self._wy = self.w.winfo_y()

    # Applique le redimensionnement en cours
    def _resize_drag(self, e):
        if not self._resizing: return
        # Limit to 60px minimum width to keep the drag header and close button accessible
        nw = max(60, self._rw + (e.x_root - self._rx))
        nh = max(40,  self._rh + (e.y_root - self._ry))
        self.w.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    # Termine le redimensionnement et sauvegarde
    def _resize_end(self, e):
        self._resizing = False
        self._save_geometry()

    # Sauvegarde la taille et position dans la config
    def _save_geometry(self):
        try:
            w = self.w.winfo_width()
            h = self.w.winfo_height()
            self.app.char_cfg[f"{self.section_key}_detach_geo"] = f"{w}x{h}"
            self.app.char_cfg[f"{self.section_key}_detach_pos"] = f"+{self.w.winfo_x()}+{self.w.winfo_y()}"
            save_config(self.app.cfg)
        except Exception:
            pass

    # Sauvegarde la géométrie et réattache la section à la fenêtre principale
    def _reattach(self):

        # Save position and size
        self._save_geometry()
        self.w.destroy()
        self.app._reattach(self.section_key)


# ── Standalone DPS overlay ───────────────────────────────────────────
# Overlay DPS autonome (indépendant du dashboard) : transparent, déplaçable,
# verrouillable en click-through, 3 vues (nombres / graphe / les deux).
class DPSOverlay:
    VIEW_NUMBERS, VIEW_GRAPH, VIEW_BOTH = 0, 1, 2
    _VIEW_COUNT = 3

    def __init__(self, main_ui, win):
        self.mu = main_ui
        self.win = win
        self.cfg = win.cfg
        self.char_cfg = win.char_cfg
        self.view = int(self.char_cfg.get("dps_overlay_view", self.VIEW_NUMBERS)) % self._VIEW_COUNT
        self.locked = False
        self._job = None
        self._dx = self._dy = 0
        self._rw = self._rh = self._rx = self._ry = self._wx = self._wy = 0
        self._scaling = False
        self._last_scale_h = 0
        self._out_lbl = self._in_lbl = self._graph = None

        self.w = tk.Toplevel(main_ui.root)
        self.w.overrideredirect(True)
        self.w.configure(bg=OVERLAY_KEY, highlightthickness=0)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", 1.0)   # crisp text; independent of global opacity
        try:
            # Color-key the background fully transparent (Windows). Only text /
            # graph lines show over EVE, like a message frame. Ignored off-Windows.
            self.w.attributes("-transparentcolor", OVERLAY_KEY)
        except Exception:
            pass

        saved_pos = self.char_cfg.get("dps_overlay_pos")
        saved_geo = self.char_cfg.get("dps_overlay_geo")
        if saved_geo and saved_pos:
            self.w.geometry(f"{saved_geo}{saved_pos}")
        elif saved_pos:
            self.w.geometry(f"230x96{saved_pos}")
        else:
            self.w.geometry(f"230x96+{main_ui.root.winfo_x()+60}+{main_ui.root.winfo_y()+60}")

        # Reusable fonts (rescaled on resize)
        self._num_font   = tkfont.Font(family="Consolas", size=22, weight="bold")
        self._title_font = tkfont.Font(family="Consolas", size=8,  weight="bold")

        self._build_chrome()
        self._build_view()
        self.w.after(120, self._finalize_scale)
        self._refresh()

        # Fresh overlay (no saved position) opens in MOVE mode so the owner can
        # place it; a restored one comes back placed (SET mode) as clean text.
        if saved_pos:
            self.locked = bool(self.char_cfg.get("dps_overlay_locked", True))
        else:
            self.locked = False
        self.w.update_idletasks()
        self._apply_mode()

    # ── Chrome: transparent body + move-mode contour / ✕ / grip (no header) ──
    def _build_chrome(self):
        self.body = tk.Frame(self.w, bg=OVERLAY_KEY)

        # ✕ = set position (exit move mode). Top-right, visible only while moving.
        self._xbtn = tk.Label(self.w, text="✕",
                              font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                              bg=OVERLAY_MOVE_BG, fg="#ffffff", cursor="hand2")
        self._xbtn.bind("<Button-1>", lambda e: self.toggle_lock(force=True))

        # Resize grip, bottom-right, visible only while moving.
        self._grip = tk.Label(self.w, text="⤡",
                              font=tkfont.Font(family="Consolas", size=9),
                              bg=OVERLAY_MOVE_BG, fg="#ffffff", cursor="bottom_right_corner")
        self._grip.bind("<Button-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_drag)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        # Drag the window by grabbing the body (guarded to move mode in _drag).
        self.body.bind("<Button-1>", self._drag_start)
        self.body.bind("<B1-Motion>", self._drag)
        self.body.bind("<ButtonRelease-1>", lambda e: self._save_geo())

        self.body.pack(fill="both", expand=True)
        self.body.bind("<Configure>", self._on_resize)

    def _build_view(self):
        for c in self.body.winfo_children():
            c.destroy()
        self._out_lbl = self._in_lbl = self._graph = None
        if self.view == self.VIEW_NUMBERS:
            self._build_numbers(self.body, inline=False)
        elif self.view == self.VIEW_GRAPH:
            self._graph = tk.Canvas(self.body, bg=OVERLAY_KEY, highlightthickness=0, bd=0)
            self._graph.pack(fill="both", expand=True, padx=3, pady=3)
        else:  # VIEW_BOTH
            top = tk.Frame(self.body, bg=OVERLAY_KEY)
            top.pack(fill="x", padx=3, pady=(3, 0))
            self._build_numbers(top, inline=True)
            self._graph = tk.Canvas(self.body, bg=OVERLAY_KEY, highlightthickness=0, bd=0)
            self._graph.pack(fill="both", expand=True, padx=3, pady=(2, 3))
        # New children must match the current mode's backdrop (keyed vs move).
        self._set_body_bg(OVERLAY_MOVE_BG if not self.locked else OVERLAY_KEY)

    def _build_numbers(self, parent, inline=False):
        def _bind_drag(*widgets):
            for _w in widgets:
                _w.bind("<Button-1>", self._drag_start)
                _w.bind("<B1-Motion>", self._drag)
                _w.bind("<ButtonRelease-1>", lambda e: self._save_geo())
        if inline:
            of = tk.Frame(parent, bg=OVERLAY_KEY); of.pack(side="left", expand=True, fill="x")
            t1 = tk.Label(of, text="▸ OUT", font=self._title_font, bg=OVERLAY_KEY, fg=CD, anchor="w")
            t1.pack(anchor="w")
            self._out_lbl = tk.Label(of, text="0", font=self._num_font, bg=OVERLAY_KEY, fg=CD, anchor="w")
            self._out_lbl.pack(anchor="w")
            inf = tk.Frame(parent, bg=OVERLAY_KEY); inf.pack(side="right", expand=True, fill="x")
            t2 = tk.Label(inf, text="IN ◂", font=self._title_font, bg=OVERLAY_KEY, fg=CR, anchor="e")
            t2.pack(anchor="e")
            self._in_lbl = tk.Label(inf, text="0", font=self._num_font, bg=OVERLAY_KEY, fg=CR, anchor="e")
            self._in_lbl.pack(anchor="e")
            _bind_drag(of, t1, self._out_lbl, inf, t2, self._in_lbl)
        else:
            orow = tk.Frame(parent, bg=OVERLAY_KEY); orow.pack(fill="x", padx=4, pady=(3, 0))
            t1 = tk.Label(orow, text="▸ OUT", font=self._title_font, bg=OVERLAY_KEY, fg=CD, anchor="w")
            t1.pack(side="left")
            self._out_lbl = tk.Label(orow, text="0", font=self._num_font, bg=OVERLAY_KEY, fg=CD, anchor="e")
            self._out_lbl.pack(side="right")
            irow = tk.Frame(parent, bg=OVERLAY_KEY); irow.pack(fill="x", padx=4, pady=(0, 3))
            t2 = tk.Label(irow, text="◂ IN", font=self._title_font, bg=OVERLAY_KEY, fg=CR, anchor="w")
            t2.pack(side="left")
            self._in_lbl = tk.Label(irow, text="0", font=self._num_font, bg=OVERLAY_KEY, fg=CR, anchor="e")
            self._in_lbl.pack(side="right")
            _bind_drag(orow, t1, self._out_lbl, irow, t2, self._in_lbl)

    def _refresh(self):
        try:
            d = self.win.data
            if self._out_lbl is not None:
                self._out_lbl.config(text=f"{d.dps(True):,.0f}")
            if self._in_lbl is not None:
                self._in_lbl.config(text=f"{d.dps(False):,.0f}")
            if self._graph is not None:
                self._redraw_graph()
        except Exception:
            pass
        try:
            self._job = self.w.after(getattr(self.win, "poll_ms", DEF_POLL), self._refresh)
        except Exception:
            self._job = None

    def _redraw_graph(self):
        try:
            if self._graph.winfo_exists() and self._graph.winfo_viewable():
                draw_dps_graph(self._graph, self.win.data.dps_hist, is_detached=True)
        except Exception:
            pass

    # ── Views ──
    def cycle_view(self):
        self.set_view((self.view + 1) % self._VIEW_COUNT)

    def set_view(self, i):
        self.view = i % self._VIEW_COUNT
        self.char_cfg["dps_overlay_view"] = self.view
        save_config(self.cfg)
        self._build_view()
        self._last_scale_h = 0
        self.w.after(30, self._apply_scale)

    # ── Resize scaling ──
    def _on_resize(self, event):
        if self._scaling:
            return
        h = event.height
        if abs(h - self._last_scale_h) < 8:
            return
        self._last_scale_h = h
        self._apply_scale(h)

    def _finalize_scale(self):
        try:
            if self.w.winfo_exists():
                self._last_scale_h = 0
                self._apply_scale()
        except Exception:
            pass

    def _apply_scale(self, h=None):
        if self._scaling:
            return
        self._scaling = True
        try:
            if h is None:
                h = self.body.winfo_height()
            if h < 8:
                return
            base = 60 if self.view == self.VIEW_BOTH else 44
            scale = max(0.5, min(3.0, h / base))
            self._num_font.configure(size=max(10, min(48, int(20 * scale))))
            self._title_font.configure(size=max(7, min(12, int(8 * scale))))
            if self._graph is not None:
                self._redraw_graph()
        finally:
            self._scaling = False

    # ── Set / move mode ──
    def toggle_lock(self, force=None):
        """locked=True → set mode (placed, pure text, click-through);
        locked=False → move mode (solid frame, white contour, ✕ + grip)."""
        self.locked = (not self.locked) if force is None else bool(force)
        self._apply_mode()
        self.char_cfg["dps_overlay_locked"] = self.locked
        save_config(self.cfg)
        try:
            self.mu._reflect_overlay_state(self.win.char_id)
        except Exception:
            pass

    def _set_body_bg(self, color):
        """Recolour body + all descendants (frames/labels/canvas) to `color`.
        Solid OVERLAY_MOVE_BG while moving (grabbable), OVERLAY_KEY when placed."""
        stack = [self.body]
        while stack:
            w = stack.pop()
            try:
                w.configure(bg=color)
            except Exception:
                pass
            stack.extend(w.winfo_children())

    def _apply_mode(self):
        """Apply the chrome for the current mode (self.locked)."""
        move = not self.locked
        # Solid movable frame while moving; keyed-transparent pure text once placed.
        self._set_body_bg(OVERLAY_MOVE_BG if move else OVERLAY_KEY)
        try:
            if move:
                self.w.configure(highlightthickness=2,
                                 highlightbackground="#ffffff", highlightcolor="#ffffff")
                self._xbtn.place(relx=1.0, x=-3, y=1, anchor="ne")
                self._grip.place(relx=1.0, rely=1.0, x=-2, y=-2, anchor="se")
            else:
                self.w.configure(highlightthickness=0)
                self._xbtn.place_forget()
                self._grip.place_forget()
        except Exception:
            pass
        # Windows click-through only in set mode (clicks pass to EVE over the text).
        if sys.platform == "win32":
            try:
                import ctypes
                GWL_EXSTYLE = -20
                WS_EX_LAYERED = 0x00080000
                WS_EX_TRANSPARENT = 0x00000020
                hwnd = ctypes.windll.user32.GetParent(self.w.winfo_id())
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if self.locked:
                    style = style | WS_EX_LAYERED | WS_EX_TRANSPARENT
                else:
                    style = style & ~WS_EX_TRANSPARENT
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            except Exception:
                pass

    # ── Drag / resize / geometry ──
    def _drag_start(self, e):
        if self.locked:
            return
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        if self.locked:
            return
        self.w.geometry(f"+{self.w.winfo_x()+e.x-self._dx}+{self.w.winfo_y()+e.y-self._dy}")

    def _resize_start(self, e):
        self._rw = self.w.winfo_width(); self._rh = self.w.winfo_height()
        self._rx = e.x_root; self._ry = e.y_root
        self._wx = self.w.winfo_x(); self._wy = self.w.winfo_y()

    def _resize_drag(self, e):
        nw = max(120, self._rw + (e.x_root - self._rx))
        nh = max(60,  self._rh + (e.y_root - self._ry))
        self.w.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    def _resize_end(self, e):
        self._save_geo()

    def _save_geo(self):
        try:
            self.char_cfg["dps_overlay_geo"] = f"{self.w.winfo_width()}x{self.w.winfo_height()}"
            self.char_cfg["dps_overlay_pos"] = f"+{self.w.winfo_x()}+{self.w.winfo_y()}"
            save_config(self.cfg)
        except Exception:
            pass

    def apply_alpha(self, a):
        # Overlay transparency is the color-key (background), independent of the
        # global opacity slider. Intentionally a no-op so the slider never fades it.
        return

    def close(self):
        if self._job:
            try: self.w.after_cancel(self._job)
            except Exception: pass
            self._job = None
        self._save_geo()
        self.char_cfg["dps_overlay_open"] = False
        save_config(self.cfg)
        try:
            self.w.destroy()
        except Exception:
            pass
        try:
            self.mu._on_overlay_closed(self.win.char_id)
        except Exception:
            pass


# ── Main app ─────────────────────────────────────────────────────────
# Application principale du dashboard de ratting EVE Online
class CharacterWindow:

    # Initialise la config, les données, l'UI et démarre les boucles de poll/tick
    def __init__(self, root_tk, main_ui, char_id: str, char_name: str, log_file: str, cfg: dict):
        top = tk.Toplevel(root_tk)
        top.withdraw()           # stay hidden until MainUI explicitly shows it (prevents flash)
        top.overrideredirect(True)
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        self.root = top          # keep self.root; all existing refs work unchanged

        self.char_id   = char_id
        self.char_name = char_name
        self._main_ui  = main_ui
        self.cfg       = cfg
        self.char_cfg  = cfg.setdefault("chars", {}).setdefault(char_id, {})
        self.log_path  = cfg.get("log_path", DEF_PATH)
        self.chat_path = self.cfg.get("chat_path", DEF_CHAT)
        self.poll_ms  = self.cfg.get("poll_ms",  DEF_POLL)
        self.alpha    = self.cfg.get("alpha",    DEF_ALPHA)
        self.anom_gap = self.cfg.get("anom_gap", ANOM_GAP)
        self.root.attributes("-alpha", self.alpha)

        self.data   = Data()
        self._dx = self._dy = 0
        self._st  = "stopped"
        self._main_hidden = False
        self._is_collapsed = False  # Track window collapse state (double-click title)
        self._full_height = 0       # Store height before collapse
        self._main_frame = None     # Reference to body frame for collapse
        self._dragging = False      # Distinguish drag vs double-click on titlebar
        self._overlay_active = False  # True while a DPS overlay is open → don't suspend parsing
        self.cf = log_file if log_file else None
        self.fh = None
        self.fp = 0
        self._last_gamelog_scan = 0.0   # monotonic ts of last gamelog-rotation scan
        self._sw  = None
        self._hw = None
        self._calc_dots = 0
        self._poll_job = None        # after() id for the log-polling loop
        self._tick_job = None        # after() id for the UI-refresh loop
        self._alert_font_cache = {}  # size -> tkfont.Font, reused across redraws

        self._chat_file = None
        self._chat_fh = None
        self._chat_fp = 0

        # Clipboard tracker state
        self._last_clipboard  = ""
        self._global_prices   = {}
        self._jita_price_cache = {}     # Session cache for Jita lookups
        self._name_to_id_cache = self._load_nameid_cache()

        # Loot loading indicator state
        self._loot_loading    = False
        self._loot_inflight   = False   # one loot lookup at a time per window
        self._loot_anim_job   = None
        self._loot_anim_step  = 0

        # ── Load or Download Market Prices (24h disk cache) ──
        threading.Thread(target=self._download_market_data, daemon=True).start()

        self._storyline_ctr = self.char_cfg.get("storyline_counter", 0)
        self.tax_var = tk.StringVar(value=self.cfg.get("tax", str(DEF_TAX)))

        self._frozen = None
        self._last_tick_wall: float = time.monotonic()
        self._session_saved = False
        self._anom_paused_secs = 0
        self._anom_last_wall   = 0.0  # time.monotonic() of last combat event (timezone-immune gap detection)
        self._anom_start_wall  = 0.0  # time.monotonic() when current anomaly started
        self._btn_sets = []

        self._isk_detached = False
        self._isk_window = None
        self._msn_detached = False
        self._msn_window = None
        self._anom_detached = False
        self._anom_window = None
        self._alert_detached = False
        self._alert_window = None
        self._isk_det_labels = {}
        self._msn_det_labels = {}
        self._anom_det_labels = {}

        # Section enabled states (ON/OFF) — per character, falling back to any
        # legacy global value so existing configs migrate without surprises.
        self._isk_enabled  = self.char_cfg.get("isk_enabled",  self.cfg.get("isk_enabled",  True))
        self._msn_enabled  = self.char_cfg.get("msn_enabled",  self.cfg.get("msn_enabled",  True))
        self._anom_enabled = self.char_cfg.get("anom_enabled", self.cfg.get("anom_enabled", False))

        # Enforce mutual exclusivity: if both ON, keep MSN, disable ANOM
        if self._msn_enabled and self._anom_enabled:
            self._anom_enabled = False
            self.char_cfg["anom_enabled"] = False

        # Section collapsed states (per character, legacy-global fallback)
        self._isk_collapsed   = self.char_cfg.get("isk_collapsed",   self.cfg.get("isk_collapsed",   False))
        self._msn_collapsed   = self.char_cfg.get("msn_collapsed",   self.cfg.get("msn_collapsed",   False))
        self._anom_collapsed  = self.char_cfg.get("anom_collapsed",  self.cfg.get("anom_collapsed",  False))
        self._alert_collapsed = self.char_cfg.get("alert_collapsed", self.cfg.get("alert_collapsed", False))
        self._brk_collapsed   = self.char_cfg.get("brk_collapsed",   self.cfg.get("brk_collapsed",   False))

        self._current_theme = self.char_cfg.get("theme", THEME_DEFAULT)
        apply_theme_colors(self._current_theme)

        # OPTIMIZATION STATE
        self._last_values = {}

        self._style()
        self._build()

        self.root.update_idletasks()
        # ── FULL GEOMETRY RESTORE (size + position) ──
        saved_geom = self.char_cfg.get("geometry", "")
        if saved_geom and "+" in saved_geom:
            self.root.geometry(saved_geom)
        else:
            self._center()

        self.root.config(highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self._fit()

        # Restore collapsed state if window was closed while collapsed.
        # winfo_* returns garbage while withdrawn — parse the geometry string instead.
        full_h = self.char_cfg.get("main_full_height", 0)
        if self.char_cfg.get("main_collapsed", False) and full_h > 32:
            self._full_height = full_h
            self._main_frame.pack_forget()
            if hasattr(self, "_grip_bar"):
                self._grip_bar.pack_forget()
            self._hdr_b_go.pack(side="left", fill="y")
            self._hdr_b_pa.pack(side="left", fill="y")
            self._hdr_b_st.pack(side="left", fill="y")
            saved = self.char_cfg.get("geometry", "")
            m = re.match(r"(\d+)x\d+([+-]\d+[+-]\d+)", saved)
            if m:
                self.root.geometry(f"{m.group(1)}x32{m.group(2)}")
            self._is_collapsed = True

        self._poll()
        self._tick()

        if self.char_cfg.get("isk_detached", False):
            self._detach("isk")
        if self.char_cfg.get("msn_detached", False):
            self._detach("msn")
        if self.char_cfg.get("anom_detached", False):
            self._detach("anom")
        if self.char_cfg.get("alert_detached", False):
            self._detach("alert")
        self._start_minimized = self.char_cfg.get("main_minimized", False)

    # ── Name-to-ID disk cache ────────────────────────────────────────
    # Charge le cache nom→type_id depuis le disque
    def _load_nameid_cache(self):
        if os.path.exists(NAMEID_CACHE):
            try:
                with open(NAMEID_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    # Sauvegarde le cache nom→type_id sur le disque
    def _save_nameid_cache(self):
        # Multiple loot threads (and multiple CharacterWindows) share one file.
        # Merge under a lock so concurrent writers don't clobber each other's IDs,
        # then write atomically so a reader never sees a half-written file.
        with _NAMEID_LOCK:
            merged = {}
            if os.path.exists(NAMEID_CACHE):
                try:
                    with open(NAMEID_CACHE, "r", encoding="utf-8") as f:
                        merged = json.load(f)
                except Exception:
                    merged = {}
            merged.update(self._name_to_id_cache)
            self._name_to_id_cache = merged   # adopt IDs other windows resolved
            try:
                tmp = NAMEID_CACHE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False)
                os.replace(tmp, NAMEID_CACHE)
            except Exception:
                pass

    # ── Market data download (24h cache) ─────────────────────────────
    # Télécharge les prix ESI (cache 24h sur disque)
    def _download_market_data(self):
        # Serialize across all CharacterWindows: only one thread fetches ESI and
        # writes the shared cache; the others block, then load the file it wrote.
        # This removes both the redundant N× downloads and the concurrent-write
        # race that could corrupt ratting_prices.json.
        with _PRICE_LOCK:
            # Use disk cache if less than 24h old
            if os.path.exists(PRICE_CACHE):
                try:
                    age_hrs = (time.time() - os.path.getmtime(PRICE_CACHE)) / 3600
                    if age_hrs < 24:
                        with open(PRICE_CACHE, "r", encoding="utf-8") as f:
                            self._global_prices = json.load(f)
                        return
                except Exception:
                    pass

            # Download fresh from ESI
            try:
                req = urllib.request.Request(
                    "https://esi.evetech.net/latest/markets/prices/?datasource=tranquility",
                    headers={"User-Agent": _ESI_UA})
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode())
                    self._global_prices = {
                        str(item['type_id']): item.get('average_price', item.get('adjusted_price', 0))
                        for item in data
                    }

                # Write atomically (temp file + os.replace) so a concurrent or
                # next-launch reader never sees a half-written cache file.
                tmp = PRICE_CACHE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._global_prices, f)
                os.replace(tmp, PRICE_CACHE)
            except Exception:
                pass

    # ── Loot clipboard parsing ───────────────────────────────────────
    # Vérifie si le presse-papiers contient un inventaire EVE à parser
    def _check_clipboard(self):
        if not _CLIP_OK or self._st not in ("running", "paused"): return
        try:
            content = pyperclip.paste()
            if not content or "\t" not in content:
                return
            # Use shared clipboard tracker when running under MainUI so only one
            # CharacterWindow processes each paste even with multiple chars active.
            tracker = self._main_ui if self._main_ui else self
            if content == tracker._last_clipboard:
                return
            # One loot lookup at a time per window: if one is already running,
            # leave _last_clipboard untouched so this paste is retried on a later
            # poll once the in-flight lookup finishes (no concurrent threads,
            # no spinner-state interleave).
            if self._loot_inflight:
                return
            tracker._last_clipboard = content
            self._loot_inflight = True
            self._loot_anim_start()
            threading.Thread(target=self._process_loot_copy, args=(content,), daemon=True).start()
        except Exception:
            pass

    # Parse le texte du presse-papiers et calcule la valeur du loot
    def _process_loot_copy(self, text):
        lines = text.strip().split('\n')
        total_session_loot = 0
        parsed_items = []
        names_to_resolve = set()
        
        for line in lines:
            parts = line.split('\t')
            if len(parts) >= 1:
                name = parts[0].strip()
                if not name: continue
                qty = 1
                if len(parts) >= 2:
                    # Reuse pnum(): it strips spaces/commas/dots so locale
                    # thousands separators ("1 000", "1,000", "1.000") all
                    # parse correctly. Blank/non-numeric → 0 → fall back to 1.
                    qty = pnum(parts[1]) or 1
                
                parsed_items.append({"name": name, "qty": qty})
                if name not in self._name_to_id_cache:
                    names_to_resolve.add(name)

        # Resolve newly copied Item Names to Type IDs in bulk via ESI
        if names_to_resolve:
            names_list = list(names_to_resolve)
            for i in range(0, len(names_list), 500):
                chunk = names_list[i:i+500]
                try:
                    data = json.dumps(chunk).encode('utf-8')
                    req = urllib.request.Request("https://esi.evetech.net/latest/universe/ids/", data=data, 
                                                 headers={'Content-Type': 'application/json', 'Accept-Language': 'en',
                                                          'User-Agent': _ESI_UA})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        res = json.loads(response.read().decode())
                        for item in res.get('inventory_types', []):
                            self._name_to_id_cache[item['name']] = item['id']
                except Exception:
                    pass
            self._save_nameid_cache()
        
        # Price calc: Jita for faction items, global avg for everything else
        for item in parsed_items:
            name = item["name"]
            qty = item["qty"]
            type_id = self._name_to_id_cache.get(name)
            
            price = 0
            if type_id:
                if RE_FACTION_ITEM.search(name):
                    price = self._get_live_esi_price(type_id)
                else:
                    price = self._global_prices.get(str(type_id), 0)
            
            # Offline Fallback if ESI entirely fails
            if price == 0:
                price = self._get_avg_loot_price_fallback(name)
                
            total_session_loot += (price * qty)
        
        now_str = datetime.now().strftime("%H:%M:%S")
        # Marshal the result back to the main thread. Guard against the window
        # being closed mid-lookup (self.root destroyed → after() would raise
        # TclError in this daemon thread).
        try:
            if total_session_loot > 0:
                self.root.after(0, lambda amt=total_session_loot, ts=now_str: self._apply_loot(amt, ts))
            else:
                # Nothing valued — stop spinner without flashing green
                self.root.after(0, lambda: self._loot_anim_stop(False))
        except Exception:
            pass

    # Bip d'alerte EWAR — Windows uniquement, joué hors du thread UI (non bloquant).
    def _ewar_sound(self):
        if not _SND_OK:
            return
        def _beep():
            try:
                winsound.Beep(1200, 130)
                winsound.Beep(1650, 160)
            except Exception:
                pass
        try:
            threading.Thread(target=_beep, daemon=True).start()
        except Exception:
            pass

    # Pulse visuel sur le cadre d'alerte (pour les événements EWAR)
    def _flash_alert(self):
        self._ewar_sound()

        # Quick pulse flash on the alert frame for EWAR
        def _pulse(step=0):
            if step < 3:

                # Alternate between highlight and normal
                bg = BDG if step % 2 == 0 else BG_P
                try:
                    self._alert_frame.config(bg=bg)
                    for w in self._alert_frame.winfo_children():
                        w.config(bg=bg)
                        for c in w.winfo_children():
                            c.config(bg=bg)
                except Exception:
                    pass
                try:
                    self.root.after(150, lambda: _pulse(step + 1))
                except Exception:
                    pass   # root torn down mid-flash — stop the pulse chain
            else:

                # Reset to normal
                try:
                    self._alert_frame.config(bg=BG_P)
                    for w in self._alert_frame.winfo_children():
                        w.config(bg=BG_P)
                        for c in w.winfo_children():
                            c.config(bg=BG_P)
                except Exception:
                    pass
        _pulse()

    # Applique la valeur de loot calculée aux données de session (thread principal)
    def _apply_loot(self, amount, now_str):

        # Stop spinner and flash green to confirm the find
        self._loot_anim_stop(True)

        # Main thread — safe to update data + UI
        self.data.loot_val += amount
        self._add_loot_alert(now_str, amount)

    # Récupère le prix Jita minimum depuis ESI (cache session par item)
    def _get_live_esi_price(self, type_id):

        # Session cache — one Jita lookup per item max
        if type_id in self._jita_price_cache:
            return self._jita_price_cache[type_id]
        try:
            time.sleep(0.5)  # Throttle: max ~2 requests/sec to ESI
            url = f"https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell&type_id={type_id}"
            req = urllib.request.Request(url, headers={"User-Agent": _ESI_UA})
            with urllib.request.urlopen(req, timeout=5) as response:
                orders = json.loads(response.read().decode())
                if orders:
                    price = min(order['price'] for order in orders)
                    self._jita_price_cache[type_id] = price
                    return price
        except Exception:
            pass
        fallback = self._global_prices.get(str(type_id), 0)
        self._jita_price_cache[type_id] = fallback
        return fallback

    # Retourne un prix de fallback hors-ligne par nom d'item
    def _get_avg_loot_price_fallback(self, name):

        # Offline price fallback if API fails
        name_lower = name.lower()
        if any(x in name_lower for x in ["missile", "rocket", "torpedo", "lead", "uranium", "emp", "fusion", "nuclear", "plasma", "proton", "sabot", "sequencer"]):
            return 100
        if "metal scraps" in name_lower: return 10000
        if any(x in name_lower for x in ["vespa", "berserker", "infiltrator", "acolyte"]):
            return 50000
        if any(x in name_lower for x in ["circuit", "plate", "compound", "console", "nanite"]):
            return 150000
        if "tag" in name_lower: return 1000000
        return 200000

    # Ajoute une alerte de loot au feed d'alertes
    def _add_loot_alert(self, now_str, amount):

        # Add loot alert to the feed
        self.data.alerts.append((now_str, "LOOT", f"Added {fisk(amount)} loot"))
        # Refresh alert display
        self._update_alert_labels()

    # ── Loot loading animation (main thread only) ─────────────────────

    def _loot_anim_start(self):
        """Begin spinning 'Searching…' on the LOOT ESTIMATE label."""
        self._loot_loading   = True
        self._loot_anim_step = 0
        if self._loot_anim_job:
            self.root.after_cancel(self._loot_anim_job)
            self._loot_anim_job = None
        self._loot_anim_tick()

    def _loot_anim_tick(self):
        """Advance one spinner frame (reschedules itself while loading)."""
        if not self._loot_loading:
            return
        try:
            spin = _LOOT_SPIN[self._loot_anim_step % len(_LOOT_SPIN)]
            self.ll.config(text=f"{spin} Searching...", fg=CW)
        except Exception:
            pass
        self._loot_anim_step += 1
        self._loot_anim_job = self.root.after(120, self._loot_anim_tick)

    def _loot_anim_stop(self, found):
        """Stop the spinner.  If found=True, flash bright green then restore."""
        self._loot_loading = False
        self._loot_inflight = False   # release the guard so the next paste can process
        if self._loot_anim_job:
            self.root.after_cancel(self._loot_anim_job)
            self._loot_anim_job = None
        if found:
            try:
                self.ll.config(fg="#39FF14")   # bright-green confirmation flash
            except Exception:
                pass
            self.root.after(500, lambda: self._loot_label_restore_fg())
        else:
            self._loot_label_restore_fg()

    def _loot_label_restore_fg(self):
        """Restore the loot label to its normal colour."""
        try:
            self.ll.config(fg=CI)
        except Exception:
            pass

    # ── Resize main window to fit content ────────────────────────────
    # Redimensionne la fenêtre principale pour s'adapter au contenu
    def _fit(self):
        self.root.update_idletasks()
        self.root.update_idletasks()  # second pass needed on Linux/X11 for nested frame heights
        # +32 header. Also add the bottom status bar's height, otherwise the
        # resize grip gets clipped off the bottom edge of the window.
        h = self._body.winfo_reqheight() + 32
        if getattr(self, "_grip_bar", None) is not None:
            h += 16   # status bar / resize grip

        # While collapsed the body is hidden and the window is pinned at 32px.
        # Resizing it to the (still full) content height would leave blank space
        # under the title bar — the exact glitch seen when a detached panel is
        # re-attached while collapsed. Instead, just remember the new full height
        # so the next expand restores the correct size (incl. the re-attached
        # section), then leave the collapsed window untouched.
        if self._is_collapsed:
            self._full_height = h
            self.char_cfg["main_full_height"] = h
            return

        saved = self.char_cfg.get("geometry", "")
        if saved:
            saved_w = saved.split("x")[0] if "x" in saved else str(WIN_W)
            # re.sub replaces only the WxH size portion, preserving ±X±Y as-is
            new_geom = re.sub(r"^\d+x\d+", f"{saved_w}x{h}", saved)
            self.root.geometry(new_geom)
        else:
            self.root.geometry(f"{WIN_W}x{h}")
            self._center()

    # Centre la fenêtre sur le bord droit de l'écran
    def _center(self):
        self.root.update_idletasks()
        x = self.root.winfo_screenwidth()  - WIN_W - 20
        y = (self.root.winfo_screenheight() - self.root.winfo_height()) // 2
        self.root.geometry(f"+{x}+{y}")

    # Mémorise la position de début de glisser
    def _sd(self, e):
        self._dx, self._dy = e.x, e.y
        self._dragging = False

    # Déplace la fenêtre principale pendant le glisser
    def _dd(self, e):
        self._dragging = True
        self.root.geometry(
            f"+{self.root.winfo_x()+e.x-self._dx}+{self.root.winfo_y()+e.y-self._dy}")

    # Finalise le glisser et sauvegarde la position
    def _dd_end(self, e):
        self._save_pos()
        # Reset dragging flag after short delay so double-click guard works correctly
        self.root.after(100, lambda: setattr(self, '_dragging', False))

    # Collapse/déplie la fenêtre sur double-clic de la barre de titre
    def _toggle_window_collapse(self, event):
        # Don't collapse if we were just dragging
        if getattr(self, '_dragging', False):
            return
        # Cooldown to prevent rapid double-clicks triggering multiple toggles
        current_time = time.time()
        if hasattr(self, '_last_toggle_time'):
            if current_time - self._last_toggle_time < 0.5:
                return
        self._last_toggle_time = current_time

        if not self._main_frame:
            return

        if self._is_collapsed:
            # Expand — restore content, hide mini controls, re-pack grip
            for mb in (self._hdr_b_go, self._hdr_b_pa, self._hdr_b_st):
                mb.pack_forget()
            self._main_frame.pack(fill="x", padx=3, pady=(0, 3))
            if hasattr(self, "_grip_bar"):
                self._grip_bar.pack_forget()
                self._grip_bar.pack(fill="x", side="bottom")
            if self._full_height > 0:
                w = self.root.winfo_width()
                x, y = self.root.winfo_x(), self.root.winfo_y()
                self.root.geometry(f"{w}x{self._full_height}+{x}+{y}")
            self._is_collapsed = False
            self.char_cfg["main_collapsed"] = False
            save_config(self.cfg)
        else:
            # Collapse — hide content, show mini controls in title bar
            self._full_height = self.root.winfo_height()
            self._main_frame.pack_forget()
            if hasattr(self, "_grip_bar"):
                self._grip_bar.pack_forget()
            self._hdr_b_go.pack(side="left", fill="y")
            self._hdr_b_pa.pack(side="left", fill="y")
            self._hdr_b_st.pack(side="left", fill="y")
            self.root.update_idletasks()
            w = self.root.winfo_width()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x32+{x}+{y}")
            self._is_collapsed = True
            self.char_cfg["main_collapsed"] = True
            self.char_cfg["main_full_height"] = self._full_height
            save_config(self.cfg)

    # Sauvegarde la géométrie complète de la fenêtre principale
    def _save_pos(self):
        try:
            self.char_cfg["geometry"] = self.root.winfo_geometry()
            if not self._is_collapsed:
                h = self.root.winfo_height()
                if h > 32:
                    self.char_cfg["main_full_height"] = h
            save_config(self.cfg)
        except Exception:
            pass

    def _resize_start(self, e):
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()
        self._rx = e.x_root
        self._ry = e.y_root
        self._wx = self.root.winfo_x()
        self._wy = self.root.winfo_y()

    def _resize_drag(self, e):
        nw = max(220, self._rw + (e.x_root - self._rx))
        nh = max(100, self._rh + (e.y_root - self._ry))
        self.root.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    def _resize_end(self, e):
        self._save_pos()

    # Configure le style TTK (combobox thème EVE)
    def _style(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("E.TCombobox",
                    fieldbackground=BG_C, background=BG_H, foreground=TB,
                    bordercolor=BD, arrowcolor=T1,
                    selectbackground=BG_H, selectforeground=T0)
        s.map("E.TCombobox",
              fieldbackground=[("readonly", BG_C)],
              foreground=[("readonly", TB)],
              bordercolor=[("focus", BDG)])

    # Construit l'interface principale (en-tête, contrôles, sections)
    def _build(self):
        hdr = tk.Frame(self.root, bg=BG_H, height=30)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        for w in (hdr,):
            w.bind("<Button-1>",        self._sd)
            w.bind("<B1-Motion>",       self._dd)
            w.bind("<ButtonRelease-1>", self._dd_end)
            w.bind("<Double-Button-1>", self._toggle_window_collapse)

        tk.Frame(hdr, bg=T0, width=3).pack(side="left", fill="y")
        _n = self.char_name.upper()
        _n = _n[:17] + "..." if len(_n) > 18 else _n
        title = tk.Label(hdr, text=f"  \u25C6 {_n}",
                         font=tkfont.Font(family="Consolas", size=11, weight="bold"),
                         bg=BG_H, fg=T0)
        title.pack(side="left")
        for w in (title,):
            w.bind("<Button-1>",        self._sd)
            w.bind("<B1-Motion>",       self._dd)
            w.bind("<ButtonRelease-1>", self._dd_end)
            w.bind("<Double-Button-1>", self._toggle_window_collapse)

        btn_fg = TD
        BF = tkfont.Font(family="Consolas", size=12, weight="bold")

        xb = tk.Label(hdr, text="\u2715", font=BF, bg=BG_H, fg=btn_fg, padx=5, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Enter>", lambda e: xb.config(fg=CR))
        xb.bind("<Leave>", lambda e: xb.config(fg=btn_fg))
        xb.bind("<Button-1>", lambda e: self._main_ui._toggle_window(self.char_id) if self._main_ui else self._quit())
        Tooltip(xb, "Hide")

        hb = tk.Label(hdr, text="\u2630",
                      font=tkfont.Font(family="Consolas", size=11),
                      bg=BG_H, fg=btn_fg, padx=4, cursor="hand2")
        hb.pack(side="right", fill="y")
        hb.bind("<Button-1>", lambda e: self._show_history())
        hb.bind("<Enter>", lambda e: hb.config(fg=TB))
        hb.bind("<Leave>", lambda e: hb.config(fg=btn_fg))
        Tooltip(hb, "History")

        # Mini controls \u2014 visible only when window is collapsed
        MF  = tkfont.Font(family="Consolas", size=10, weight="bold")
        MF7 = tkfont.Font(family="Consolas", size=7,  weight="bold")
        self._hdr_b_go = tk.Label(hdr, text="\u25b6",       fg=CA, font=MF,  bg=BG_H, padx=4, cursor="hand2")
        self._hdr_b_go.bind("<Button-1>", lambda e: self._go())
        Tooltip(self._hdr_b_go, "Start")
        self._hdr_b_pa = tk.Label(hdr, text="\u258c\u258c", fg=TD, font=MF7, bg=BG_H, padx=3, cursor="hand2")
        self._hdr_b_pa.bind("<Button-1>", lambda e: self._pause())
        Tooltip(self._hdr_b_pa, "Pause")
        self._hdr_b_st = tk.Label(hdr, text="\u25a0",       fg=TD, font=MF,  bg=BG_H, padx=4, cursor="hand2")
        self._hdr_b_st.bind("<Button-1>", lambda e: self._stop())
        Tooltip(self._hdr_b_st, "Stop")
        # Register as a btn_set so _update_buttons keeps them in sync
        self._hdr_btn_set = {"go": self._hdr_b_go, "pa": self._hdr_b_pa, "st": self._hdr_b_st}
        self._btn_sets.append(self._hdr_btn_set)
        # Don't pack yet \u2014 shown only when collapsed

        # Every child of the title bar is also a drag handle (append \u2014 existing bindings still fire)
        for _w in hdr.winfo_children():
            _w.bind("<Button-1>",        self._sd,    "+")
            _w.bind("<B1-Motion>",       self._dd,    "+")
            _w.bind("<ButtonRelease-1>", self._dd_end, "+")

        tk.Frame(self.root, bg=BDG, height=1).pack(fill="x")

        self._body = tk.Frame(self.root, bg=BG)
        self._body.pack(fill="x", padx=3, pady=(0, 3))
        self._body.grid_columnconfigure(0, weight=1)
        self._main_frame = self._body  # For collapse on titlebar double-click

        self._ctrl_frame = tk.Frame(self._body, bg=BG)
        self._ctrl_frame.grid(row=0, column=0, sticky="ew")
        self._build_controls(self._ctrl_frame)

        # Alerts section (right under controls)
        self._alert_container = tk.Frame(self._body, bg=BG)
        self._alert_container.grid(row=1, column=0, sticky="ew")
        self._build_alerts(self._alert_container)

        self._sep_alert_isk = tk.Frame(self._body, bg=BD, height=1)
        self._sep_alert_isk.grid(row=2, column=0, sticky="ew", padx=4)

        self._isk_container = tk.Frame(self._body, bg=BG)
        self._isk_container.grid(row=3, column=0, sticky="ew")
        self._build_isk(self._isk_container, detached=False)

        self._sep_isk_msn = tk.Frame(self._body, bg=BD, height=1)
        self._sep_isk_msn.grid(row=4, column=0, sticky="ew", padx=4)

        self._msn_container = tk.Frame(self._body, bg=BG)
        self._msn_container.grid(row=5, column=0, sticky="ew")
        self._build_missions(self._msn_container)

        self._sep_msn_anom = tk.Frame(self._body, bg=BD, height=1)
        self._sep_msn_anom.grid(row=6, column=0, sticky="ew", padx=4)

        self._anom_container = tk.Frame(self._body, bg=BG)
        self._anom_container.grid(row=7, column=0, sticky="ew")
        self._build_anomalies(self._anom_container)

        # DPS MONITOR section removed — DPS now lives in the standalone overlay.
        # The bottom of the dashboard is a minimal status bar: just the resize grip.

        # ── Status bar (bottom): a slim visible bar with a decorative grip. ──
        # Panel-coloured so it reads as a bar against the darker content area.
        # The character window auto-fits its content and is NOT user-resizable;
        # the grip glyph is kept purely for visual consistency with the Overview
        # (no drag-to-resize bindings, and no resize cursor).
        self._grip_bar = tk.Frame(self.root, bg=BG_P, height=16)
        self._grip_bar.pack(fill="x", side="bottom")
        self._grip_bar.pack_propagate(False)
        grip_bar = self._grip_bar
        grip_l = tk.Label(grip_bar, text="⤡",
                          font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                          bg=BG_P, fg=T1)
        grip_l.pack(side="right", padx=4)

    # Construit la barre de contrôle (Play/Pause/Stop/Reset + combobox de personnage)
    def _build_controls(self, parent):
        pad = dict(padx=6, pady=2)
        F12 = tkfont.Font(family="Consolas", size=12, weight="bold")
        F8  = tkfont.Font(family="Consolas", size=8)
        F10 = tkfont.Font(family="Consolas", size=10, weight="bold")

        self._sec(parent, "CONTROLS", T0)
        ctrl_wrap = tk.Frame(parent, bg=BG_P)
        ctrl_wrap.pack(fill="x", **pad)
        bk = dict(bg=BG_P, cursor="hand2", bd=0, padx=6)

        self._b_go = tk.Label(ctrl_wrap, text="\u25B6", fg=CA, font=F12, **bk)
        self._b_go.pack(side="left")
        self._b_go.bind("<Button-1>", lambda e: self._go())

        self._b_pa = tk.Label(ctrl_wrap, text="\u258C\u258C", fg=TD, font=F8, **bk)
        self._b_pa.pack(side="left")
        self._b_pa.bind("<Button-1>", lambda e: self._pause())

        self._b_st = tk.Label(ctrl_wrap, text="\u25A0", fg=TD, font=F12, **bk)
        self._b_st.pack(side="left")
        self._b_st.bind("<Button-1>", lambda e: self._stop())

        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        self._b_cl = tk.Label(ctrl_wrap, text="RESET", fg=CW, font=F8B, bg=BG_P, cursor="hand2", bd=0, padx=6)
        self._b_cl.pack(side="left")
        self._b_cl.bind("<Button-1>", lambda e: self._reset())
        self._b_cl.bind("<Enter>",    lambda e: self._b_cl.config(bg=BDG))
        self._b_cl.bind("<Leave>",    lambda e: self._b_cl.config(bg=BG_P))
        Tooltip(self._b_cl, "Save session & restart")

        self._b_ns = tk.Label(ctrl_wrap, text="NEXT SITE", fg=C_ANOM, font=F8B, bg=BG_P, cursor="hand2", bd=0, padx=6)
        self._b_ns.pack(side="left")
        self._b_ns.bind("<Button-1>", lambda e: self._next_site())
        self._b_ns.bind("<Enter>",    lambda e: self._b_ns.config(bg=BDG))
        self._b_ns.bind("<Leave>",    lambda e: self._b_ns.config(bg=BG_P))
        Tooltip(self._b_ns, "Save session, complete site & reset")

        self._main_btn_set = {"go": self._b_go, "pa": self._b_pa, "st": self._b_st}
        self._btn_sets.append(self._main_btn_set)
        self._update_buttons()


    # Construit la section d'alertes avec son en-tête et feed
    def _build_alerts(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9  = tkfont.Font(family="Consolas", size=9)

        if not detached:
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            tk.Frame(hdr_f, bg=T0, width=3).pack(side="left", fill="y")
            tk.Label(hdr_f, text="  ALERTS", font=F8B, bg=BG_P, fg=T0).pack(side="left")

            # Clear alerts button
            clr_btn = tk.Label(hdr_f, text="CLR", font=F8B, bg=BG_P, fg=TD, cursor="hand2", padx=4)
            clr_btn.pack(side="left", padx=(6, 0))
            clr_btn.bind("<Button-1>", lambda e: self._clear_alerts())
            clr_btn.bind("<Enter>", lambda e: clr_btn.config(fg=C_ALERT))
            clr_btn.bind("<Leave>", lambda e: clr_btn.config(fg=TD))
            Tooltip(clr_btn, "Clear alerts")

            self._alert_det_btn = tk.Label(hdr_f, text=" \u21F1 ", font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                                            bg=BG_P, fg=C_DETACH, cursor="hand2")
            self._alert_det_btn.pack(side="right", padx=2)
            self._alert_det_btn.bind("<Button-1>", lambda e: self._detach("alert"))
            self._alert_det_btn.bind("<Enter>", lambda e: self._alert_det_btn.config(bg=BDG))
            self._alert_det_btn.bind("<Leave>", lambda e: self._alert_det_btn.config(bg=BG_P))
            Tooltip(self._alert_det_btn, "Detach")

            # Collapse toggle (left of detach)
            self._alert_tog_btn = tk.Label(hdr_f, text="\u25BC" if not self._alert_collapsed else "\u25B6",
                                           font=tkfont.Font(family="Consolas", size=8), bg=BG_P, fg=TD, cursor="hand2")
            self._alert_tog_btn.pack(side="right", padx=4)
            self._alert_tog_btn.bind("<Button-1>", lambda e: self._toggle_collapse("alert"))
            self._alert_tog_btn.bind("<Enter>", lambda e: self._alert_tog_btn.config(fg=TB))
            self._alert_tog_btn.bind("<Leave>", lambda e: self._alert_tog_btn.config(fg=TD))
        else:
            # Detached header has CLR button too
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            clr_btn = tk.Label(hdr_f, text="CLR", font=F8B, bg=BG_P, fg=TD, cursor="hand2", padx=4)
            clr_btn.pack(side="right", padx=4)
            clr_btn.bind("<Button-1>", lambda e: self._clear_alerts())
            clr_btn.bind("<Enter>", lambda e: clr_btn.config(fg=C_ALERT))
            clr_btn.bind("<Leave>", lambda e: clr_btn.config(fg=TD))
            Tooltip(clr_btn, "Clear alerts")

        self._alert_wrap = tk.Frame(parent, bg=BG_P)
        if not detached and self._alert_collapsed:
            pass  # don't pack — collapsed
        else:
            self._alert_wrap.pack(fill="both", expand=True, padx=6, pady=(2, 4))
        self._alert_frame = self._alert_wrap
        tk.Label(self._alert_frame, text="  No alerts", font=F9, bg=BG_P, fg=CM, anchor="w").pack(anchor="w")
        self._last_alert_key = None  # Force redraw on next tick

        # For detached window: track font scaling on resize
        if detached:
            self._alert_det_frame = self._alert_frame
            self._alert_det_font_size = 9
            self._alert_frame.bind("<Configure>", self._on_alert_detached_resize)

    # Vide toutes les alertes du feed
    def _clear_alerts(self):
        self.data.alerts.clear()
        self._last_alert_key = None  # Force redraw

    # Adapte la taille de police quand la fenêtre alerte détachée est redimensionnée
    def _on_alert_detached_resize(self, event):
        if not self._alert_detached:
            return
        h = event.height
        
        # Calculate font size based on height (base 9pt at ~80px)
        base_h = 80
        base_size = 9
        scale = max(0.8, min(2.5, h / base_h))
        new_size = max(8, min(16, int(base_size * scale)))
        
        # Only update if size changed
        if hasattr(self, '_alert_det_font_size') and self._alert_det_font_size == new_size:
            return
        self._alert_det_font_size = new_size
        
        # Force redraw with new font size
        self._last_alert_key = None

    # Construit la section ISK Tracker (ISK/h, timer, breakdown)
    def _build_isk(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F7B = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [ISK TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Skip header when detached — DetachedWindow provides its own
        if not detached:
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            tk.Frame(hdr_f, bg=CD, width=3).pack(side="left", fill="y")
            tk.Label(hdr_f, text="  ISK TRACKER", font=F8B, bg=BG_P, fg=CD).pack(side="left")

            # ON/OFF button
            self._isk_on_btn = tk.Label(hdr_f, text="ON" if self._isk_enabled else "OFF",
                                         font=F7B, bg=BG_P, fg=CA if self._isk_enabled else CS, cursor="hand2", padx=4)
            self._isk_on_btn.pack(side="left", padx=(4, 0))
            self._isk_on_btn.bind("<Button-1>", lambda e: self._toggle_enabled("isk"))

            # Detach button (rightmost)
            self._isk_det_btn = tk.Label(hdr_f, text=" \u21F1 ", font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                                          bg=BG_P, fg=C_DETACH, cursor="hand2")
            self._isk_det_btn.pack(side="right", padx=2)
            self._isk_det_btn.bind("<Button-1>", lambda e: self._detach("isk"))
            self._isk_det_btn.bind("<Enter>", lambda e: self._isk_det_btn.config(bg=BDG))
            self._isk_det_btn.bind("<Leave>", lambda e: self._isk_det_btn.config(bg=BG_P))
            Tooltip(self._isk_det_btn, "Detach")

            # Collapse toggle
            self._isk_tog_btn = tk.Label(hdr_f, text="\u25BC" if not self._isk_collapsed else "\u25B6",
                                          font=tkfont.Font(family="Consolas", size=8), bg=BG_P, fg=TD, cursor="hand2")
            self._isk_tog_btn.pack(side="right", padx=4)
            self._isk_tog_btn.bind("<Button-1>", lambda e: self._toggle_collapse("isk"))
            self._isk_tog_btn.bind("<Enter>", lambda e: self._isk_tog_btn.config(fg=TB))
            self._isk_tog_btn.bind("<Leave>", lambda e: self._isk_tog_btn.config(fg=TD))

            if not self._isk_enabled:
                self._isk_det_btn.pack_forget()
                self._isk_tog_btn.pack_forget()

        # ── Content wrapper (hides on collapse or OFF) ──
        self._isk_wrap = tk.Frame(parent, bg=BG_P)
        show_content = self._isk_enabled and (detached or not self._isk_collapsed)
        if detached:
            if show_content:
                self._isk_wrap.pack(fill="both", expand=True, **pad)
        else:
            if show_content:
                self._isk_wrap.pack(fill="x", **pad)

        isk_top = tk.Frame(self._isk_wrap, bg=BG_P)
        isk_top.pack(fill="x")

        isk_left = tk.Frame(isk_top, bg=BG_P)
        isk_left.pack(side="left", fill="x", expand=True)
        tk.Label(isk_left, text="ISK / HOUR", font=F8, bg=BG_P, fg=TD).pack(anchor="w")
        self._isk_font_big  = tkfont.Font(family="Consolas", size=16, weight="bold")
        self._isk_font_calc = tkfont.Font(family="Consolas", size=10, weight="bold")

        il = tk.Label(isk_left, text="\u2014 STANDBY \u2014", font=self._isk_font_calc, bg=BG_P, fg=TD)
        il.pack(anchor="w")

        isk_right = tk.Frame(isk_top, bg=BG_P)
        isk_right.pack(side="right")
        tk.Label(isk_right, text="SESSION", font=F8, bg=BG_P, fg=TD).pack(anchor="e")
        sl = tk.Label(isk_right, text="00:00", font=tkfont.Font(family="Consolas", size=14, weight="bold"), bg=BG_P, fg=T1)
        sl.pack(anchor="e")

        labels = {"il": il, "sl": sl}
        if detached:
            self._isk_det_labels = labels
            self._isk_wrap.bind("<Configure>", self._on_isk_detached_resize)
        else:
            self.il = il
        self.sl = sl

        # ── Breakdown sub-collapse (inside ISK section) ──
        tk.Frame(self._isk_wrap, bg=BD, height=1).pack(fill="x", pady=3)

        brk_hdr = tk.Frame(self._isk_wrap, bg=BG_P, height=16)
        brk_hdr.pack(fill="x")
        brk_hdr.pack_propagate(False)
        self._brk_tog_btn = tk.Label(brk_hdr, text="\u25BC" if not self._brk_collapsed else "\u25B6",
                                      font=tkfont.Font(family="Consolas", size=7), bg=BG_P, fg=TD, cursor="hand2")
        self._brk_tog_btn.pack(side="left", padx=(6, 2))
        self._brk_tog_btn.bind("<Button-1>", lambda e: self._toggle_breakdown())
        self._brk_tog_btn.bind("<Enter>", lambda e: self._brk_tog_btn.config(fg=TB))
        self._brk_tog_btn.bind("<Leave>", lambda e: self._brk_tog_btn.config(fg=TD))
        tk.Label(brk_hdr, text="BREAKDOWN", font=tkfont.Font(family="Consolas", size=7, weight="bold"),
                 bg=BG_P, fg=TD).pack(side="left")

        self._brk_wrap = tk.Frame(self._isk_wrap, bg=BG_P)
        if not self._brk_collapsed:
            self._brk_wrap.pack(fill="x", padx=6, pady=(2, 2))

        # Breakdown content
        self._build_breakdown_content(self._brk_wrap)

    # Construit le contenu du sous-panneau breakdown ISK
    def _build_breakdown_content(self, brk_wrap):
        F8  = tkfont.Font(family="Consolas", size=8)

        r1 = tk.Frame(brk_wrap, bg=BG_P)
        r1.pack(fill="x")
        for idx, (lbl_text, c) in enumerate([("BOUNTIES", CG), ("EST. TAXES", CT), ("KILLS", CG)]):
            f = tk.Frame(r1, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")
            
            # Align: 0=Left(w), 1=Center(center), 2=Right(e)
            align = "w" if idx == 0 else ("center" if idx == 1 else "e")
            
            hdr_l = tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD)
            hdr_l.pack(anchor=align)
            l = tk.Label(f, text="0" if lbl_text == "KILLS" else "0 ISK",
                         font=tkfont.Font(family="Consolas", size=11, weight="bold"), bg=BG_P, fg=c)
            l.pack(anchor=align)
            
            if lbl_text == "BOUNTIES":
                self.gl = l
            elif lbl_text == "EST. TAXES":
                self.tl = l
                DynamicTooltip(hdr_l, lambda: f"Corp Tax: {self.tax_var.get()}%")
                DynamicTooltip(l,     lambda: f"Corp Tax: {self.tax_var.get()}%")
            else:
                self.bl = l

        tk.Frame(brk_wrap, bg=BD, height=1).pack(fill="x", pady=3)

        r3 = tk.Frame(brk_wrap, bg=BG_P)
        r3.pack(fill="x")
        for idx, (lbl_text, c) in enumerate([("LOOT ESTIMATE (CTRL+C)", CI), ("TOTAL NET (+LOOT)", CI)]):
            f = tk.Frame(r3, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")
            
            # Align: 0=Left(w), 1=Right(e)
            align = "w" if idx == 0 else "e"
            
            hdr_l = tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD)
            hdr_l.pack(anchor=align)
            l = tk.Label(f, text="0 ISK", font=tkfont.Font(family="Consolas", size=11, weight="bold"), bg=BG_P, fg=c)
            l.pack(anchor=align)
            
            if lbl_text == "LOOT ESTIMATE (CTRL+C)":
                self.ll = l
                Tooltip(hdr_l, "Copy items from inventory (CTRL+C) to parse value")
            else:
                self.tnl = l

    # Bascule l'affichage du sous-panneau breakdown ISK
    def _toggle_breakdown(self):
        self._brk_collapsed = not self._brk_collapsed
        self.char_cfg["brk_collapsed"] = self._brk_collapsed
        save_config(self.cfg)
        if self._brk_collapsed:
            self._brk_tog_btn.config(text="\u25B6")
            self._brk_wrap.pack_forget()
        else:
            self._brk_tog_btn.config(text="\u25BC")
            self._brk_wrap.pack(fill="x", padx=6, pady=(2, 2))

        # Resize: main window or detached ISK window
        if self._isk_detached and self._isk_window:
            try:
                w = self._isk_window.w
                w.update_idletasks()
                body = self._isk_window.body
                # Width never changes on breakdown collapse — only height
                cur_w = w.winfo_width()
                # DetachedWindow overhead: header(28) + sep(1) + bottom_bar(14) + body_pady(6) = 49
                req_h = body.winfo_reqheight() + 49
                w.geometry(f"{cur_w}x{req_h}+{w.winfo_x()}+{w.winfo_y()}")
            except Exception:
                pass
        else:
            self._fit()

    # Construit la section Mission Tracker
    def _build_missions(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F7B = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9  = tkfont.Font(family="Consolas", size=9)
        F9B = tkfont.Font(family="Consolas", size=9, weight="bold")
        F10B = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._msn_pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [MISSION TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Skip header when detached — DetachedWindow provides its own
        if not detached:
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            tk.Frame(hdr_f, bg=C_MSN, width=3).pack(side="left", fill="y")
            tk.Label(hdr_f, text="  MISSION TRACKER", font=F8B, bg=BG_P, fg=C_MSN).pack(side="left")

            # ON/OFF button
            self._msn_on_btn = tk.Label(hdr_f, text="ON" if self._msn_enabled else "OFF",
                                         font=F7B, bg=BG_P, fg=CA if self._msn_enabled else CS, cursor="hand2", padx=4)
            self._msn_on_btn.pack(side="left", padx=(4, 0))
            self._msn_on_btn.bind("<Button-1>", lambda e: self._toggle_enabled("msn"))

            # Detach button (rightmost)
            self._msn_det_btn = tk.Label(hdr_f, text=" \u21F1 ", font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                                          bg=BG_P, fg=C_DETACH, cursor="hand2")
            self._msn_det_btn.pack(side="right", padx=2)
            self._msn_det_btn.bind("<Button-1>", lambda e: self._detach("msn"))
            self._msn_det_btn.bind("<Enter>", lambda e: self._msn_det_btn.config(bg=BDG))
            self._msn_det_btn.bind("<Leave>", lambda e: self._msn_det_btn.config(bg=BG_P))
            Tooltip(self._msn_det_btn, "Detach")

            # Collapse toggle
            self._msn_tog_btn = tk.Label(hdr_f, text="\u25BC" if not self._msn_collapsed else "\u25B6",
                                          font=tkfont.Font(family="Consolas", size=8), bg=BG_P, fg=TD, cursor="hand2")
            self._msn_tog_btn.pack(side="right", padx=4)
            self._msn_tog_btn.bind("<Button-1>", lambda e: self._toggle_collapse("msn"))
            self._msn_tog_btn.bind("<Enter>", lambda e: self._msn_tog_btn.config(fg=TB))
            self._msn_tog_btn.bind("<Leave>", lambda e: self._msn_tog_btn.config(fg=TD))

            if not self._msn_enabled:
                self._msn_det_btn.pack_forget()
                self._msn_tog_btn.pack_forget()

        # ── Content wrapper ──
        self._msn_wrap = tk.Frame(parent, bg=BG_P)
        show_content = self._msn_enabled and (detached or not self._msn_collapsed)
        if show_content:
            self._msn_wrap.pack(fill="x", **self._msn_pad)
        msn_wrap = self._msn_wrap

        r1 = tk.Frame(msn_wrap, bg=BG_P)
        r1.pack(fill="x")
        lf = tk.Frame(r1, bg=BG_P)
        lf.pack(side="left", expand=True, fill="x")
        tk.Label(lf, text="MISSION", font=F8, bg=BG_P, fg=TD).pack(anchor="w")
        self._msn_name_lbl = tk.Label(lf, text="\u2014 None \u2014", font=F10B, bg=BG_P, fg=CM)
        self._msn_name_lbl.pack(anchor="w")

        rf = tk.Frame(r1, bg=BG_P)
        rf.pack(side="right")
        tk.Label(rf, text="OBJECTIVE", font=F8, bg=BG_P, fg=TD).pack(anchor="e")
        self._msn_obj_lbl = tk.Label(rf, text="\u2014", font=F9B, bg=BG_P, fg=CM)
        self._msn_obj_lbl.pack(anchor="e")

        tk.Frame(msn_wrap, bg=BD, height=1).pack(fill="x", pady=3)

        r2 = tk.Frame(msn_wrap, bg=BG_P)
        r2.pack(fill="x")
        for lbl_text, c in [("STORYLINE", C_MSN), ("COMPLETED", CG)]:
            f = tk.Frame(r2, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")
            tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD).pack(anchor="w")
            l = tk.Label(f, text="0/16" if lbl_text == "STORYLINE" else "0", font=F10B, bg=BG_P, fg=c)
            l.pack(anchor="w")
            if lbl_text == "STORYLINE":
                self._msn_story_lbl = l
                Tooltip(l, "Missions toward next Storyline offer")
            else:
                self._msn_done_lbl = l

        if detached:
            self._msn_det_labels = {"msn_name": self._msn_name_lbl, "msn_obj": self._msn_obj_lbl,
                                     "msn_story": self._msn_story_lbl, "msn_done": self._msn_done_lbl}

    # Construit la section Anomaly Tracker
    def _build_anomalies(self, parent, detached=False):
        F8   = tkfont.Font(family="Consolas", size=8)
        F7B  = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B  = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9B  = tkfont.Font(family="Consolas", size=9, weight="bold")
        F10B = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._anom_pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [ANOMALY TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Skip header when detached — DetachedWindow provides its own
        if not detached:
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            tk.Frame(hdr_f, bg=C_ANOM, width=3).pack(side="left", fill="y")
            tk.Label(hdr_f, text="  ANOMALY TRACKER", font=F8B, bg=BG_P, fg=C_ANOM).pack(side="left")

            # ON/OFF button
            self._anom_on_btn = tk.Label(hdr_f, text="ON" if self._anom_enabled else "OFF",
                                          font=F7B, bg=BG_P, fg=CA if self._anom_enabled else CS, cursor="hand2", padx=4)
            self._anom_on_btn.pack(side="left", padx=(4, 0))
            self._anom_on_btn.bind("<Button-1>", lambda e: self._toggle_enabled("anom"))

            # Detach button (rightmost)
            self._anom_det_btn = tk.Label(hdr_f, text=" \u21F1 ", font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                                           bg=BG_P, fg=C_DETACH, cursor="hand2")
            self._anom_det_btn.pack(side="right", padx=2)
            self._anom_det_btn.bind("<Button-1>", lambda e: self._detach("anom"))
            self._anom_det_btn.bind("<Enter>", lambda e: self._anom_det_btn.config(bg=BDG))
            self._anom_det_btn.bind("<Leave>", lambda e: self._anom_det_btn.config(bg=BG_P))
            Tooltip(self._anom_det_btn, "Detach")

            # Collapse toggle
            self._anom_tog_btn = tk.Label(hdr_f, text="\u25BC" if not self._anom_collapsed else "\u25B6",
                                           font=tkfont.Font(family="Consolas", size=8), bg=BG_P, fg=TD, cursor="hand2")
            self._anom_tog_btn.pack(side="right", padx=4)
            self._anom_tog_btn.bind("<Button-1>", lambda e: self._toggle_collapse("anom"))
            self._anom_tog_btn.bind("<Enter>", lambda e: self._anom_tog_btn.config(fg=TB))
            self._anom_tog_btn.bind("<Leave>", lambda e: self._anom_tog_btn.config(fg=TD))

            if not self._anom_enabled:
                self._anom_det_btn.pack_forget()
                self._anom_tog_btn.pack_forget()

        # ── Content wrapper ──
        self._anom_wrap = tk.Frame(parent, bg=BG_P)
        show_content = self._anom_enabled and (detached or not self._anom_collapsed)
        if detached:
            if show_content:
                self._anom_wrap.pack(fill="both", expand=True, **self._anom_pad)
        else:
            if show_content:
                self._anom_wrap.pack(fill="x", **self._anom_pad)
        aw = self._anom_wrap

        r1 = tk.Frame(aw, bg=BG_P)
        r1.pack(fill="x")
        lf = tk.Frame(r1, bg=BG_P)
        lf.pack(side="left", expand=True, fill="x")
        tk.Label(lf, text="CURRENT SITE", font=F8, bg=BG_P, fg=TD).pack(anchor="w")
        self._anom_cur_lbl = tk.Label(lf, text="\u2014 Idle \u2014", font=F10B, bg=BG_P, fg=CM)
        self._anom_cur_lbl.pack(anchor="w")

        rf = tk.Frame(r1, bg=BG_P)
        rf.pack(side="right")
        tk.Label(rf, text="CLEARED", font=F8, bg=BG_P, fg=TD).pack(anchor="e")
        self._anom_cleared_lbl = tk.Label(rf, text="0", font=F10B, bg=BG_P, fg=CG)
        self._anom_cleared_lbl.pack(anchor="e")

        tk.Frame(aw, bg=BD, height=1).pack(fill="x", pady=3)

        r2 = tk.Frame(aw, bg=BG_P)
        r2.pack(fill="x")
        for lbl_text, c, attr in [("AVG TIME", T1, "_anom_avg_time_lbl"), ("AVG ISK", CI, "_anom_avg_isk_lbl"), ("BEST ISK", CG, "_anom_best_isk_lbl")]:
            f = tk.Frame(r2, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")
            tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD).pack(anchor="w")
            l = tk.Label(f, text="\u2014", font=F9B, bg=BG_P, fg=c)
            l.pack(anchor="w")
            setattr(self, attr, l)

        if detached:
            self._anom_det_labels = {"cur": self._anom_cur_lbl, "cleared": self._anom_cleared_lbl,
                                      "avg_time": self._anom_avg_time_lbl, "avg_isk": self._anom_avg_isk_lbl,
                                      "best_isk": self._anom_best_isk_lbl}
            self._anom_wrap.bind("<Configure>", self._on_anom_detached_resize)

    # Adapte la police de la section anomalie quand la fenêtre détachée est redimensionnée
    def _on_anom_detached_resize(self, event):
        if not self._anom_detached or not self._anom_det_labels:
            return
        if getattr(self, '_scaling_anom', False):
            return
        h = event.height
        last_h = getattr(self, '_anom_det_last_h', 0)
        if abs(h - last_h) < 5:
            return
        self._anom_det_last_h = h

        self._scaling_anom = True
        try:
            scale    = max(0.8, min(3.0, h / 100))
            val_size = max(9, min(36, int(10 * scale)))
            val_font = getattr(self, "_anom_det_val_font", None)
            if val_font is None:
                self._anom_det_val_font = val_font = tkfont.Font(family="Consolas", size=val_size, weight="bold")
            else:
                val_font.configure(size=val_size)
            labels = self._anom_det_labels
            for key in ("cur", "cleared", "avg_time", "avg_isk", "best_isk"):
                if labels.get(key):
                    labels[key].config(font=val_font)
        finally:
            self._scaling_anom = False

    # Adapte la police ISK/SESSION quand la fenêtre ISK détachée est redimensionnée
    def _on_isk_detached_resize(self, event):
        if not self._isk_detached or not self._isk_det_labels:
            return
        if getattr(self, '_scaling_isk', False):
            return
            
        # Scaling by width prevents text from shrinking wildly when the breakdown is collapsed
        w = event.width
        last_w = getattr(self, '_isk_det_last_w', 0)
        if abs(w - last_w) < 5:
            return
        self._isk_det_last_w = w

        self._scaling_isk = True
        try:
            # Base width of ~350 yields scale ~1.0. Keeps text sizes reasonable.
            scale     = max(0.8, min(2.5, w / 350))
            val_size  = max(11, min(32, int(14 * scale)))
            sess_size = max(11, min(24, int(12 * scale)))
            
            self._isk_font_big.configure(size=val_size)
            self._isk_font_calc.configure(size=max(10, val_size - 4))
            labels = self._isk_det_labels
            if labels.get("sl"):
                sess_font = getattr(self, "_isk_det_sess_font", None)
                if sess_font is None:
                    self._isk_det_sess_font = sess_font = tkfont.Font(family="Consolas", size=sess_size, weight="bold")
                else:
                    sess_font.configure(size=sess_size)
                labels["sl"].config(font=sess_font)
        finally:
            self._scaling_isk = False

    # ── Graphique d'historique DPS ────────────────────────────────────

    # Ajoute les valeurs DPS courantes au deque d'historique (appelé à chaque tick)
    def _sample_dps_history(self, dps_out=None, dps_in=None):
        # _tick already computed both values this frame — accept them to avoid
        # two redundant dps() recomputations per tick.
        d = self.data
        if dps_out is None: dps_out = d.dps(True)
        if dps_in is None:  dps_in  = d.dps(False)
        d.dps_hist.append((time.monotonic(), dps_out, dps_in))

    # ── Section toggle helpers ───────────────────────────────────────
    # Active/désactive une section (avec exclusivité mutuelle MSN/ANOM)
    def _toggle_enabled(self, section):
        attr = f"_{section}_enabled"
        enabled = not getattr(self, attr)

        # ── Mutual exclusivity: MSN and ANOM cannot both be ON ──
        if enabled and section in ("msn", "anom"):
            other = "anom" if section == "msn" else "msn"
            if getattr(self, f"_{other}_enabled"):
                self._force_disable(other)

        setattr(self, attr, enabled)
        self.char_cfg[f"{section}_enabled"] = enabled
        save_config(self.cfg)

        # If turning OFF while detached, reattach first
        if not enabled:
            self._force_detach_off(section)

        # Update ON/OFF button appearance
        on_btn = getattr(self, f"_{section}_on_btn", None)
        if on_btn:
            on_btn.config(text="ON" if enabled else "OFF", fg=CA if enabled else CS)

        # Show/hide header controls and content
        if not getattr(self, f"_{section}_detached", False):
            tog = getattr(self, f"_{section}_tog_btn", None)
            det = getattr(self, f"_{section}_det_btn", None)
            wrap = getattr(self, f"_{section}_wrap", None)
            collapsed = getattr(self, f"_{section}_collapsed", False)

            if enabled:
                if det:
                    det.pack(side="right", padx=2)
                if tog:
                    tog.pack(side="right", padx=4)
                if wrap and not collapsed:
                    wrap.pack(fill="x", **self._get_section_pad(section))
            else:
                if tog:
                    tog.pack_forget()
                if det:
                    det.pack_forget()
                if wrap:
                    wrap.pack_forget()

        self._fit()

    # Désactive de force une section (exclusivité mutuelle MSN/ANOM)
    def _force_disable(self, section):

        # Force-disable a section (for mutual exclusivity)
        setattr(self, f"_{section}_enabled", False)
        self.char_cfg[f"{section}_enabled"] = False

        self._force_detach_off(section)

        on_btn = getattr(self, f"_{section}_on_btn", None)
        if on_btn:
            on_btn.config(text="OFF", fg=CS)

        if not getattr(self, f"_{section}_detached", False):
            tog = getattr(self, f"_{section}_tog_btn", None)
            det = getattr(self, f"_{section}_det_btn", None)
            wrap = getattr(self, f"_{section}_wrap", None)
            if tog:
                tog.pack_forget()
            if det:
                det.pack_forget()
            if wrap:
                wrap.pack_forget()

        save_config(self.cfg)

    # Réattache et ferme la fenêtre détachée d'une section
    def _force_detach_off(self, section):

        # Reattach and close detached window if section is detached
        detached_attr = f"_{section}_detached"
        if getattr(self, detached_attr, False):
            window_attr = f"_{section}_window"
            win = getattr(self, window_attr, None)
            if win:
                try:
                    win._save_geometry()
                    win.w.destroy()
                except Exception:
                    pass
                setattr(self, window_attr, None)
            setattr(self, detached_attr, False)
            det_labels_attr = f"_{section}_det_labels"
            setattr(self, det_labels_attr, {})
            container = getattr(self, f"_{section}_container")
            for w in container.winfo_children():
                w.destroy()
            build_fn = getattr(self, f"_build_{self._section_build_name(section)}")
            build_fn(container, detached=False)
            container.grid()

    # Retourne le nom de la méthode de construction pour une section
    def _section_build_name(self, section):
        names = {"isk": "isk", "msn": "missions", "anom": "anomalies"}
        return names.get(section, section)

    # Retourne le padding approprié pour une section
    def _get_section_pad(self, section):
        return dict(padx=6, pady=(2, 4))

    # Collapse/déplie une section de l'interface
    def _toggle_collapse(self, section):
        attr = f"_{section}_collapsed"
        collapsed = not getattr(self, attr)
        setattr(self, attr, collapsed)
        self.char_cfg[f"{section}_collapsed"] = collapsed
        save_config(self.cfg)

        tog = getattr(self, f"_{section}_tog_btn", None)
        wrap = getattr(self, f"_{section}_wrap", None)

        if collapsed:
            if tog:
                tog.config(text="\u25B6")
            if wrap:
                wrap.pack_forget()
        else:
            if tog:
                tog.config(text="\u25BC")
            if wrap:
                if section == "alert":
                    wrap.pack(fill="both", expand=True, **self._get_section_pad(section))
                else:
                    wrap.pack(fill="x", **self._get_section_pad(section))
        self._fit()

    # Crée un en-tête de section coloré générique
    def _sec(self, par, title, accent):
        tb = tk.Frame(par, bg=BG_P, height=20)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Frame(tb, bg=accent, width=3).pack(side="left", fill="y")
        tk.Label(tb, text=f"  {title}", font=tkfont.Font(family="Consolas", size=8, weight="bold"), bg=BG_P, fg=accent).pack(side="left")

    # Met à jour les couleurs des boutons Play/Pause/Stop selon l'état
    def _update_buttons(self):
        for bs in self._btn_sets:
            go = bs["go"]
            pa = bs["pa"]
            st = bs["st"]
            if self._st == "running":
                go.config(fg=TD)
                pa.config(fg=CP)
                st.config(fg=CS)
            elif self._st == "paused":
                go.config(fg=CA)
                pa.config(fg=TD)
                st.config(fg=CS)
            else:
                go.config(fg=CA)
                pa.config(fg=TD)
                st.config(fg=TD)

    # Met à jour les labels ISK/heure et timer (live ou frozen)
    def _update_isk_labels(self, labels, frozen=None):
        if not labels: return
        il = labels.get("il")
        sl = labels.get("sl")
        if frozen:
            if il:
                font = self._isk_font_big if frozen["isk_font"] == "big" else self._isk_font_calc
                il.config(text=frozen["isk_text"], fg=frozen["isk_fg"], font=font)
            if sl:
                sl.config(text=frozen["timer"])
        else:
            d = self.data
            if il:
                if self._st == "running":
                    if d.secs() >= 60 and d.bg > 0:
                        il.config(text=f"{fisk(d.isk())} ISK", fg=CI, font=self._isk_font_big)
                    else:
                        # Still waiting for data — show CALC animation
                        self._show_calc_on(il)
                elif self._st == "paused":
                    if d.secs() >= 60 and d.bg > 0:
                        il.config(text=f"{fisk(d.isk())} ISK", fg=CP, font=self._isk_font_big)
                    else:
                        il.config(text="\u2014 PAUSED \u2014", fg=CP, font=self._isk_font_calc)
                elif self._st == "stopped":
                    il.config(text="\u2014 STANDBY \u2014", fg=TD, font=self._isk_font_calc)
            if sl:
                dur = fdur(d.secs()) if (d.t0 or d.acc_sec > 0) else "00:00"
                sl.config(text=dur)

    # Met à jour les labels du breakdown (bounties, taxes, kills, loot)
    def _update_breakdown_labels(self, frozen=None):
        if frozen:
            self.gl.config(text=frozen["gross"])
            self.tl.config(text=frozen["taxes"])
            self.bl.config(text=frozen["kills"])
            self.ll.config(text=frozen["loot"])
            self.tnl.config(text=frozen["total_net"])
        else:
            d = self.data
            self.gl.config(text=f"{fiskf(d.bg)} ISK")
            self.tl.config(text=f"-{fiskf(d.bg*d.tax)} ISK")
            self.bl.config(text=str(d.bc))
            if not self._loot_loading:   # don't overwrite the spinner
                self.ll.config(text=f"{fiskf(d.loot_val)} ISK")
            self.tnl.config(text=f"{fiskf(d.bg*(1-d.tax) + d.loot_val)} ISK")

    # Met à jour les labels de mission (nom, objectif, compteurs)
    def _update_mission_labels(self, frozen=None):
        if frozen:
            name = frozen.get("msn_name", "\u2014 None \u2014")
            self._msn_name_lbl.config(text=name[:24], fg=C_MSN if name != "\u2014 None \u2014" else CM)
            obj = frozen.get("msn_obj", "\u2014")
            self._msn_obj_lbl.config(text=obj, fg=CA if "\u2714" in obj else CM)
            self._msn_done_lbl.config(text=frozen.get("msn_done", "0"))
            self._msn_story_lbl.config(text=frozen.get("msn_story", "0/16"))
        else:
            d = self.data
            name = d.mission_name or "\u2014 None \u2014"
            self._msn_name_lbl.config(text=name[:24], fg=C_MSN if d.mission_name else CM)
            if d.mission_obj_met:
                self._msn_obj_lbl.config(text="\u2714 DONE", fg=CA)
            elif d.mission_name:
                self._msn_obj_lbl.config(text="IN PROGRESS", fg=CP)
            else:
                self._msn_obj_lbl.config(text="\u2014", fg=CM)
            self._msn_done_lbl.config(text=str(d.missions_done))
            self._msn_story_lbl.config(text=f"{self._storyline_ctr}/16")

    # Redessine le feed d'alertes si le contenu a changé
    def _update_alert_labels(self, frozen=None):
        if frozen:
            alerts = frozen.get("msn_alerts", [])
        else:
            alerts = self.data.alerts

        alert_key = hash(tuple((t, a, x) for t, a, x in alerts)) if alerts else 0
        if not hasattr(self, '_last_alert_key') or self._last_alert_key != alert_key:
            self._last_alert_key = alert_key
            
            # Use dynamic font size if detached, otherwise default 9pt
            font_size = getattr(self, '_alert_det_font_size', 9) if self._alert_detached else 9
            F_alert = self._alert_font_cache.get(font_size)
            if F_alert is None:
                F_alert = self._alert_font_cache[font_size] = tkfont.Font(family="Consolas", size=font_size)
            
            for w in self._alert_frame.winfo_children():
                w.destroy()
            if alerts:
                for ts_str, atype, text in alerts:
                    if atype in ("DANGER", "FACTION"):
                        ac = C_ALERT
                    elif atype in ("SCRAM", "WEB"):
                        ac = C_EWAR
                    elif atype == "ESCAL":
                        ac = C_ESCAL
                    elif atype == "STORY":
                        ac = CW
                    elif atype == "OBJ":
                        ac = CA
                    elif atype == "STAND":
                        ac = CI
                    elif atype == "INFO":
                        ac = T0
                    else:
                        ac = T1
                    row = tk.Frame(self._alert_frame, bg=BG_P)
                    row.pack(fill="x")
                    tk.Label(row, text=f"  {ts_str}", font=F_alert, bg=BG_P, fg=TD, anchor="w").pack(side="left")
                    tk.Label(row, text=text, font=F_alert, bg=BG_P, fg=ac, anchor="w").pack(side="left", fill="x")
            else:
                tk.Label(self._alert_frame, text="  No alerts", font=F_alert, bg=BG_P, fg=CM, anchor="w").pack(anchor="w")

    # Met à jour les labels du tracker d'anomalie
    def _update_anomaly_labels(self, frozen=None):
        if frozen:
            sites    = frozen.get("anom_sites", 0)
            avg_time = frozen.get("anom_avg_time", "\u2014")
            avg_isk  = frozen.get("anom_avg_isk", "\u2014")
            best_isk = frozen.get("anom_best_isk", "\u2014")
            cur_time = frozen.get("anom_cur_time", "\u2014")
            self._anom_cur_lbl.config(text=cur_time if cur_time != "\u2014" else "\u2014 Stopped \u2014", fg=C_ANOM if cur_time != "\u2014" else CM)
            self._anom_cleared_lbl.config(text=str(sites))
            self._anom_avg_time_lbl.config(text=avg_time)
            self._anom_avg_isk_lbl.config(text=avg_isk)
            self._anom_best_isk_lbl.config(text=best_isk)
        else:
            d = self.data
            n, avg_time, avg_isk, best_isk, cur_secs = self._anom_stats()

            # When paused, show frozen anomaly time instead of live
            if self._st == "paused" and self._anom_paused_secs > 0:
                cur_secs = self._anom_paused_secs
            if d.anom_current and cur_secs > 0:
                self._anom_cur_lbl.config(text=fdur(cur_secs), fg=CP if self._st == "paused" else C_ANOM)
            elif self._st == "running":
                self._anom_cur_lbl.config(text="\u2014 Warping \u2014", fg=CM)
            elif self._st == "paused":
                self._anom_cur_lbl.config(text="\u2014 Paused \u2014", fg=CP)
            else:
                self._anom_cur_lbl.config(text="\u2014 Idle \u2014", fg=CM)
            self._anom_cleared_lbl.config(text=str(n))
            self._anom_avg_time_lbl.config(text=fdur(avg_time) if avg_time > 0 else "\u2014")
            self._anom_avg_isk_lbl.config(text=fisk(avg_isk) if avg_isk > 0 else "\u2014")
            self._anom_best_isk_lbl.config(text=fisk(best_isk) if best_isk > 0 else "\u2014")

    # Lance l'animation CALC sur le label ISK principal
    def _show_calc(self): self._show_calc_on(self.il)

    # Affiche l'animation CALC sur un label donné
    def _show_calc_on(self, label):
        self._calc_dots = (self._calc_dots + 1) % 4
        dots = "." * self._calc_dots
        pad  = " " * (3 - self._calc_dots)
        if self._st != "running" or (self.data.t0 is None and self.data.acc_sec == 0):
            label.config(text="\u2014 STANDBY \u2014", fg=TD)
        else:
            label.config(text=f"\u25C8 CALC{dots}{pad}", fg=CK)

    # Sauvegarde la session, la config et ferme l'application
    def _quit(self):
        d = self.data

        # Always save session on close if there's any data worth saving
        if not self._session_saved and (d.bg > 0 or d.dd > 0 or d.loot_val > 0):

            # Accumulate running time if still active
            if d.t0:
                d.acc_sec += (datetime.now(timezone.utc) - d.t0).total_seconds()
                d.t0 = None
            try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
            except Exception:
                pass
            self._anom_close_current()
            char_name = self.char_name
            try: tax_pct = float(self.tax_var.get())
            except:
                tax_pct = DEF_TAX
            save_session(d, char_name, tax_pct)
        self._save_pos()
        self.char_cfg["main_minimized"] = self._main_hidden
        self.char_cfg["isk_detached"]   = self._isk_detached
        self.char_cfg["msn_detached"]   = self._msn_detached
        self.char_cfg["anom_detached"]  = self._anom_detached
        self.char_cfg["alert_detached"] = self._alert_detached
        for key, attr in [("isk", "_isk_window"),
                           ("msn", "_msn_window"), ("anom", "_anom_window"),
                           ("alert", "_alert_window")]:
            try:
                win = getattr(self, attr)
                if win and win.w.winfo_exists():
                    win._save_geometry()
                    win.w.destroy()
            except Exception:
                pass
        save_config(self.cfg)
        if self.fh:
            self.fh.close()
        self._close_chatlog()
        # Cancel pending after() loops so they don't fire on destroyed widgets
        for _job in ("_poll_job", "_tick_job", "_loot_anim_job"):
            jid = getattr(self, _job, None)
            if jid:
                try: self.root.after_cancel(jid)
                except Exception: pass
                setattr(self, _job, None)
        self.root.destroy()   # destroys this Toplevel; MainUI root stays alive

    # ── Parse a combat log line ──────────────────────────────────────
    # Parse une ligne de log de combat et met à jour les données de session
    def _parse(self, raw):
        d = self.data
        ts = datetime.now(timezone.utc)
        m = RE_TS.search(raw)
        if m:
            try:
                ts = datetime.strptime(m.group(1), "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                pass

        if RE_SS.search(raw) or raw.strip().startswith("---"): return

        # Fast skip — only process lines with known keywords
        if not any(k in raw for k in ('(combat)', '(bounty)', '(notify)', 'Objective', 'mission', 'standings', 'Dreadnought')):
            return

        # Most common events first
        if (m := RE_TO.search(raw)):
            dm = int(m.group(1) or m.group(4))   # group 1=HTML alt, 4=plain alt
            d.add_dmg_out(ts, dm)
            self._anom_combat_event(ts)
            return

        if (m := RE_FR.search(raw)):
            dm = int(m.group(1) or m.group(4))   # group 1=HTML alt, 4=plain alt
            d.add_dmg_in(ts, dm)
            self._anom_combat_event(ts)
            return

        if (m := RE_BT.search(raw)):
            a = pnum(m.group(1))
            d.bg += a
            d.bc += 1
            self._anom_combat_event(ts)
            self._anom_add_bounty(ts, a)
            return

        if (m := RE_DM.search(raw)):
            d.md += 1
            self._anom_combat_event(ts)
            return

        if RE_NM.search(raw):
            self._anom_combat_event(ts)
            return

        # Rare events
        now_str = datetime.now().strftime("%H:%M:%S")
        m = RE_OBJ_MET.search(raw)
        if m:
            d.mission_obj_met = True
            d.alerts.append((now_str, "OBJ", "Objective complete \u2014 return to agent"))
            return

        m = RE_MSN_COMP.search(raw)
        if m:
            d.missions_done += 1
            d.mission_obj_met = False
            self._storyline_ctr += 1
            if self._storyline_ctr >= 16:
                d.alerts.append((now_str, "STORY", "\u2605 STORYLINE MISSION IMMINENT"))
                self._storyline_ctr = 0
            d.alerts.append((now_str, "MSN", f"Mission #{m.group(1)} complete ({self._storyline_ctr}/16)"))
            self.char_cfg["storyline_counter"] = self._storyline_ctr
            save_config(self.cfg)
            return

        m = RE_STAND.search(raw)
        if m:
            faction = m.group(1).strip()
            amt = m.group(2)
            d.alerts.append((now_str, "STAND", f"+{amt} standing with {faction}"))
            return

        m = RE_FACTION.search(raw)
        if m:
            ftype = m.group(1).strip()
            fname = m.group(2).strip()
            d.alerts.append((now_str, "FACTION", f"\u26A0 {ftype} {fname} on grid!"))
            return

        m = RE_DREAD.search(raw)
        if m:
            d.alerts.append((now_str, "DANGER", f"\u2620 DREADNOUGHT: {m.group(1).strip()}"))
            return

        m = RE_ESCAL.search(raw)
        if m:
            d.alerts.append((now_str, "ESCAL", f"\u272A ESCALATION: {m.group(1).strip()}"))
            return

        # EWAR — scramble fires as (combat) line; group 1=HTML alt, 2=plain alt
        m = RE_SCRAM.search(raw)
        if m:
            npc = shtml((m.group(1) or m.group(2)).strip())
            d.alerts.append((now_str, "SCRAM", f"\u26D4 SCRAMBLED by {npc}!"))
            self._flash_alert()
            return

    # ── Polling loop (reads new log data) ────────────────────────────
    # Lit une fois les nouveaux logs (gamelog + rotation + chatlog).
    # Appelé par le timer _poll ET par le watchdog (sur événement fichier).
    def _read_logs_once(self):
        if getattr(self, "_suspended", False) or self._st != "running":
            return
        try:
            self._read()
            self._check_gamelog_rotation()
            latest_chat = self._find_latest_chatlog()
            if latest_chat and latest_chat != self._chat_file:
                self._open_chatlog()
            self._read_chatlog()
        except Exception:
            pass

    # Boucle de lecture des logs. Quand le watchdog est actif ce timer n'est
    # plus qu'un filet de sécurité lent (2 s) ; sinon c'est le lecteur principal
    # à poll_ms. La lecture du presse-papiers vit dans _tick pour rester réactive.
    def _poll(self):
        try:
            self._read_logs_once()
        except Exception:
            pass
        interval = self.poll_ms
        mu = self._main_ui
        if mu is not None and getattr(mu, "_log_observer", None) is not None:
            interval = max(self.poll_ms, 2000)
        self._poll_job = self.root.after(interval, self._poll)

    # ── UI tick loop (updates labels) ────────────────────────────────
    # Boucle de mise à jour de l'UI (s'exécute toutes les poll_ms ms)
    def _tick(self):
        self._last_tick_wall = time.monotonic()
        # Clipboard/loot polling lives here (not _poll) so it stays responsive
        # even when the watchdog observer slows the _poll fallback interval.
        if not getattr(self, "_suspended", False):
            self._check_clipboard()
        d = self.data
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            pass

        if self._st == "stopped" and self._frozen:
            main_isk = {"il": self.il, "sl": self.sl}
            self._update_isk_labels(main_isk, frozen=self._frozen)
            self._update_breakdown_labels(frozen=self._frozen)
            self._update_mission_labels(frozen=self._frozen)
            self._update_alert_labels(frozen=self._frozen)
            self._update_anomaly_labels(frozen=self._frozen)
            if self._isk_detached and self._isk_det_labels:
                self._update_isk_labels(self._isk_det_labels, frozen=self._frozen)
            self._tick_job = self.root.after(self.poll_ms, self._tick)
            return

        # Live dirty-flag updates (main window)
        isk_text = f"{fisk(d.isk())} ISK" if d.secs() >= 60 and d.bg > 0 else "\u2014 STANDBY \u2014"
        if self._last_values.get("isk_hr") != isk_text:
            self._last_values["isk_hr"] = isk_text
            fg = CI if d.secs() >= 60 and d.bg > 0 else (CP if self._st == "paused" else TD)
            font = self._isk_font_big if d.secs() >= 60 and d.bg > 0 else self._isk_font_calc
            self.il.config(text=isk_text, fg=fg, font=font)

        timer_text = fdur(d.secs()) if (d.t0 or d.acc_sec > 0) else "00:00"
        if self._last_values.get("timer") != timer_text:
            self._last_values["timer"] = timer_text
            self.sl.config(text=timer_text)

        dd = d.dps(True)
        dr = d.dps(False)
        # Track the session PEAK continuously — _stop() alone only captured the
        # instantaneous DPS at the moment Stop was pressed, missing real spikes.
        if dd > d.pkd: d.pkd = dd
        if dr > d.pkr: d.pkr = dr

        # Échantillonne l'historique DPS — consommé par l'overlay DPS autonome
        if self._st == "running":
            self._sample_dps_history(dd, dr)

        self._update_breakdown_labels()
        self._update_mission_labels()
        self._update_alert_labels()
        if self._st == "running":
            self._anom_check_gap()
        self._update_anomaly_labels()

        # Fenêtres détachées
        if self._isk_detached and self._isk_det_labels:
            self._update_isk_labels(self._isk_det_labels)

        self._tick_job = self.root.after(self.poll_ms, self._tick)

    # ── Stop session & freeze display ────────────────────────────────
    # Arrête la session et gèle l'affichage avec les données finales
    def _stop(self):
        if self._st == "stopped": return
        d = self.data
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            pass

        if self._st == "running" and d.t0:
            d.acc_sec += (datetime.now(timezone.utc) - d.t0).total_seconds()
            d.t0 = None

        dd = d.dps(True)
        dr = d.dps(False)
        if dd > d.pkd:
            d.pkd = dd
        if dr > d.pkr:
            d.pkr = dr

        # Freeze anomaly timer (save current site elapsed time)
        if d.anom_current and self._anom_start_wall:
            self._anom_paused_secs = time.monotonic() - self._anom_start_wall

        a_n, a_avg_t, a_avg_i, a_best, _ = self._anom_stats()
        a_cur = self._anom_paused_secs

        self._frozen = {
            "timer":    fdur(d.secs()) if (d.acc_sec > 0) else "00:00",
            "isk_text": f"{fisk(d.isk())} ISK" if d.secs() >= 60 and d.bg > 0 else "\u2014 STOPPED \u2014",
            "isk_fg":   CI if (d.secs() >= 60 and d.bg > 0) else TD,
            "isk_font": "big" if (d.secs() >= 60 and d.bg > 0) else "calc",
            "gross":    f"{fiskf(d.bg)} ISK",
            "taxes":    f"-{fiskf(d.bg*d.tax)} ISK",
            "kills":    str(d.bc),
            "loot":     f"{fiskf(d.loot_val)} ISK",
            "total_net":f"{fiskf(d.bg*(1-d.tax) + d.loot_val)} ISK",
            "dps_out":  f"{dd:,.0f}",
            "dps_in":   f"{dr:,.0f}",
            "peak_d":   f"PEAK: {d.pkd:,.0f}",
            "peak_r":   f"PEAK: {d.pkr:,.0f}",
            "msn_name": d.mission_name or "\u2014 None \u2014",
            "msn_obj":  "\u2714 DONE" if d.mission_obj_met else "\u2014",
            "msn_done": str(d.missions_done),
            "msn_story": f"{self._storyline_ctr}/16",
            "msn_alerts": list(d.alerts),
            "anom_sites":    a_n,
            "anom_avg_time": fdur(a_avg_t) if a_avg_t > 0 else "\u2014",
            "anom_avg_isk":  fisk(a_avg_i) if a_avg_i > 0 else "\u2014",
            "anom_best_isk": fisk(a_best)  if a_best > 0  else "\u2014",
            "anom_cur_time": fdur(a_cur)   if a_cur > 0   else "\u2014",
        }

        self._st = "stopped"
        self._update_buttons()

    # ── Session management ──────────────────────────────────────────
    # Sauvegarde la session et remet tout à zéro
    def _reset(self):
        d = self.data
        char_name = self.char_name
        try: tax_pct = float(self.tax_var.get())
        except:
            tax_pct = DEF_TAX
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            pass
        self._anom_close_current()
        if not self._session_saved:
            save_session(d, char_name, tax_pct)
        self._session_saved = False
        self.data.reset()
        self._frozen = None
        self._anom_paused_secs = 0
        if self.fh:
            self.fh.close()
            self.fh = None
        self.fp = 0
        # Keep self.cf (the character's gamelog path) intact so Play (_go) can
        # restart the same character — closing fh forces _go to re-open from EOF.
        self._close_chatlog()
        self._st = "stopped"
        self._update_buttons()

    # Sauvegarde la session et réinitialise pour le prochain site
    def _next_site(self):
        # Identical behaviour to RESET — save the session, then clear all
        # counters/state. Delegates to _reset so the two can never drift apart.
        self._reset()

    # Ouvre la fenêtre de paramètres (ou la met au premier plan)
    def _settings(self):
        if self._sw and self._sw.w.winfo_exists():
            self._sw.w.lift()
            return
        self._sw = Settings(self.root, self)

    # Ouvre la fenêtre d'historique (ou la met au premier plan)
    def _show_history(self):
        if self._hw and self._hw.w.winfo_exists():
            self._hw.w.lift()
            return
        self._hw = HistoryWindow(self.root, self, char_name=self.char_name)

    # Relit le log courant pour récupérer les bounties récentes et initialiser le compteur de session
    def _backfill_bounties(self):
        """Scan gamelog for bounties from the last BACKFILL_MINS minutes and add them to the session."""
        if not self.cf or not os.path.exists(self.cf):
            return
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=BACKFILL_MINS)
        earliest_ts = None
        bounties_found = 0
        total_isk = 0
        
        try:
            # Stream the file line-by-line instead of readlines() so a long
            # session's multi-MB gamelog isn't fully materialised on the UI thread.
            with open(self.cf, "r", encoding="utf-8", errors="replace") as f:
                for raw in f:
                    raw = raw.rstrip("\n\r")
                    if not raw.strip():
                        continue

                    # Extract timestamp
                    m = RE_TS.search(raw)
                    if not m:
                        continue
                    try:
                        ts = datetime.strptime(m.group(1), "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except Exception:
                        continue

                    # Skip lines older than cutoff
                    if ts < cutoff:
                        continue

                    # Vérifie si la ligne est un paiement de bounty
                    m = RE_BT.search(raw)
                    if m:
                        amt = pnum(m.group(1))
                        self.data.bg += amt
                        self.data.bc += 1
                        # Drive the anomaly (site) state machine too, mirroring the
                        # live _parse path, so backfilled kills populate site
                        # count/ISK instead of leaving the anomaly panel at zero.
                        self._anom_combat_event(ts)
                        self._anom_add_bounty(ts, amt)
                        bounties_found += 1
                        total_isk += amt

                        # Mémorise le timestamp de la bounty la plus ancienne
                        if earliest_ts is None or ts < earliest_ts:
                            earliest_ts = ts

            # Ajuste le t0 de la session sur la première bounty retrouvée
            if earliest_ts:
                self.data.t0 = earliest_ts
                now_str = datetime.now().strftime("%H:%M:%S")
                self.data.alerts.append((now_str, "INFO", f"Backfilled {bounties_found} kills ({fiskf(total_isk)} ISK)"))
        
        except Exception:
            pass

    # Lit les nouvelles lignes du fichier log depuis la dernière position
    def _read(self):
        if not self.fh: return
        self.fh.seek(self.fp)
        for l in self.fh.readlines():
            l = l.rstrip("\n\r")
            if l.strip():
                self._parse(l)
        self.fp = self.fh.tell()

    # Détecte un nouveau gamelog pour ce personnage (EVE écrit un nouveau fichier
    # par session de jeu au relog/undock) et bascule dessus, pour qu'une session
    # active continue de compter au lieu de lire indéfiniment un fichier périmé.
    def _check_gamelog_rotation(self):
        now = time.monotonic()
        if now - self._last_gamelog_scan < 5:
            return
        self._last_gamelog_scan = now
        if not self.cf:
            return
        try:
            latest = scan_logs(self.log_path).get(self.char_id)
        except Exception:
            return
        if not latest or os.path.normcase(latest) == os.path.normcase(self.cf):
            return
        # Ne bascule que vers un fichier strictement plus récent que le courant.
        try:
            if os.path.getmtime(latest) <= os.path.getmtime(self.cf):
                return
        except Exception:
            return
        try:
            if self.fh:
                self.fh.close()
        except Exception:
            pass
        try:
            self.fh = open(latest, "r", encoding="utf-8", errors="replace")
            self.fp = 0                       # nouveau fichier de session — lire depuis le début
            self.cf = latest
            now_str = datetime.now().strftime("%H:%M:%S")
            self.data.alerts.append((now_str, "INFO", "Switched to new gamelog"))
        except Exception:
            self.fh = None

    # Retourne le chemin du fichier chatlog le plus récent dans le dossier EVE
    def _find_latest_chatlog(self):
        chat_dir = self.chat_path
        if not os.path.isdir(chat_dir): return None
        best = None
        best_mt = 0
        # EVE chatlog files are Agent_<date>_<time>_<charid>.txt. Match only THIS
        # character's logs, otherwise every window tails whichever character's
        # Agent log is globally newest and misattributes its WEB alerts.
        suffix = f"_{self.char_id}.txt"
        try:
            for fn in os.listdir(chat_dir):
                if RE_CHATLOG_FN.match(fn) and fn.endswith(suffix):
                    fp = os.path.join(chat_dir, fn)
                    mt = os.path.getmtime(fp)
                    if mt > best_mt:
                        best = fp
                        best_mt = mt
        except Exception:
            pass
        return best

    # Ouvre le chatlog le plus récent en UTF-16 et positionne le curseur en fin de fichier
    def _open_chatlog(self):
        fp = self._find_latest_chatlog()
        if not fp: return
        if fp != self._chat_file:
            if self._chat_fh:
                try: self._chat_fh.close()
                except Exception:
                    pass
            try:
                self._chat_fh = open(fp, "r", encoding="utf-16", errors="ignore")
                self._chat_fh.seek(0, 2)
                self._chat_fp = self._chat_fh.tell()
                self._chat_file = fp
            except Exception:
                self._chat_fh = None
                self._chat_file = None

    # Lit les nouvelles lignes du chatlog depuis la dernière position
    def _read_chatlog(self):
        if not self._chat_fh: return
        try:
            self._chat_fh.seek(self._chat_fp)
            for l in self._chat_fh.readlines():
                l = l.rstrip("\n\r")
                if l.strip():
                    self._parse_chatlog(l)
            self._chat_fp = self._chat_fh.tell()
        except Exception:
            pass

    # Analyse une ligne du chatlog et déclenche les alertes (ex: web, scram)
    def _parse_chatlog(self, raw):
        d = self.data
        now_str = datetime.now().strftime("%H:%M:%S")

        # WEB fires as (notify) in chatlog (unlike SCRAM which is in combat log)
        m = RE_WEB.search(raw)
        if m:
            npc = shtml(m.group(1).strip())
            d.alerts.append((now_str, "WEB", f"\u26A0 WEBBED by {npc}!"))
            self._flash_alert()
            return

        # Accepted-mission line names the current mission (drives the mission
        # tracker + history 'last_mission'; previously RE_MSN_ACCEPT was unused
        # so mission_name never populated).
        m = RE_MSN_ACCEPT.search(raw)
        if m:
            d.mission_name = m.group(1).strip()
            d.mission_obj_met = False
            d.alerts.append((now_str, "MSN", f"Accepted: {d.mission_name[:32]}"))
            return

    # Ferme le handle du chatlog et réinitialise les variables associées
    def _close_chatlog(self):
        if self._chat_fh:
            try: self._chat_fh.close()
            except Exception:
                pass
            self._chat_fh = None
            self._chat_file = None
            self._chat_fp = 0

    # Reconstruit entièrement l'interface en appliquant le thème courant sans perdre l'état
    def _apply_theme_live(self):
        """Re-colour every widget in-place — no rebuild, no flicker."""

        # 1. Snapshot current (old) palette BEFORE updating globals
        old = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
               T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
               CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]

        # 2. Update globals to the new theme
        apply_theme_colors(self._current_theme)

        # 3. New palette (same order)
        new = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
               T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
               CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]

        # 4. Build old-hex → new-hex replacement map (only changed entries)
        remap = {o.lower(): n for o, n in zip(old, new) if o.lower() != n.lower()}
        if not remap:
            return

        # 5. Walk every widget and swap matching colours
        PROPS = ('bg', 'fg', 'highlightbackground', 'highlightcolor',
                 'insertbackground', 'selectbackground',
                 'activebackground', 'activeforeground')

        def _walk(widget):
            for prop in PROPS:
                try:
                    v = widget.cget(prop)
                    if isinstance(v, str) and v.lower() in remap:
                        widget.config(**{prop: remap[v.lower()]})
                except Exception:
                    pass
            for child in widget.winfo_children():
                _walk(child)

        # Main window
        _walk(self.root)
        self.root.configure(bg=BG,
                            highlightbackground=BDG, highlightcolor=BDG)

        # Detached windows
        for attr in ('_isk_window', '_msn_window',
                     '_anom_window', '_alert_window'):
            win = getattr(self, attr, None)
            if win:
                try:
                    if win.w.winfo_exists():
                        _walk(win.w)
                        win.w.configure(bg=BG,
                                        highlightbackground=BDG,
                                        highlightcolor=BDG)
                except Exception:
                    pass

        # DPS overlay (owned by MainUI) — keep its color-keyed background and
        # re-assert its mode chrome (backdrop / contour / ✕ / grip) after the walk.
        try:
            _mu = getattr(self, "_main_ui", None)
            ov = _mu._overlays.get(self.char_id) if _mu else None
            if ov and ov.w.winfo_exists():
                _walk(ov.w)
                ov.w.configure(bg=OVERLAY_KEY)
                ov._apply_mode()
        except Exception:
            pass

        # Settings / History Toplevels (if open)
        for attr in ('_sw', '_hw'):
            obj = getattr(self, attr, None)
            if obj:
                try:
                    if obj.w.winfo_exists():
                        _walk(obj.w)
                except Exception:
                    pass

        # 6. Refresh ttk combobox style and button states
        self._style()
        self._update_buttons()

    # Démarre ou reprend la session de ratting pour le personnage sélectionné
    def _go(self):
        if not self.cf:
            return
        was_paused    = (self._st == "paused")
        was_stopped   = (self._st == "stopped" and self.data.acc_sec > 0 and self.cf is not None)
        was_suspended = was_paused or was_stopped
        self._st = "running"
        self._frozen = None
        self._session_saved = False
        self._update_buttons()

        fp = self.cf
        already_open = (self.fh and not self.fh.closed
                        and os.path.normcase(self.fh.name) == os.path.normcase(fp))
        if not already_open:
            if self.fh:
                self.fh.close()
            self.fh = open(fp, "r", encoding="utf-8", errors="replace")
            self.fh.seek(0, 2)
            self.fp = self.fh.tell()
            self.data.reset()
            self._anom_paused_secs = 0
            self._backfill_bounties()
            if self.data.t0 is None:
                self.data.t0 = datetime.now(timezone.utc)
        elif was_suspended:
            self.data.t0 = datetime.now(timezone.utc)
            if self.fh:
                self.fh.seek(0, 2)
                self.fp = self.fh.tell()
            if self.data.anom_current and self._anom_paused_secs > 0:
                self.data.anom_current["start"] = (
                    datetime.now(timezone.utc) - timedelta(seconds=self._anom_paused_secs))
            if self.data.anom_current and self.data.anom_last_combat:
                self.data.anom_last_combat = datetime.now(timezone.utc)
                self._anom_last_wall  = time.monotonic()
                self._anom_start_wall = time.monotonic() - self._anom_paused_secs

        self._open_chatlog()
        if was_suspended and self._chat_fh:
            try:
                self._chat_fh.seek(0, 2)
                self._chat_fp = self._chat_fh.tell()
            except Exception:
                pass

    # Met en pause la session (fige les timers) ou la reprend si déjà en pause
    def _pause(self):
        if self._st == "running":
            self._st = "paused"

            # Freeze session timer
            if self.data.t0:
                self.data.acc_sec += (datetime.now(timezone.utc) - self.data.t0).total_seconds()
                self.data.t0 = None

            # Freeze anomaly current site timer
            if self.data.anom_current and self._anom_start_wall:
                self._anom_paused_secs = time.monotonic() - self._anom_start_wall
            else:
                self._anom_paused_secs = 0
        elif self._st == "paused":
            self._go()
            return
        self._update_buttons()

    # Détache un panneau de la fenêtre principale dans sa propre fenêtre flottante
    def _detach(self, section):
        if section == "isk" and not self._isk_detached:
            self._isk_detached = True
            self._isk_container.grid_remove()
            self._sep_isk_msn.grid_remove()
            self._isk_window = DetachedWindow(self.root, self, "ISK TRACKER", CD, "isk", lambda parent, detached: self._build_isk(parent, detached=True), char_name=self.char_name)
            self._fit()
        elif section == "msn" and not self._msn_detached:
            self._msn_detached = True
            self._msn_container.grid_remove()
            self._sep_isk_msn.grid_remove()
            self._msn_window = DetachedWindow(self.root, self, "MISSION TRACKER", C_MSN, "msn", lambda parent, detached: self._build_missions(parent, detached=True), char_name=self.char_name)
            self._fit()
        elif section == "anom" and not self._anom_detached:
            self._anom_detached = True
            self._anom_container.grid_remove()
            self._sep_msn_anom.grid_remove()
            self._anom_window = DetachedWindow(self.root, self, "ANOMALY TRACKER", C_ANOM, "anom", lambda parent, detached: self._build_anomalies(parent, detached=True), char_name=self.char_name)
            self._fit()
        elif section == "alert" and not self._alert_detached:
            self._alert_detached = True
            self._alert_container.grid_remove()
            self._sep_alert_isk.grid_remove()
            self._alert_window = DetachedWindow(self.root, self, "ALERTS", T0, "alert", lambda parent, detached: self._build_alerts(parent, detached=True), char_name=self.char_name)
            self._fit()

    # Réintègre un panneau détaché dans la fenêtre principale et reconstruit son contenu
    def _reattach(self, section):
        if section == "isk":
            self._isk_detached = False
            self._isk_window = None
            self._isk_det_labels = {}
            for w in self._isk_container.winfo_children():
                w.destroy()
            self._build_isk(self._isk_container, detached=False)
            self._isk_container.grid()
            self._sep_isk_msn.grid()
            self._fit()
        elif section == "msn":
            self._msn_detached = False
            self._msn_window = None
            self._msn_det_labels = {}
            for w in self._msn_container.winfo_children():
                w.destroy()
            self._build_missions(self._msn_container, detached=False)
            self._msn_container.grid()
            self._sep_isk_msn.grid()
            self._fit()
        elif section == "anom":
            self._anom_detached = False
            self._anom_window = None
            self._anom_det_labels = {}
            for w in self._anom_container.winfo_children():
                w.destroy()
            self._build_anomalies(self._anom_container, detached=False)
            self._anom_container.grid()
            self._sep_msn_anom.grid()
            self._fit()
        elif section == "alert":
            self._alert_detached = False
            self._alert_window = None
            for w in self._alert_container.winfo_children():
                w.destroy()
            self._build_alerts(self._alert_container, detached=False)
            self._alert_container.grid()
            self._sep_alert_isk.grid()
            self._fit()

    # Enregistre un événement de combat et crée/ferme une anomalie selon les gaps
    def _anom_combat_event(self, ts):
        d = self.data
        if d.anom_current and d.anom_last_combat:
            gap = (ts - d.anom_last_combat).total_seconds()
            if gap > self.anom_gap:
                d.anom_current["end"] = d.anom_last_combat
                d.anom_completed.append(d.anom_current)
                d.anom_current = None
        if d.anom_current is None:
            d.anom_current = {"start": ts, "end": None, "kills": 0, "isk": 0}
            self._anom_start_wall = time.monotonic()
        d.anom_last_combat = ts
        self._anom_last_wall = time.monotonic()

    # Incrémente le compteur de kills et ISK de l'anomalie en cours
    def _anom_add_bounty(self, ts, amount):
        d = self.data
        if d.anom_current:
            d.anom_current["kills"] += 1
            d.anom_current["isk"]   += amount

    # Ferme manuellement l'anomalie en cours et l'archive dans la liste des complétées
    def _anom_close_current(self):
        d = self.data
        if d.anom_current:
            d.anom_current["end"] = d.anom_last_combat or datetime.now(timezone.utc)
            d.anom_completed.append(d.anom_current)
            d.anom_current = None

    # Vérifie si le gap de combat dépasse le seuil et clôture l'anomalie si nécessaire
    def _anom_check_gap(self):
        d = self.data
        if d.anom_current and self._anom_last_wall:
            gap = time.monotonic() - self._anom_last_wall
            if gap > self.anom_gap:
                d.anom_current["end"] = d.anom_last_combat
                d.anom_completed.append(d.anom_current)
                d.anom_current = None

    # Calcule et retourne les statistiques agrégées sur toutes les anomalies complétées
    def _anom_stats(self):
        d = self.data
        completed = d.anom_completed
        n = len(completed)
        if n > 0:
            total_time = sum(max(0, (a["end"] - a["start"]).total_seconds()) for a in completed if a["end"] and a["start"])
            avg_time = total_time / n
        else:
            avg_time = 0
        avg_isk  = sum(a["isk"] for a in completed) / n if n > 0 else 0
        best_isk = max((a["isk"] for a in completed), default=0)
        cur_secs = (time.monotonic() - self._anom_start_wall) if (d.anom_current and self._anom_start_wall) else 0
        return n, avg_time, avg_isk, best_isk, cur_secs

# ── Global settings popup (opened from MainUI header) ────────────────
class MainUISettings:

    def __init__(self, parent_root, main_ui):
        self.main_ui = main_ui
        cfg = main_ui.cfg
        self._dx = self._dy = 0

        self.w = tk.Toplevel(parent_root)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG,
                         highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", cfg.get("alpha", DEF_ALPHA))

        saved = cfg.get("main_ui", {}).get("settings_pos", "")
        if saved:
            self.w.geometry(f"340x320{saved}")
        else:
            self.w.geometry(
                f"340x320+{parent_root.winfo_x()+30}+{parent_root.winfo_y()+40}")

        hdr = tk.Frame(self.w, bg=BG_H, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>",
                 lambda e: (setattr(self, "_dx", e.x), setattr(self, "_dy", e.y)))
        hdr.bind("<B1-Motion>",
                 lambda e: self.w.geometry(
                     f"+{self.w.winfo_x()+e.x-self._dx}"
                     f"+{self.w.winfo_y()+e.y-self._dy}"))
        hdr.bind("<ButtonRelease-1>", lambda e: self._save_pos())

        tk.Frame(hdr, bg=T0, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="  ⚙ SETTINGS",
                 font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                 bg=BG_H, fg=T0).pack(side="left")
        xb = tk.Label(hdr, text="✕",
                      font=tkfont.Font(family="Consolas", size=12, weight="bold"),
                      bg=BG_H, fg=TD, padx=8, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self.w.destroy())
        xb.bind("<Enter>",    lambda e: xb.config(fg=CR))
        xb.bind("<Leave>",    lambda e: xb.config(fg=TD))
        tk.Frame(self.w, bg=BDG, height=1).pack(fill="x")

        body = tk.Frame(self.w, bg=BG_POP)
        body.pack(fill="both", expand=True, padx=10, pady=10)
        lf = tkfont.Font(family="Consolas", size=9)
        ek = dict(font=tkfont.Font(family="Consolas", size=10), bg=BG_C, fg=TB,
                  insertbackground=TB, relief="flat", bd=0,
                  highlightthickness=1, highlightbackground=BD, highlightcolor=BDG)

        tk.Label(body, text="GAMELOGS PATH", font=lf, bg=BG_POP, fg=TD).pack(
            anchor="w", pady=(0, 2))
        self.pv = tk.StringVar(value=cfg.get("log_path", DEF_PATH))
        tk.Entry(body, textvariable=self.pv, width=36, **ek).pack(fill="x", pady=(0, 4))

        tk.Label(body, text="CHATLOGS PATH", font=lf, bg=BG_POP, fg=TD).pack(
            anchor="w", pady=(0, 2))
        self.cpv = tk.StringVar(value=cfg.get("chat_path", DEF_CHAT))
        tk.Entry(body, textvariable=self.cpv, width=36, **ek).pack(fill="x", pady=(0, 8))

        r = tk.Frame(body, bg=BG_POP)
        r.pack(fill="x", pady=(0, 6))
        tk.Label(r, text="OPACITY %", font=lf, bg=BG_POP, fg=TD).pack(side="left")
        self.av = tk.StringVar(value=str(int(cfg.get("alpha", DEF_ALPHA) * 100)))
        tk.Entry(r, textvariable=self.av, width=8, **ek).pack(side="right")

        r2 = tk.Frame(body, bg=BG_POP)
        r2.pack(fill="x", pady=(0, 6))
        tk.Label(r2, text="CORP TAX %", font=lf, bg=BG_POP, fg=TD).pack(side="left")
        self.tv = tk.StringVar(value=cfg.get("tax", str(DEF_TAX)))
        tk.Entry(r2, textvariable=self.tv, width=8, **ek).pack(side="right")

        tk.Label(body, text="THEME", font=lf, bg=BG_POP, fg=TD).pack(
            anchor="w", pady=(0, 2))
        self._theme_var = tk.StringVar(value=cfg.get("last_theme", THEME_DEFAULT))
        self._theme_cb = ttk.Combobox(
            body, textvariable=self._theme_var, state="readonly",
            style="E.TCombobox",
            font=tkfont.Font(family="Consolas", size=9),
            values=THEME_NAMES)
        self._theme_cb.pack(fill="x", pady=(0, 8))

        r3 = tk.Frame(body, bg=BG_POP)
        r3.pack(fill="x", pady=(0, 8))
        self.bgm_var = tk.BooleanVar(value=cfg.get("bg_monitor", False))
        bgm_lbl = tk.Label(r3, text="BACKGROUND MONITORING", font=lf, bg=BG_POP, fg=TD)
        bgm_lbl.pack(side="left")
        self._bgm_box = tk.Label(r3, text="☑" if self.bgm_var.get() else "☐",
                                 font=tkfont.Font(family="Consolas", size=12),
                                 bg=BG_POP, fg=CA if self.bgm_var.get() else TD,
                                 cursor="hand2")
        self._bgm_box.pack(side="right")
        def _toggle_bgm(e=None):
            self.bgm_var.set(not self.bgm_var.get())
            on = self.bgm_var.get()
            self._bgm_box.config(text="☑" if on else "☐", fg=CA if on else TD)
            self._check_dirty()
        self._bgm_box.bind("<Button-1>", _toggle_bgm)
        bgm_lbl.bind("<Button-1>", _toggle_bgm)

        # Snapshot of values at open time — used to detect changes
        self._snap = {
            "log":   self.pv.get(),
            "chat":  self.cpv.get(),
            "alpha": self.av.get(),
            "tax":   self.tv.get(),
            "theme": self._theme_var.get(),
            "bgm":   self.bgm_var.get(),
        }

        ap_font = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._ap = tk.Label(body, text="✔ APPLY", font=ap_font,
                            bg=BG_POP, fg=TD, padx=12)
        self._ap.pack(side="right", pady=(6, 0))
        self._ap_dirty = False

        # Trace StringVars so any keystroke updates dirty state
        for var in (self.pv, self.cpv, self.av, self.tv, self._theme_var):
            var.trace_add("write", lambda *_: self._check_dirty())

    def _check_dirty(self):
        dirty = (
            self.pv.get()          != self._snap["log"]   or
            self.cpv.get()         != self._snap["chat"]  or
            self.av.get()          != self._snap["alpha"] or
            self.tv.get()          != self._snap["tax"]   or
            self._theme_var.get()  != self._snap["theme"] or
            self.bgm_var.get()     != self._snap["bgm"]
        )
        if dirty == self._ap_dirty:
            return
        self._ap_dirty = dirty
        if dirty:
            self._ap.config(fg=CA, cursor="hand2")
            self._ap.bind("<Button-1>", lambda e: self._apply())
            self._ap.bind("<Enter>",    lambda e: self._ap.config(bg=BDG))
            self._ap.bind("<Leave>",    lambda e: self._ap.config(bg=BG_POP))
        else:
            self._ap.config(fg=TD, cursor="")
            self._ap.unbind("<Button-1>")
            self._ap.unbind("<Enter>")
            self._ap.unbind("<Leave>")
            self._ap.config(bg=BG_POP)

    def _save_pos(self):
        try:
            self.main_ui.cfg.setdefault("main_ui", {})["settings_pos"] = (
                f"+{self.w.winfo_x()}+{self.w.winfo_y()}")
            save_config(self.main_ui.cfg)
        except Exception:
            pass

    def _apply(self):
        mu  = self.main_ui
        cfg = mu.cfg
        cfg["log_path"]  = self.pv.get().strip()
        cfg["chat_path"] = self.cpv.get().strip()
        for win in mu._windows.values():
            win.log_path  = cfg["log_path"]
            win.chat_path = cfg["chat_path"]
        # Re-point the watchdog observer at the new directories
        try:
            mu._start_log_observer()
        except Exception:
            pass

        try:
            v     = max(20, min(100, int(self.av.get())))
            alpha = v / 100
            cfg["alpha"] = alpha
            mu.root.attributes("-alpha", alpha)
            # Apply to this Settings window itself
            if self.w.winfo_exists():
                self.w.attributes("-alpha", alpha)
            # Apply to Fleet Manager if open
            fm = mu._fleet_mgr_win
            if fm and fm.winfo_exists():
                fm.attributes("-alpha", alpha)
            for win in mu._windows.values():
                win.alpha = alpha
                if win.root.winfo_exists():
                    win.root.attributes("-alpha", alpha)
                for attr in ("_isk_window", "_msn_window",
                             "_anom_window", "_alert_window"):
                    dw = getattr(win, attr, None)
                    if dw and dw.w.winfo_exists():
                        dw.w.attributes("-alpha", alpha)
                ov = mu._overlays.get(win.char_id)
                if ov and ov.w.winfo_exists():
                    ov.apply_alpha(alpha)
        except Exception:
            pass

        try:
            tax_str = self.tv.get().strip()
            float(tax_str)   # validate
            cfg["tax"] = tax_str
            for win in mu._windows.values():
                win.tax_var.set(tax_str)
        except Exception:
            pass

        new_theme = self._theme_var.get()
        if new_theme != cfg.get("last_theme", THEME_DEFAULT):
            # Snapshot old palette BEFORE changing globals (must be done once for all windows)
            old_pal = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
                       T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
                       CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]
            cfg["last_theme"] = new_theme
            apply_theme_colors(new_theme)
            new_pal = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
                       T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
                       CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]
            remap = {o.lower(): n for o, n in zip(old_pal, new_pal) if o.lower() != n.lower()}

            PROPS = ('bg', 'fg', 'highlightbackground', 'highlightcolor',
                     'insertbackground', 'selectbackground',
                     'activebackground', 'activeforeground')

            def _walk(widget):
                for prop in PROPS:
                    try:
                        v = widget.cget(prop)
                        if isinstance(v, str) and v.lower() in remap:
                            widget.config(**{prop: remap[v.lower()]})
                    except Exception:
                        pass
                for child in widget.winfo_children():
                    _walk(child)

            if remap:
                # MainUI overview window
                _walk(mu.root)
                # Settings popup itself
                if self.w.winfo_exists():
                    _walk(self.w)
                # Every CharacterWindow + its detached panels + open popups
                for win in mu._windows.values():
                    if not win.root.winfo_exists():
                        continue
                    win._current_theme = new_theme
                    win.char_cfg["theme"] = new_theme
                    _walk(win.root)
                    win.root.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG)
                    for attr in ('_isk_window', '_msn_window',
                                 '_anom_window', '_alert_window'):
                        dw = getattr(win, attr, None)
                        if dw and dw.w.winfo_exists():
                            _walk(dw.w)
                            dw.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG)
                    ov = mu._overlays.get(win.char_id)
                    if ov and ov.w.winfo_exists():
                        _walk(ov.w)
                        ov.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG)
                    for attr in ('_sw', '_hw'):
                        obj = getattr(win, attr, None)
                        if obj and obj.w.winfo_exists():
                            _walk(obj.w)
                    try:
                        win._style()
                        win._update_buttons()
                    except Exception:
                        pass

        cfg["bg_monitor"] = self.bgm_var.get()

        save_config(cfg)

        # Reset snapshot so APPLY goes back to grayed-out
        self._snap = {
            "log":   self.pv.get(),
            "chat":  self.cpv.get(),
            "alpha": self.av.get(),
            "tax":   self.tv.get(),
            "theme": self._theme_var.get(),
            "bgm":   self.bgm_var.get(),
        }
        self._check_dirty()


# ── Fleet manager popup (add / remove characters from active fleet) ───
class FleetManager:

    def __init__(self, parent_root, main_ui):
        self.main_ui = main_ui
        self._dx = self._dy = 0

        self.w = tk.Toplevel(parent_root)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG,
                         highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", main_ui.cfg.get("alpha", DEF_ALPHA))

        saved = main_ui.cfg.get("main_ui", {}).get("fleet_mgr_pos", "")
        if saved:
            self.w.geometry(f"300x400{saved}")
        else:
            self.w.geometry(
                f"300x400+{parent_root.winfo_x()+40}+{parent_root.winfo_y()+44}")

        F8B  = tkfont.Font(family="Consolas", size=8,  weight="bold")
        F10B = tkfont.Font(family="Consolas", size=10, weight="bold")
        F12B = tkfont.Font(family="Consolas", size=12, weight="bold")

        hdr = tk.Frame(self.w, bg=BG_H, height=32)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>",
                 lambda e: (setattr(self, "_dx", e.x), setattr(self, "_dy", e.y)))
        hdr.bind("<B1-Motion>",
                 lambda e: self.w.geometry(
                     f"+{self.w.winfo_x()+e.x-self._dx}"
                     f"+{self.w.winfo_y()+e.y-self._dy}"))
        hdr.bind("<ButtonRelease-1>", lambda e: self._save_pos())

        tk.Frame(hdr, bg=CI, width=3).pack(side="left", fill="y")
        tk.Label(hdr, text="  ◈ FLEET MANAGER",
                 font=F10B, bg=BG_H, fg=T0).pack(side="left")
        xb = tk.Label(hdr, text="✕", font=F12B,
                      bg=BG_H, fg=TD, padx=8, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self.w.destroy())
        xb.bind("<Enter>",    lambda e: xb.config(fg=CR))
        xb.bind("<Leave>",    lambda e: xb.config(fg=TD))
        tk.Frame(self.w, bg=BDG, height=1).pack(fill="x")

        # Subtitle
        tk.Label(self.w, text="Toggle characters in the active fleet.",
                 font=tkfont.Font(family="Consolas", size=8),
                 bg=BG, fg=TD).pack(anchor="w", padx=10, pady=(6, 0))

        tk.Frame(self.w, bg=BD, height=1).pack(fill="x", padx=10, pady=(4, 0))

        # Scrollable character list
        canvas = tk.Canvas(self.w, bg=BG, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=0, pady=0)
        self._list_frame = tk.Frame(canvas, bg=BG)
        _win = canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        def _fm_fix_sr(e, c=canvas):
            bb = c.bbox("all")
            if bb:
                c.configure(scrollregion=(0, 0, bb[2], bb[3]))

        def _fm_scroll(ev, c=canvas):
            c.yview_scroll(int(-1 * (ev.delta / 120)), "units")
            if c.yview()[0] <= 0:
                c.yview_moveto(0)

        self._list_frame.bind("<Configure>", _fm_fix_sr)
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(_win, width=e.width))
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _fm_scroll))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        tk.Frame(self.w, bg=BD, height=1).pack(fill="x", padx=10, pady=(0, 4))

        # Refresh button at the bottom
        bot = tk.Frame(self.w, bg=BG)
        bot.pack(fill="x", padx=10, pady=(0, 8))
        refresh_lbl = tk.Label(bot, text="⟳ REFRESH",
                               font=F8B, bg=BG, fg=TD, cursor="hand2")
        refresh_lbl.pack(side="left")
        refresh_lbl.bind("<Button-1>", lambda e: self._populate())
        refresh_lbl.bind("<Enter>",    lambda e: refresh_lbl.config(fg=T0))
        refresh_lbl.bind("<Leave>",    lambda e: refresh_lbl.config(fg=TD))

        self._F8B = F8B
        self._F9  = tkfont.Font(family="Consolas", size=9)
        self._populate()

    def _populate(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        mu       = self.main_ui
        cfg      = mu.cfg
        char_map = cfg.setdefault("chars", {})
        log_path = cfg.get("log_path", DEF_PATH)

        # Scan logs fresh to get all known characters (including ignored ones)
        cf = scan_logs(log_path)
        if not cf:
            tk.Label(self._list_frame, text="No characters found in logs.",
                     font=self._F9, bg=BG, fg=TD).pack(padx=10, pady=6)
            return

        # Merge: chars from logs + chars already in windows (in case log file gone)
        all_chars = {}
        for char_id, log_file in cf.items():
            name = rlisten(log_file) or f"Unknown ({char_id})"
            all_chars[char_id] = name
        for char_id, win in mu._windows.items():
            if char_id not in all_chars:
                all_chars[char_id] = win.char_name

        for char_id, char_name in sorted(all_chars.items(), key=lambda x: x[1].lower()):
            ignored = char_map.get(char_id, {}).get("ignored", False)
            active  = char_id in mu._windows and not ignored

            row = tk.Frame(self._list_frame, bg=BG)
            row.pack(fill="x", padx=8, pady=2)

            name_fg = T0 if active else TD
            tk.Label(row, text=f"★ {char_name[:22]}",
                     font=self._F9, bg=BG, fg=name_fg, anchor="w",
                     width=22).pack(side="left")

            btn_text = "✔ ACTIVE" if active else "✗ IGNORE"
            btn_fg   = CI if active else CR
            btn = tk.Label(row, text=btn_text, font=self._F8B,
                           bg=BG, fg=btn_fg, cursor="hand2", anchor="e")
            btn.pack(side="right")
            btn.bind("<Button-1>",
                     lambda e, cid=char_id, cn=char_name, lf=cf.get(char_id, ""):
                         self._toggle(cid, cn, lf))
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=T0))
            btn.bind("<Leave>", lambda e, b=btn, a=active: b.config(fg=CI if a else CR))

    def _toggle(self, char_id: str, char_name: str, log_file: str):
        mu       = self.main_ui
        cfg      = mu.cfg
        char_map = cfg.setdefault("chars", {})
        char_map.setdefault(char_id, {})

        currently_active = char_id in mu._windows

        if currently_active:
            # Remove from fleet — close overlay + window and mark ignored
            ov = mu._overlays.get(char_id)
            if ov:
                try: ov.close()
                except Exception: pass
            win = mu._windows.pop(char_id, None)
            if win and win.root.winfo_exists():
                win._quit()
            char_map[char_id]["ignored"] = True
        else:
            # Add to fleet — clear ignored flag and spawn window
            char_map[char_id]["ignored"] = False
            if log_file and char_id not in mu._windows:
                win = CharacterWindow(mu.root, mu, char_id, char_name, log_file, cfg)
                mu._windows[char_id] = win
                if char_map[char_id].get("show", True):
                    win.root.deiconify()

        save_config(cfg)
        mu._rebuild_rows()
        self._populate()   # refresh the list to reflect new state

    def _save_pos(self):
        try:
            self.main_ui.cfg.setdefault("main_ui", {})["fleet_mgr_pos"] = (
                f"+{self.w.winfo_x()}+{self.w.winfo_y()}")
            save_config(self.main_ui.cfg)
        except Exception:
            pass


# ── Fleet overview ────────────────────────────────────────────────────
# ── Watchdog handler: wakes log readers on real file I/O (optional) ───
class _LogEventHandler(FileSystemEventHandler):
    """Debounced: coalesces bursts of file events into one read on the main thread."""
    def __init__(self, main_ui):
        self._mu = main_ui
        self._pending = None

    def _schedule(self):
        if self._pending is not None:
            return
        def _fire():
            self._pending = None
            try:
                self._mu._wake_readers()
            except Exception:
                pass
        try:
            self._pending = self._mu.root.after(300, _fire)
        except Exception:
            self._pending = None

    def on_modified(self, event):
        if not getattr(event, "is_directory", False):
            try:
                self._mu.root.after(0, self._schedule)
            except Exception:
                pass

    def on_created(self, event):
        self.on_modified(event)


class MainUI:

    MAIN_W    = 420   # default & minimum window width
    # Treeview column pixel widths (fixed columns; char column stretches)
    _TV_NET  = 100   # TOTAL NET (wide enough for the "TOTAL NET" header so it doesn't overflow)
    _TV_HR   = 85    # ISK/HR
    _TV_SES  = 68    # SESSION (HH:MM:SS)
    _TV_DPS  = 30    # DPS overlay toggle glyph

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.attributes("-topmost", True)

        self.cfg = load_config()
        apply_theme_colors(self.cfg.get("last_theme", THEME_DEFAULT))
        self.root.attributes("-alpha", self.cfg.get("alpha", DEF_ALPHA))

        self._windows: dict = {}   # char_id → CharacterWindow
        self._overlays: dict = {}  # char_id → DPSOverlay
        self._rows:    dict = {}   # char_id → iid in _tree (iid == char_id)
        self._tree            = None
        self._total_bnt_lbl   = None
        self._total_net_lbl   = None
        self._health_job      = None
        self._settings_win    = None
        self._fleet_mgr_win   = None
        self._label_vals: dict = {}   # id(label) → {text, fg} — for fleet-total labels
        self._tv_cache:   dict = {}   # (iid, col) → last value set in tree
        self._dx = self._dy = 0
        self._rw = self._rh = self._rx = self._ry = self._wx = self._wy = 0
        self._last_clipboard  = ""  # shared across all CharacterWindows — first to see a paste wins

        self._scan_job       = None
        self._is_collapsed   = False
        self._full_height    = 0
        self._dragging       = False
        self._tray_icon      = None
        self._log_observer   = None   # watchdog Observer (None ⇒ pure timer polling)

        self._build()
        self._restore_geometry()

        # Restore collapsed state if overview was closed while collapsed.
        # _restore_geometry() already set the correct geometry (position + collapsed height).
        # We must NOT call winfo_* here — the window is still withdrawn and returns garbage.
        mui = self.cfg.get("main_ui", {})
        full_h = mui.get("full_height", 0)
        if mui.get("collapsed", False) and full_h > 32:
            self._full_height = full_h
            self._body.pack_forget()
            self._is_collapsed = True

        self._scan()
        self._health_check()
        self._auto_scan()
        self._start_log_observer()

        if _TRAY_OK:
            self.root.after(500, self._init_tray_icon)

        self.root.deiconify()
        self.root.mainloop()

    # ── Scan logs — spawn a CharacterWindow for every new character ───
    def _scan(self):
        cf = scan_logs(self.cfg.get("log_path", DEF_PATH))
        char_map = self.cfg.setdefault("chars", {})
        changed = False

        # Collect truly new characters (never seen before — not in config at all)
        new_chars = {}   # char_id → (char_name, log_file)
        for char_id, log_file in cf.items():
            if char_id in self._windows:
                continue
            if char_id in char_map:
                # Already known — skip if ignored, otherwise spawn
                if char_map[char_id].get("ignored", False):
                    continue
                char_name = rlisten(log_file) or f"Unknown ({char_id})"
                win = CharacterWindow(self.root, self, char_id, char_name, log_file, self.cfg)
                self._windows[char_id] = win
                if char_map[char_id].get("show", True):
                    win.root.deiconify()
                changed = True
            else:
                char_name = rlisten(log_file) or f"Unknown ({char_id})"
                new_chars[char_id] = (char_name, log_file)

        if new_chars:
            selected = self._show_char_picker(new_chars)
            for char_id, (char_name, log_file) in new_chars.items():
                if char_id in selected:
                    win = CharacterWindow(self.root, self, char_id, char_name, log_file, self.cfg)
                    self._windows[char_id] = win
                    if char_map.get(char_id, {}).get("show", True):
                        win.root.deiconify()
                    changed = True
                else:
                    char_map.setdefault(char_id, {})["ignored"] = True
            save_config(self.cfg)

        if changed:
            self._rebuild_rows()

    # ── Character picker popup — returns set of selected char_ids ────────
    def _show_char_picker(self, new_chars: dict) -> set:
        """Modal dialog — user picks which new characters to add to the fleet."""
        dlg = tk.Toplevel(self.root)
        dlg.title("Add Characters to Fleet")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.grab_set()   # modal

        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9  = tkfont.Font(family="Consolas", size=9)

        tk.Label(dlg, text="NEW CHARACTERS DETECTED",
                 font=F8B, bg=BG, fg=TD, pady=6).pack(fill="x", padx=10)
        tk.Label(dlg, text="Select which characters to add to the ratting fleet:",
                 font=F9, bg=BG, fg=T0).pack(padx=10, anchor="w")

        tk.Frame(dlg, bg=BD, height=1).pack(fill="x", padx=10, pady=(4, 0))

        frame = tk.Frame(dlg, bg=BG)
        frame.pack(fill="x", padx=10, pady=4)

        vars_ = {}
        for char_id, (char_name, _) in sorted(new_chars.items(), key=lambda x: x[1][0].lower()):
            var = tk.BooleanVar(value=True)
            vars_[char_id] = var
            cb = tk.Checkbutton(frame, text=char_name, variable=var,
                                 font=F9, bg=BG, fg=T0, selectcolor=BG,
                                 activebackground=BG, activeforeground=CI,
                                 anchor="w")
            cb.pack(fill="x", pady=1)

        tk.Frame(dlg, bg=BD, height=1).pack(fill="x", padx=10, pady=(0, 4))

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=(0, 8), padx=10)

        def _select_all():
            for v in vars_.values(): v.set(True)

        def _select_none():
            for v in vars_.values(): v.set(False)

        def _confirm():
            dlg.destroy()

        tk.Button(btn_row, text="All",  font=F9, bg=BG_H, fg=T0, relief="flat",
                  command=_select_all,  padx=6, pady=2).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="None", font=F9, bg=BG_H, fg=T0, relief="flat",
                  command=_select_none, padx=6, pady=2).pack(side="left", padx=(0, 12))
        tk.Button(btn_row, text="Add Selected", font=F8B, bg=CI, fg=BG, relief="flat",
                  command=_confirm, padx=8, pady=3).pack(side="left")

        # Centre over the main window
        self.root.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2
        dlg.update_idletasks()
        dlg.geometry(f"+{rx - dlg.winfo_width()//2}+{ry - dlg.winfo_height()//2}")

        dlg.wait_window()   # blocks until _confirm() or window closed

        return {cid for cid, v in vars_.items() if v.get()}

    # ── Auto-scan every 10 s so new characters appear without a button ──
    def _auto_scan(self):
        self._scan()
        self._scan_job = self.root.after(10_000, self._auto_scan)

    # ── Event-driven log watching (optional; falls back to timer polling) ──
    def _start_log_observer(self):
        """Watch the gamelog + chatlog dirs so reads fire on real I/O.
        No-op (pure polling) when the watchdog package isn't installed."""
        obs = getattr(self, "_log_observer", None)
        if obs is not None:
            try:
                obs.stop(); obs.join(timeout=2.0)
            except Exception:
                pass
            self._log_observer = None
        if not _WATCHDOG_OK:
            return
        try:
            handler = _LogEventHandler(self)
            obs = Observer()
            seen = set()
            for d in (self.cfg.get("log_path", DEF_PATH), self.cfg.get("chat_path", DEF_CHAT)):
                if d and os.path.isdir(d) and os.path.normcase(d) not in seen:
                    obs.schedule(handler, d, recursive=False)
                    seen.add(os.path.normcase(d))
            obs.start()
            self._log_observer = obs
        except Exception:
            self._log_observer = None

    def _wake_readers(self):
        """File event fired — read new log data for every live character window."""
        for win in list(self._windows.values()):
            try:
                if win.root.winfo_exists():
                    win._read_logs_once()
            except Exception:
                pass

    # ── Build the overview window UI ─────────────────────────────────
    def _build(self):
        F8B  = tkfont.Font(family="Consolas", size=8,  weight="bold")
        F11B = tkfont.Font(family="Consolas", size=11, weight="bold")

        hdr = tk.Frame(self.root, bg=BG_H, height=28)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<Button-1>",
                 lambda e: (setattr(self, "_dx", e.x), setattr(self, "_dy", e.y),
                             setattr(self, "_dragging", False)))
        hdr.bind("<B1-Motion>",
                 lambda e: (setattr(self, "_dragging", True),
                             self.root.geometry(
                                 f"+{self.root.winfo_x()+e.x-self._dx}"
                                 f"+{self.root.winfo_y()+e.y-self._dy}")))
        hdr.bind("<ButtonRelease-1>",
                 lambda e: (self._save_pos(),
                             self.root.after(100, lambda: setattr(self, "_dragging", False))))
        hdr.bind("<Double-Button-1>", self._toggle_collapse)

        tk.Frame(hdr, bg=T0, width=3).pack(side="left", fill="y")
        title_lbl = tk.Label(hdr, text="  ◆ RATTING OVERVIEW",
                             font=F11B, bg=BG_H, fg=T0)
        title_lbl.pack(side="left")
        title_lbl.bind("<Double-Button-1>", self._toggle_collapse)

        xb = tk.Label(hdr, text="✕", font=F11B,
                      bg=BG_H, fg=TD, padx=5, cursor="hand2")
        xb.pack(side="right", fill="y")
        xb.bind("<Button-1>", lambda e: self._quit())
        xb.bind("<Enter>",    lambda e: xb.config(fg=CR))
        xb.bind("<Leave>",    lambda e: xb.config(fg=TD))

        gb = tk.Label(hdr, text="⚙", font=F11B,
                      bg=BG_H, fg=TD, padx=5, cursor="hand2")
        gb.pack(side="right", fill="y")
        gb.bind("<Button-1>", lambda e: self._settings())
        gb.bind("<Enter>",    lambda e: gb.config(fg=T0))
        gb.bind("<Leave>",    lambda e: gb.config(fg=TD))
        Tooltip(gb, "Settings")

        fb = tk.Label(hdr, text="◈", font=F11B,
                      bg=BG_H, fg=TD, padx=5, cursor="hand2")
        fb.pack(side="right", fill="y")
        fb.bind("<Button-1>", lambda e: self._fleet_manager())
        fb.bind("<Enter>",    lambda e: fb.config(fg=CI))
        fb.bind("<Leave>",    lambda e: fb.config(fg=TD))
        Tooltip(fb, "Fleet Manager")

        tk.Frame(self.root, bg=BDG, height=1).pack(fill="x")

        # Resize grip — must be packed with side="bottom" BEFORE the expanding body
        btm = tk.Frame(self.root, bg=BG, height=14)
        btm.pack(fill="x", side="bottom")
        btm.pack_propagate(False)
        grip_f = tk.Frame(btm, bg=BDG, width=14, height=14, cursor="bottom_right_corner")
        grip_f.pack(side="right", padx=1, pady=1)
        grip_f.pack_propagate(False)
        grip_l = tk.Label(grip_f, text="⤡",
                          font=tkfont.Font(family="Consolas", size=9),
                          bg=BDG, fg=T1, cursor="bottom_right_corner")
        grip_l.pack(expand=True)
        for w in (grip_f, grip_l):
            w.bind("<Button-1>",        self._resize_start)
            w.bind("<B1-Motion>",       self._resize_drag)
            w.bind("<ButtonRelease-1>", self._resize_end)

        body = tk.Frame(self.root, bg=BG, padx=6, pady=4)
        body.pack(fill="both", expand=True)
        self._body = body

        hdr2 = tk.Frame(body, bg=BG)
        hdr2.pack(fill="x", pady=(0, 3))
        tk.Label(hdr2, text="ACTIVE RATTING FLEET",
                 font=F8B, bg=BG, fg=T0).pack(side="left")

        tk.Frame(body, bg=BD, height=1).pack(fill="x", pady=(0, 2))

        # ── Style Treeview to match the dark EVE theme ────────────────
        st = ttk.Style()
        st.theme_use("clam")
        # Remove only the outer border wrapper from the layout.
        # Keeping Treeview.treearea (via Treeview.padding) preserves tag colour
        # rendering; removing Treeview.border eliminates the white highlight ring.
        st.layout("RatTV.Treeview", [
            ("Treeview.padding", {
                "sticky": "nswe",
                "children": [("Treeview.treearea", {"sticky": "nswe"})],
            })
        ])
        st.configure("RatTV.Treeview",
            background=BG, foreground=T0, fieldbackground=BG,
            font=("Consolas", 9), rowheight=22,
            borderwidth=0, relief="flat",
        )
        st.configure("RatTV.Treeview.Heading",
            background=BG_H, foreground=TD,
            font=("Consolas", 8, "bold"),
            borderwidth=0, relief="flat", padding=(4, 3),
        )
        st.map("RatTV.Treeview",
            background=[("selected", BD)],
            foreground=[("selected", TB)],
        )
        st.map("RatTV.Treeview.Heading",
            background=[("active", BDG), ("!active", BG_H)],
            foreground=[("active", T0),  ("!active", TD)],
            relief=[("active", "flat"), ("!active", "flat")],
        )

        # ── Treeview ──────────────────────────────────────────────────
        self._tree = ttk.Treeview(
            body, style="RatTV.Treeview",
            columns=("char", "net", "isk_hr", "session", "dps"),
            show="headings", selectmode="none", takefocus=False,
        )
        tv = self._tree

        # Headers + cells all centered (except CHARACTER, left) so each header sits
        # centered over its value — center-over-center aligns by construction and
        # avoids ttk's heading-vs-cell right-inset mismatch.
        tv.heading("char",    text="CHARACTER", anchor="w", command=lambda: None)
        tv.heading("net",     text="TOTAL NET",  anchor="center", command=lambda: None)
        tv.heading("isk_hr",  text="ISK/HR",     anchor="center", command=lambda: None)
        tv.heading("session", text="SESSION",    anchor="center", command=lambda: None)
        tv.heading("dps",     text="DPS",        anchor="center", command=lambda: None)

        tv.column("char",    stretch=True,  minwidth=60,  width=140, anchor="w")
        tv.column("net",     stretch=False, minwidth=24,  width=self._TV_NET,  anchor="center")
        tv.column("isk_hr",  stretch=False, minwidth=24,  width=self._TV_HR,   anchor="center")
        tv.column("session", stretch=False, minwidth=24,  width=self._TV_SES,  anchor="center")
        tv.column("dps",     stretch=False, minwidth=24,  width=self._TV_DPS,  anchor="center")

        # Restore any user-customised column widths from a previous session.
        self._restore_col_widths()

        # Green ★ = window visible, orange ★ = window hidden
        tv.tag_configure("vis", foreground=CI)
        tv.tag_configure("hid", foreground=CW)

        # ── Ligne « Fleet Total » — ancrée en bas en premier pour rester toujours visible ──
        tk.Frame(body, bg=BD, height=1).pack(side="bottom", fill="x", pady=(3, 0))
        total_row = tk.Frame(body, bg=BG)
        total_row.pack(side="bottom", fill="x", pady=(2, 0))
        self._total_name_lbl = tk.Label(total_row, text="FLEET TOTAL",
                                         font=F8B, bg=BG, fg=TD, anchor="w")
        self._total_name_lbl.pack(side="left", padx=(2, 0))
        self._total_bnt_lbl = tk.Label(total_row, text="",
                                        font=F8B, bg=BG, fg=CG, anchor="e",
                                        width=12)
        self._total_bnt_lbl.pack(side="left")
        self._total_net_lbl = tk.Label(total_row, text="",
                                        font=F8B, bg=BG, fg=CI, anchor="e",
                                        width=12)
        self._total_net_lbl.pack(side="left")

        # ── Treeview — remplit l'espace restant entre le header et le total ──
        tv.pack(fill="both", expand=True)
        tv.bind("<MouseWheel>",      lambda e: tv.yview_scroll(int(-1*(e.delta/120)), "units"))
        tv.bind("<ButtonRelease-1>", self._on_row_click)
        tv.bind("<ButtonRelease-1>", self._save_col_widths, add="+")  # persist column drags
        tv.bind("<Button-3>",        self._on_row_right)
        tv.bind("<Motion>",          self._on_row_motion)
        tv.bind("<Leave>",           lambda e: tv.configure(cursor=""))

        self.root.bind("<Configure>", self._on_main_resize)

    # ── Rebuild all character rows in the Treeview ───────────────────
    def _rebuild_rows(self):
        tv = self._tree
        for iid in tv.get_children():
            tv.delete(iid)
        self._rows.clear()
        self._tv_cache.clear()

        for char_id, win in self._windows.items():
            if not win.root.winfo_exists():
                continue
            visible  = win.root.winfo_viewable()
            name_txt = f"★ {win.char_name[:18]}" + ("…" if len(win.char_name) > 18 else "")
            tv.insert("", "end", iid=char_id,
                      values=(name_txt, "-", "-", "00:00:00", "○"),
                      tags=("vis" if visible else "hid",))
            self._rows[char_id] = char_id   # iid == char_id
            self._restore_overlay(char_id)
            self._reflect_overlay_state(char_id)

        self.root.update_idletasks()
        self._resize_char_col()

    # ── Treeview helpers ──────────────────────────────────────────────
    def _tv_set(self, iid: str, col: str, value: str):
        """Update a Treeview cell only when the value actually changed."""
        key = (iid, col)
        if self._tv_cache.get(key) == value:
            return
        self._tv_cache[key] = value
        self._tree.set(iid, col, value)

    def _tv_tag(self, iid: str, state: str, visible: bool):
        """Tag the 4 data columns by visibility only (state is for future use)."""
        tag = "vis" if visible else "hid"
        key = (iid, "__tag__")
        if self._tv_cache.get(key) == tag:
            return
        self._tv_cache[key] = tag
        self._tree.item(iid, tags=(tag,))

    def _tv_col_name(self, event):
        """Logical column name under the pointer (or None)."""
        try:
            cols = self._tree["columns"]
            cid = self._tree.identify_column(event.x)   # like "#5"
            idx = int(cid[1:]) - 1
            if 0 <= idx < len(cols):
                return cols[idx]
        except Exception:
            pass
        return None

    def _on_row_click(self, event):
        """Left-click the DPS cell → toggle that character's DPS overlay;
        any other cell → toggle the character's dashboard window."""
        iid = self._tree.identify_row(event.y)
        if not iid or self._tree.identify_region(event.x, event.y) != "cell":
            return
        if self._tv_col_name(event) == "dps":
            self._toggle_overlay(iid)
        else:
            self._toggle_window(iid)

    def _on_row_right(self, event):
        """Right-click the DPS cell → overlay context menu
        (open / reposition / view / close)."""
        iid = self._tree.identify_row(event.y)
        if not (iid and self._tree.identify_region(event.x, event.y) == "cell"
                and self._tv_col_name(event) == "dps"):
            return
        ov = self._overlays.get(iid)
        m = tk.Menu(self._tree, tearoff=0, bg=BG_H, fg=TB,
                    activebackground=BDG, activeforeground=TB, bd=0, relief="flat")
        if ov and ov.w.winfo_exists():
            m.add_command(label="Reposition", command=lambda: ov.toggle_lock(force=False))
            vv = tk.IntVar(value=ov.view)
            m._vv = vv  # keep a reference alive while the menu is up
            sub = tk.Menu(m, tearoff=0, bg=BG_H, fg=TB,
                          activebackground=BDG, activeforeground=TB, bd=0, relief="flat")
            for i, name in enumerate(("Numbers", "Graph", "Numbers + graph")):
                sub.add_radiobutton(label=name, value=i, variable=vv,
                                    command=lambda idx=i: ov.set_view(idx))
            m.add_cascade(label="View", menu=sub)
            m.add_separator()
            m.add_command(label="Close overlay", command=ov.close)
        else:
            m.add_command(label="Open DPS overlay", command=lambda: self._toggle_overlay(iid))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # ── DPS overlay management ────────────────────────────────────────
    def _toggle_overlay(self, char_id):
        win = self._windows.get(char_id)
        if not win or not win.root.winfo_exists():
            return
        ov = self._overlays.get(char_id)
        if ov and ov.w.winfo_exists():
            ov.close()
            return
        win._overlay_active = True
        self._overlays[char_id] = DPSOverlay(self, win)
        win.char_cfg["dps_overlay_open"] = True
        save_config(self.cfg)
        self._reflect_overlay_state(char_id)

    def _restore_overlay(self, char_id):
        """Idempotently re-open an overlay if the character's config says it was open."""
        win = self._windows.get(char_id)
        if not win or self._overlays.get(char_id):
            return
        if win.char_cfg.get("dps_overlay_open", False):
            win._overlay_active = True
            self._overlays[char_id] = DPSOverlay(self, win)
            self._reflect_overlay_state(char_id)

    def _on_overlay_closed(self, char_id):
        self._overlays.pop(char_id, None)
        win = self._windows.get(char_id)
        if win:
            win._overlay_active = False
        self._reflect_overlay_state(char_id)

    def _reflect_overlay_state(self, char_id):
        """Set the row's DPS glyph: ○ closed, ◉ placed (set), ✜ move mode."""
        if char_id not in self._rows:
            return
        ov = self._overlays.get(char_id)
        glyph = "○"
        if ov and getattr(ov, "w", None) is not None:
            try:
                if ov.w.winfo_exists():
                    glyph = "◉" if ov.locked else "✜"
            except Exception:
                pass
        try:
            self._tv_set(char_id, "dps", glyph)
        except Exception:
            pass

    def _on_row_motion(self, event):
        """Show hand cursor when hovering over a data row."""
        region = self._tree.identify_region(event.x, event.y)
        self._tree.configure(cursor="hand2" if region == "cell" else "")

    def _resize_char_col(self):
        """Make the CHARACTER column fill all space left by the fixed columns
        (using their CURRENT widths, so user-resized columns are respected)."""
        if not self._tree:
            return
        tv_w  = self._tree.winfo_width() or self.MAIN_W
        try:
            fixed = sum(self._tree.column(c, "width")
                        for c in ("net", "isk_hr", "session", "dps"))
        except Exception:
            fixed = self._TV_NET + self._TV_HR + self._TV_SES + self._TV_DPS
        char_w = max(60, tv_w - fixed)
        self._tree.column("char", width=char_w)

    def _restore_col_widths(self):
        """Apply saved per-column widths for the fixed columns (if any)."""
        saved = self.cfg.get("main_ui", {}).get("col_widths", {})
        if not saved or not self._tree:
            return
        for col in ("net", "isk_hr", "session", "dps"):
            w = saved.get(col)
            if isinstance(w, int) and w >= 20:
                try:
                    self._tree.column(col, width=w)
                except Exception:
                    pass

    def _save_col_widths(self, event=None):
        """Persist fixed-column widths after the user drags a header separator
        (only writes config when a width actually changed)."""
        if not self._tree:
            return
        try:
            widths = {c: self._tree.column(c, "width")
                      for c in ("net", "isk_hr", "session", "dps")}
            mui = self.cfg.setdefault("main_ui", {})
            if mui.get("col_widths") != widths:
                mui["col_widths"] = widths
                save_config(self.cfg)
        except Exception:
            pass

    # ── Live stats update + frozen detection ─────────────────────────
    def _lset(self, lbl, text=None, fg=None):
        """Update a label only when its value changed.

        Compares against a Python-side cache (self._label_vals) instead of
        calling lbl.cget(), which on Windows returns 12-digit hex colors that
        never compare equal to the 6-digit hex strings we pass in.
        """
        lid  = id(lbl)
        prev = self._label_vals.get(lid, {})
        opts = {}
        if text is not None and prev.get("text") != text:
            opts["text"] = text
        if fg is not None and prev.get("fg") != fg:
            opts["fg"] = fg
        if opts:
            self._label_vals[lid] = {**prev, **opts}
            lbl.config(**opts)

    def _health_check(self):
        now       = time.monotonic()
        fleet_net = 0.0
        fleet_hr  = 0.0
        running_n = 0

        for char_id, win in self._windows.items():
            if char_id not in self._rows:
                continue
            if not win.root.winfo_exists():
                continue

            suspended = getattr(win, "_suspended", False)
            vis       = win.root.winfo_viewable()

            # Suspended (hidden + bg_monitor OFF): show last earned, mark offline
            if suspended:
                d       = win.data
                net_tot = d.bg * (1 - d.tax) + d.loot_val
                self._tv_tag(char_id, "standby", False)   # orange — offline
                self._tv_set(char_id, "net",     fisk(net_tot) if net_tot > 0 else "-")
                self._tv_set(char_id, "isk_hr",  "— OFFLINE —")
                self._tv_set(char_id, "session", fdur(d.acc_sec) if d.acc_sec > 0 else "00:00:00")
                continue

            # Hidden but still monitored (bg_monitor ON): fall through to live data display below.
            # vis=False already causes _tv_tag to use the dimmed/hidden style.

            frozen = (now - getattr(win, "_last_tick_wall", now)) > 1.5
            if frozen:
                self._tv_tag(char_id, "frozen", vis)
                self._tv_set(char_id, "net",     "— NO TICK —")
                self._tv_set(char_id, "isk_hr",  "—")
                self._tv_set(char_id, "session", "—")
                continue

            d      = win.data
            st     = win._st
            sec    = d.secs()
            net_tot = d.bg * (1 - d.tax) + d.loot_val
            isk_hr  = d.isk()

            if st == "running" and sec >= 60 and d.bg > 0:
                fleet_net += net_tot
                fleet_hr  += isk_hr
                running_n += 1
                self._tv_tag(char_id, "run", vis)
                self._tv_set(char_id, "net",     fisk(net_tot))
                self._tv_set(char_id, "isk_hr",  fisk(isk_hr) + "/hr")
                self._tv_set(char_id, "session", fdur(sec))
            elif st == "paused":
                self._tv_tag(char_id, "paused", vis)
                self._tv_set(char_id, "net",     fisk(net_tot) if net_tot > 0 else "-")
                self._tv_set(char_id, "isk_hr",  "— PAUSED —")
                self._tv_set(char_id, "session", fdur(sec))
            else:
                self._tv_tag(char_id, "standby", vis)
                self._tv_set(char_id, "net",     fisk(net_tot) if net_tot > 0 else "-")
                self._tv_set(char_id, "isk_hr",  "-")
                self._tv_set(char_id, "session", fdur(sec) if sec > 0 else "00:00:00")

        if running_n >= 2:
            self._lset(self._total_bnt_lbl, text=fisk(fleet_net),        fg=CG)
            self._lset(self._total_net_lbl, text=fisk(fleet_hr) + "/hr", fg=CI)
        else:
            self._lset(self._total_bnt_lbl, text="")
            self._lset(self._total_net_lbl, text="")

        self._health_job = self.root.after(500, self._health_check)

    # ── Show / hide a character window ───────────────────────────────
    def _toggle_window(self, char_id: str):
        win = self._windows.get(char_id)
        if not win or not win.root.winfo_exists():
            return
        char_cfg = self.cfg.setdefault("chars", {}).setdefault(char_id, {})

        bg_monitor = self.cfg.get("bg_monitor", False)

        if win.root.winfo_viewable():
            # HIDE — withdraw main + all detached panels (keep widgets alive for _tick)
            panels = [("isk", "_isk_window"),
                      ("msn", "_msn_window"), ("anom", "_anom_window"),
                      ("alert", "_alert_window")]
            was_detached = []
            for key, attr in panels:
                if getattr(win, f"_{key}_detached", False):
                    was_detached.append(key)
                dw = getattr(win, attr, None)
                if dw and dw.w.winfo_exists():
                    try:
                        dw.w.withdraw()
                    except Exception:
                        pass
            win._hidden_detached = was_detached
            win.root.withdraw()
            char_cfg["show"] = False
            if bg_monitor or getattr(win, "_overlay_active", False):
                # Keep monitoring — bg-monitor on, or a DPS overlay is open for this char
                win._suspended = False
            else:
                win._suspended = True      # stop log reading for this character
            if char_id in self._rows:
                self._tv_cache.pop((char_id, "__tag__"), None)
                self._tv_tag(char_id, "standby", False)
        else:
            # SHOW — restore main window and all panels that were visible before hide
            win.root.deiconify()
            win.root.lift()
            panels = [("isk", "_isk_window"),
                      ("msn", "_msn_window"), ("anom", "_anom_window"),
                      ("alert", "_alert_window")]
            for key, attr in panels:
                if key in getattr(win, "_hidden_detached", []):
                    dw = getattr(win, attr, None)
                    if dw and dw.w.winfo_exists():
                        try:
                            dw.w.deiconify()
                            dw.w.lift()
                        except Exception:
                            pass
            win._hidden_detached = []
            char_cfg["show"] = True
            win._suspended = False         # resume log reading
            if char_id in self._rows:
                self._tv_cache.pop((char_id, "__tag__"), None)
                self._tv_tag(char_id, "standby", True)
        
        save_config(self.cfg)

    # ── Called by CharacterWindow._quit() when a window closes itself ─
    def _on_char_closed(self, char_id: str):
        self._windows.pop(char_id, None)
        self._rows.pop(char_id, None)
        if self.root.winfo_exists() and self._tree:
            try:
                self._tree.delete(char_id)
            except Exception:
                pass
            # purge cache entries for this char
            for k in [k for k in self._tv_cache if k[0] == char_id]:
                del self._tv_cache[k]

    # ── Resize grip ──────────────────────────────────────────────────
    def _resize_start(self, e):
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()
        self._rx = e.x_root
        self._ry = e.y_root
        self._wx = self.root.winfo_x()
        self._wy = self.root.winfo_y()

    def _resize_drag(self, e):
        nw = max(self.MAIN_W, self._rw + (e.x_root - self._rx))
        nh = max(100, self._rh + (e.y_root - self._ry))
        self.root.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    def _resize_end(self, e):
        self._save_pos()

    def _on_main_resize(self, event):
        if event.widget is not self.root:
            return
        w = event.width
        if abs(w - getattr(self, "_main_last_w", 0)) < 3:
            return
        self._main_last_w = w
        self._resize_char_col()

    def _toggle_collapse(self, event=None):
        if getattr(self, "_dragging", False):
            return
        current_time = time.time()
        if hasattr(self, "_last_toggle_time"):
            if current_time - self._last_toggle_time < 0.5:
                return
        self._last_toggle_time = current_time

        if self._is_collapsed:
            self._body.pack(fill="both", expand=True)
            if self._full_height > 0:
                w = self.root.winfo_width()
                x, y = self.root.winfo_x(), self.root.winfo_y()
                self.root.geometry(f"{w}x{self._full_height}+{x}+{y}")
            self._is_collapsed = False
            self._main_last_w = 0
            self.cfg.setdefault("main_ui", {})["collapsed"] = False
            save_config(self.cfg)
        else:
            self._full_height = self.root.winfo_height()
            self._body.pack_forget()
            self.root.update_idletasks()
            w = self.root.winfo_width()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x29+{x}+{y}")
            self._is_collapsed = True
            mui = self.cfg.setdefault("main_ui", {})
            mui["collapsed"] = True
            mui["full_height"] = self._full_height
            save_config(self.cfg)

    # ── Settings ─────────────────────────────────────────────────────
    def _settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        self._settings_win = MainUISettings(self.root, self).w

    # ── Fleet Manager ─────────────────────────────────────────────────
    def _fleet_manager(self):
        if self._fleet_mgr_win and self._fleet_mgr_win.winfo_exists():
            self._fleet_mgr_win.lift()
            return
        self._fleet_mgr_win = FleetManager(self.root, self).w

    # ── Geometry ─────────────────────────────────────────────────────
    def _save_pos(self):
        try:
            mui = self.cfg.setdefault("main_ui", {})
            mui["geometry"] = self.root.winfo_geometry()
            if not self._is_collapsed:
                h = self.root.winfo_height()
                if h > 32:
                    mui["full_height"] = h
            save_config(self.cfg)
        except Exception:
            pass

    def _restore_geometry(self):
        saved = self.cfg.get("main_ui", {}).get("geometry", "")
        if saved:
            self.root.geometry(saved)
        else:
            self.root.geometry(f"{self.MAIN_W}x300+10+80")

    # ── System tray (single icon for the whole app) ──────────────────
    def _init_tray_icon(self):
        try:
            icon_img = None
            for fname in ('PVE.ico', 'PVE.png'):
                icon_path = _get_resource_path(fname)
                if os.path.exists(icon_path):
                    icon_img = Image.open(icon_path)
                    break
            if icon_img is None:
                icon_img = Image.new('RGB', (64, 64), "#1a1a1a")
                d = ImageDraw.Draw(icon_img)
                d.ellipse([10, 10, 54, 54], outline="#3dd8e0", width=6)
                d.point([32, 32], fill="#ffffff")

            menu = pystray.Menu(
                pystray.MenuItem("Show Overview", self._tray_show, default=True),
                pystray.MenuItem("Exit", self._tray_exit),
            )
            self._tray_icon = pystray.Icon("PVE", icon_img, "EVE Ratting", menu)
            threading.Thread(target=self._tray_icon.run, daemon=True).start()
        except Exception:
            traceback.print_exc()

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self._tray_restore)

    def _tray_restore(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        for char_id, win in self._windows.items():
            try:
                if not win.root.winfo_exists():
                    continue
                show = self.cfg.get("chars", {}).get(char_id, {}).get("show", True)
                if show:
                    win.root.deiconify()
                    win.root.lift()
                    for attr in ("_isk_window", "_msn_window",
                                 "_anom_window", "_alert_window"):
                        dw = getattr(win, attr, None)
                        if dw and dw.w.winfo_exists():
                            dw.w.deiconify()
                            dw.w.lift()
            except Exception:
                pass

    def _tray_exit(self, icon=None, item=None):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        self.root.after(0, self._quit)

    # ── Quit all ─────────────────────────────────────────────────────
    def _quit(self):
        if self._health_job:
            self.root.after_cancel(self._health_job)
            self._health_job = None
        if self._scan_job:
            self.root.after_cancel(self._scan_job)
            self._scan_job = None
        obs = getattr(self, "_log_observer", None)
        if obs is not None:
            try:
                obs.stop(); obs.join(timeout=2.0)
            except Exception:
                pass
            self._log_observer = None
        self._save_pos()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
        for ov in list(self._overlays.values()):
            try:
                ov.close()
            except Exception:
                pass
        for win in list(self._windows.values()):
            try:
                win._quit()
            except Exception:
                pass
        if self.root.winfo_exists():
            self.root.destroy()


if __name__ == "__main__":
    MainUI()