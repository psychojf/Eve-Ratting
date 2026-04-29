# -*- coding: utf-8 -*-
import sys
import tkinter as tk
from tkinter import ttk, font as tkfont
import os, re, json, time, threading, urllib.request, traceback
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque

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

# Formate des secondes en durée lisible (H:MM:SS)
def fdur(s):
    h, r = divmod(int(s), 3600)
    m, s2 = divmod(r, 60)
    return f"{h}:{m:02d}:{s2:02d}" if h else f"{m:02d}:{s2:02d}"

# Extrait l'arme et le type de coup depuis une chaîne de combat
def ptail(t):
    t = shtml(t)
    p = [x.strip() for x in t.split(" - ") if x.strip()]
    if len(p) >= 2: return p[0], p[-1]
    return ("Unknown", p[0]) if p else ("Unknown", "Hits")

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
    r = {}
    if not os.path.isdir(base): return r
    for dp, dn, fns in os.walk(base):
        for fn in fns:
            m = RE_CF.match(fn)
            if m:
                c = m.group(3)
                fp = os.path.join(dp, fn)
                if c not in r or os.path.getmtime(fp) > os.path.getmtime(r[c]):
                    r[c] = fp
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
            (a["end"] - a["start"]).total_seconds()
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
        self.hd = self.hr = self.md = self.mr = 0
        self.bp = self.bg = 0
        self.tax = DEF_TAX / 100
        self.bc = 0
        self.loot_val = 0               # Total loot estimated value
        self.fb = None
        self.pkd = self.pkr = 0

        # Mission tracking
        self.mission_name = None        # Current mission name (from chatlog)
        self.mission_obj_met = False    # Objective accomplished flag
        self.missions_done = 0          # Missions completed this session
        self.storyline_ctr = 0          # Running counter toward storyline (16)
        self.standings = []             # [(faction, amount), ...]
        self.alerts = deque(maxlen=MAX_ALERTS)  # [(timestamp_str, type, text), ...]

        # Anomaly tracking
        self.anom_current = None         # dict for active anomaly (or None)
        self.anom_completed = []         # list of completed anomaly dicts
        self.anom_last_combat = None     # datetime of last combat event (UTC)

        # Deque + running sum for O(1) DPS calc
        self.ed = deque(maxlen=1000)     # (ts, dmg) out
        self.er = deque(maxlen=1000)     # (ts, dmg) in
        self.ed_sum = 0
        self.er_sum = 0

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
        self.ed.append((time.monotonic(), dmg))
        self.ed_sum += dmg
        self.dd += dmg
        self.hd += 1

    # Enregistre un coup reçu et met à jour les totaux
    def add_dmg_in(self, ts, dmg):
        self.er.append((time.monotonic(), dmg))
        self.er_sum += dmg
        self.dr += dmg
        self.hr += 1

    # Méthode vide — le nettoyage est fait en direct dans dps()
    def trim(self):
        pass  # handled live in dps()

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
        
        self._scroll_binding = canvas.bind_all("<MouseWheel>", _safe_scroll)
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
            if a._dps_window and a._dps_window.w.winfo_exists():
                a._dps_window.w.attributes("-alpha", a.alpha)
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

            # Parse saved geometry for position, use saved size if available
            geo_key = f"{section_key}_detach_geo"
            saved_geo = app.char_cfg.get(geo_key)
            if saved_geo:
                self.w.geometry(f"{saved_geo}{saved}")
            else:
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
        self.cf = log_file if log_file else None
        self.fh = None
        self.fp = 0
        self._sw  = None
        self._hw = None
        self._calc_dots = 0

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
        self._loot_anim_job   = None
        self._loot_anim_step  = 0

        # ── Load or Download Market Prices (24h disk cache) ──
        threading.Thread(target=self._download_market_data, daemon=True).start()

        self._storyline_ctr = self.cfg.get("storyline_counter", 0)
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
        self._dps_detached = False
        self._dps_window = None
        self._msn_detached = False
        self._msn_window = None
        self._anom_detached = False
        self._anom_window = None
        self._alert_detached = False
        self._alert_window = None
        self._isk_det_labels = {}
        self._dps_det_labels = {}
        self._msn_det_labels = {}
        self._anom_det_labels = {}

        # Section enabled states (ON/OFF)
        self._isk_enabled  = self.cfg.get("isk_enabled", True)
        self._msn_enabled  = self.cfg.get("msn_enabled", True)
        self._anom_enabled = self.cfg.get("anom_enabled", False)

        # Enforce mutual exclusivity: if both ON, keep MSN, disable ANOM
        if self._msn_enabled and self._anom_enabled:
            self._anom_enabled = False
            self.cfg["anom_enabled"] = False
        self._dps_enabled  = self.cfg.get("dps_enabled", True)

        # Section collapsed states
        self._isk_collapsed = self.cfg.get("isk_collapsed", False)
        self._msn_collapsed = self.cfg.get("msn_collapsed", False)
        self._anom_collapsed = self.cfg.get("anom_collapsed", False)
        self._dps_collapsed = self.cfg.get("dps_collapsed", False)
        self._brk_collapsed = self.cfg.get("brk_collapsed", False)

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
        self._poll()
        self._tick()

        if self.char_cfg.get("isk_detached", False):
            self._detach("isk")
        if self.char_cfg.get("dps_detached", False):
            self._detach("dps")
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
        try:
            with open(NAMEID_CACHE, "w", encoding="utf-8") as f:
                json.dump(self._name_to_id_cache, f, ensure_ascii=False)
        except Exception:
            pass

    # ── Market data download (24h cache) ─────────────────────────────
    # Télécharge les prix ESI (cache 24h sur disque)
    def _download_market_data(self):

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
            req = urllib.request.Request("https://esi.evetech.net/latest/markets/prices/?datasource=tranquility")
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode())
                self._global_prices = {
                    str(item['type_id']): item.get('average_price', item.get('adjusted_price', 0))
                    for item in data
                }

            # Save to disk
            with open(PRICE_CACHE, "w", encoding="utf-8") as f:
                json.dump(self._global_prices, f)
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
            tracker._last_clipboard = content
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
                    try: qty = int(parts[1].replace(',', '').replace('.', '').strip())
                    except:
                        qty = 1
                
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
                                                 headers={'Content-Type': 'application/json', 'Accept-Language': 'en'})
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
        if total_session_loot > 0:
            self.root.after(0, lambda amt=total_session_loot, ts=now_str: self._apply_loot(amt, ts))
        else:
            # Nothing valued — stop spinner without flashing green
            self.root.after(0, lambda: self._loot_anim_stop(False))

    # Pulse visuel sur le cadre d'alerte (pour les événements EWAR)
    def _flash_alert(self):

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
                self.root.after(150, lambda: _pulse(step + 1))
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
            req = urllib.request.Request(url)
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
        h = self._body.winfo_reqheight() + 32

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
            # Expand — restore content, then re-pack grip so it stays at the bottom
            self._main_frame.pack(fill="x", padx=3, pady=(0, 3))
            if hasattr(self, "_grip_bar"):
                self._grip_bar.pack_forget()
                self._grip_bar.pack(fill="x")
            if self._full_height > 0:
                w = self.root.winfo_width()
                x, y = self.root.winfo_x(), self.root.winfo_y()
                self.root.geometry(f"{w}x{self._full_height}+{x}+{y}")
            self._is_collapsed = False
        else:
            # Collapse — hide content, keep only header bar visible
            self._full_height = self.root.winfo_height()
            self._main_frame.pack_forget()
            self.root.update_idletasks()
            w = self.root.winfo_width()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x32+{x}+{y}")
            self._is_collapsed = True

    # Sauvegarde la géométrie complète de la fenêtre principale
    def _save_pos(self):
        try:
            self.char_cfg["geometry"] = self.root.winfo_geometry()
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

        self._sep_anom_dps = tk.Frame(self._body, bg=BD, height=1)
        self._sep_anom_dps.grid(row=8, column=0, sticky="ew", padx=4)

        self._dps_container = tk.Frame(self._body, bg=BG)
        self._dps_container.grid(row=9, column=0, sticky="ew")
        self._build_dps(self._dps_container, detached=False)

        # Resize grip at bottom-right
        self._grip_bar = tk.Frame(self.root, bg=BG, height=14)
        self._grip_bar.pack(fill="x")
        self._grip_bar.pack_propagate(False)
        grip_bar = self._grip_bar
        grip_f = tk.Frame(grip_bar, bg=BDG, width=14, height=14, cursor="bottom_right_corner")
        grip_f.pack(side="right", padx=1, pady=1)
        grip_f.pack_propagate(False)
        grip_l = tk.Label(grip_f, text="⤡",
                          font=tkfont.Font(family="Consolas", size=9),
                          bg=BDG, fg=T1, cursor="bottom_right_corner")
        grip_l.pack(expand=True)
        for _gw in (grip_f, grip_l):
            _gw.bind("<Button-1>",        self._resize_start)
            _gw.bind("<B1-Motion>",       self._resize_drag)
            _gw.bind("<ButtonRelease-1>", self._resize_end)

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

        self._alert_frame = tk.Frame(parent, bg=BG_P)
        self._alert_frame.pack(fill="both", expand=True, padx=6, pady=(2, 4))
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
        self.cfg["brk_collapsed"] = self._brk_collapsed
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

    # Construit la section DPS Monitor (inline ou détaché avec barres visuelles)
    def _build_dps(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F7B = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F16 = tkfont.Font(family="Consolas", size=16, weight="bold")
        pad = dict(padx=6, pady=2)

        # ── Header: [accent] [DPS MONITOR] [ON/OFF] ... [▼/▶] [↱] ──
        # Skip header when detached — DetachedWindow provides its own
        if not detached:
            hdr_f = tk.Frame(parent, bg=BG_P, height=20)
            hdr_f.pack(fill="x")
            hdr_f.pack_propagate(False)
            tk.Frame(hdr_f, bg=CD, width=3).pack(side="left", fill="y")
            tk.Label(hdr_f, text="  DPS MONITOR", font=F8B, bg=BG_P, fg=CD).pack(side="left")

            # ON/OFF button
            self._dps_on_btn = tk.Label(hdr_f, text="ON" if self._dps_enabled else "OFF",
                                         font=F7B, bg=BG_P, fg=CA if self._dps_enabled else CS, cursor="hand2", padx=4)
            self._dps_on_btn.pack(side="left", padx=(4, 0))
            self._dps_on_btn.bind("<Button-1>", lambda e: self._toggle_enabled("dps"))

            # Detach button (rightmost)
            self._dps_det_btn = tk.Label(hdr_f, text=" \u21F1 ", font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                                          bg=BG_P, fg=C_DETACH, cursor="hand2")
            self._dps_det_btn.pack(side="right", padx=2)
            self._dps_det_btn.bind("<Button-1>", lambda e: self._detach("dps"))
            self._dps_det_btn.bind("<Enter>", lambda e: self._dps_det_btn.config(bg=BDG))
            self._dps_det_btn.bind("<Leave>", lambda e: self._dps_det_btn.config(bg=BG_P))
            Tooltip(self._dps_det_btn, "Detach")

            # Collapse toggle
            self._dps_tog_btn = tk.Label(hdr_f, text="\u25BC" if not self._dps_collapsed else "\u25B6",
                                          font=tkfont.Font(family="Consolas", size=8), bg=BG_P, fg=TD, cursor="hand2")
            self._dps_tog_btn.pack(side="right", padx=4)
            self._dps_tog_btn.bind("<Button-1>", lambda e: self._toggle_collapse("dps"))
            self._dps_tog_btn.bind("<Enter>", lambda e: self._dps_tog_btn.config(fg=TB))
            self._dps_tog_btn.bind("<Leave>", lambda e: self._dps_tog_btn.config(fg=TD))

            if not self._dps_enabled:
                self._dps_det_btn.pack_forget()
                self._dps_tog_btn.pack_forget()

        # ── Content wrapper ──
        self._dps_wrap = tk.Frame(parent, bg=BG_P)
        show_content = self._dps_enabled and (detached or not self._dps_collapsed)
        if detached:
            if show_content:
                self._dps_wrap.pack(fill="both", expand=True, **pad)
        else:
            if show_content:
                self._dps_wrap.pack(fill="x", **pad)

        if detached:
            # ═══════════════════════════════════════════════════════════════
            # DETACHED MODE: Enhanced layout with bar indicators
            # ═══════════════════════════════════════════════════════════════
            
            # DPS OUT section (top half)
            out_frame = tk.Frame(self._dps_wrap, bg=BG_P, width=1)
            out_frame.pack(fill="both", expand=True, pady=(0, 2))
            out_frame.pack_propagate(False)
            
            # Title row
            out_hdr = tk.Frame(out_frame, bg=BG_P)
            out_hdr.pack(fill="x")
            lbl_out_title = tk.Label(out_hdr, text="▸ DPS OUT", font=F8B, bg=BG_P, fg=CD, anchor="w")
            lbl_out_title.pack(side="left")
            
            # Value with bar background
            out_bar_frame = tk.Frame(out_frame, bg=BG, highlightbackground=BD, highlightthickness=1, width=1)
            out_bar_frame.pack(fill="both", expand=True, pady=2)
            out_bar_frame.pack_propagate(False)
            
            # The bar canvas — no fixed height so it shrinks freely
            out_canvas = tk.Canvas(out_bar_frame, bg=BG, highlightthickness=0)
            out_canvas.pack(fill="both", expand=True)
            
            # Value label overlaid on canvas
            dps_out = tk.Label(out_bar_frame, text="0", font=F16, bg=BG, fg=CD, anchor="center")
            dps_out.place(relx=0.02, rely=0.5, anchor="w")
            
            # DPS IN section (bottom half)
            in_frame = tk.Frame(self._dps_wrap, bg=BG_P, width=1)
            in_frame.pack(fill="both", expand=True, pady=(2, 0))
            in_frame.pack_propagate(False)
            
            # Title row
            in_hdr = tk.Frame(in_frame, bg=BG_P)
            in_hdr.pack(fill="x")
            lbl_in_title = tk.Label(in_hdr, text="◂ DPS IN", font=F8B, bg=BG_P, fg=CR, anchor="w")
            lbl_in_title.pack(side="left")
            
            # Value with bar background
            in_bar_frame = tk.Frame(in_frame, bg=BG, highlightbackground=BD, highlightthickness=1, width=1)
            in_bar_frame.pack(fill="both", expand=True, pady=2)
            in_bar_frame.pack_propagate(False)
            
            # The bar canvas
            in_canvas = tk.Canvas(in_bar_frame, bg=BG, highlightthickness=0)
            in_canvas.pack(fill="both", expand=True)
            
            # Value label overlaid on canvas
            dps_in = tk.Label(in_bar_frame, text="0", font=F16, bg=BG, fg=CR, anchor="center")
            dps_in.place(relx=0.02, rely=0.5, anchor="w")
            
            labels = {
                "dps_out": dps_out, "dps_in": dps_in,
                "lbl_out_title": lbl_out_title, "lbl_in_title": lbl_in_title,
                "out_canvas": out_canvas, "in_canvas": in_canvas,
                "out_bar_frame": out_bar_frame, "in_bar_frame": in_bar_frame,
                "_last_scale_h": 0, "_max_dps_out": 1000, "_max_dps_in": 500
            }
            self._dps_det_labels = labels
            
            # Bind resize handler for dynamic scaling
            self._dps_wrap.bind("<Configure>", self._on_dps_detached_resize)
        else:
            # ═══════════════════════════════════════════════════════════════
            # INLINE MODE: Simple side-by-side layout (unchanged)
            # ═══════════════════════════════════════════════════════════════
            dl = tk.Frame(self._dps_wrap, bg=BG_P)
            dl.pack(side="left", expand=True, fill="both")
            tk.Label(dl, text="DPS OUT", font=F8, bg=BG_P, fg=TD, anchor="w").pack(anchor="w", fill="x")
            dps_out = tk.Label(dl, text="0", font=F16, bg=BG_P, fg=CD, anchor="w")
            dps_out.pack(anchor="w")

            dr_f = tk.Frame(self._dps_wrap, bg=BG_P)
            dr_f.pack(side="right", expand=True, fill="both")
            tk.Label(dr_f, text="DPS IN", font=F8, bg=BG_P, fg=TD, anchor="e").pack(anchor="e", fill="x")
            dps_in = tk.Label(dr_f, text="0", font=F16, bg=BG_P, fg=CR, anchor="e")
            dps_in.pack(anchor="e")

            self.dps_out = dps_out
            self.dps_in = dps_in

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
            val_font = tkfont.Font(family="Consolas", size=val_size, weight="bold")
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
                labels["sl"].config(font=tkfont.Font(family="Consolas", size=sess_size, weight="bold"))
        finally:
            self._scaling_isk = False

    # Adapte les polices et barres DPS quand la fenêtre détachée est redimensionnée
    def _on_dps_detached_resize(self, event):
        if not self._dps_detached or not self._dps_det_labels:
            return
        # Guard: font changes trigger another <Configure>, causing an oscillation loop
        if getattr(self, '_scaling_dps', False):
            return
        labels = self._dps_det_labels
        h = event.height

        last_h = labels.get("_last_scale_h", 0)
        if abs(h - last_h) < 5:
            return
        labels["_last_scale_h"] = h

        self._scaling_dps = True
        try:
            base_h = 100
            value_base = 18
            title_base = 9

            scale      = max(0.8, min(4.0, h / base_h))
            value_size = max(14, min(72, int(value_base * scale)))
            title_size = max(8,  min(18, int(title_base * scale * 0.8)))

            value_font = tkfont.Font(family="Consolas", size=value_size, weight="bold")
            title_font = tkfont.Font(family="Consolas", size=title_size, weight="bold")

            labels["dps_out"].config(font=value_font)
            labels["dps_in"].config(font=value_font)
            if "lbl_out_title" in labels:
                labels["lbl_out_title"].config(font=title_font)
            if "lbl_in_title" in labels:
                labels["lbl_in_title"].config(font=title_font)

            self._update_dps_bars()
        finally:
            self._scaling_dps = False

    # Met à jour les barres visuelles DPS en mode détaché
    def _update_dps_bars(self):
        if not self._dps_detached or not self._dps_det_labels:
            return
        
        labels = self._dps_det_labels
        out_canvas = labels.get("out_canvas")
        in_canvas = labels.get("in_canvas")
        
        if not out_canvas or not in_canvas:
            return
        
        # Get current DPS values
        dps_out_val = self.data.dps(True)
        dps_in_val = self.data.dps(False)
        
        # Update max trackers (auto-scale)
        max_out = labels.get("_max_dps_out", 1000)
        max_in = labels.get("_max_dps_in", 500)
        if dps_out_val > max_out:
            labels["_max_dps_out"] = dps_out_val * 1.2
            max_out = labels["_max_dps_out"]
        if dps_in_val > max_in:
            labels["_max_dps_in"] = dps_in_val * 1.2
            max_in = labels["_max_dps_in"]
        
        # Calculate bar fill percentages
        out_pct = min(1.0, dps_out_val / max_out) if max_out > 0 else 0
        in_pct = min(1.0, dps_in_val / max_in) if max_in > 0 else 0
        
        # Update OUT canvas
        out_canvas.delete("bar")
        w = out_canvas.winfo_width()
        h = out_canvas.winfo_height()
        if w > 1 and h > 1:
            bar_w = int(w * out_pct)
            # Subtle gradient effect using dimmed accent color
            bar_color = _dim(CD, 0.3)
            out_canvas.create_rectangle(0, 0, bar_w, h, fill=bar_color, outline="", tags="bar")
        
        # Update IN canvas
        in_canvas.delete("bar")
        w = in_canvas.winfo_width()
        h = in_canvas.winfo_height()
        if w > 1 and h > 1:
            bar_w = int(w * in_pct)
            bar_color = _dim(CR, 0.3)
            in_canvas.create_rectangle(0, 0, bar_w, h, fill=bar_color, outline="", tags="bar")

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
        self.cfg[f"{section}_enabled"] = enabled
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
                if tog:
                    tog.pack(side="right", padx=4)
                if det:
                    det.pack(side="right", padx=2)
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
        self.cfg[f"{section}_enabled"] = False

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
        names = {"isk": "isk", "msn": "missions", "anom": "anomalies", "dps": "dps"}
        return names.get(section, section)

    # Retourne le padding approprié pour une section
    def _get_section_pad(self, section):
        if section == "dps": return dict(padx=6, pady=2)
        return dict(padx=6, pady=(2, 4))

    # Collapse/déplie une section de l'interface
    def _toggle_collapse(self, section):
        attr = f"_{section}_collapsed"
        collapsed = not getattr(self, attr)
        setattr(self, attr, collapsed)
        self.cfg[f"{section}_collapsed"] = collapsed
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

    # Met à jour les labels DPS out/in (live ou frozen)
    def _update_dps_labels(self, labels, frozen=None):
        if not labels: return
        if frozen:
            if labels.get("dps_out"):
                labels["dps_out"].config(text=frozen["dps_out"])
            if labels.get("dps_in"):
                labels["dps_in"].config(text=frozen["dps_in"])
            return

        # live path (dirty flags already handled in _tick for main window)
        dd = self.data.dps(True)
        dr = self.data.dps(False)
        if labels.get("dps_out"):
            labels["dps_out"].config(text=f"{dd:,.0f}")
        if labels.get("dps_in"):
            labels["dps_in"].config(text=f"{dr:,.0f}")
        
        # Update visual bars if this is the detached window
        if labels is self._dps_det_labels and self._dps_detached:
            self._update_dps_bars()

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
            F_alert = tkfont.Font(family="Consolas", size=font_size)
            
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
        self.char_cfg["dps_detached"]   = self._dps_detached
        self.char_cfg["msn_detached"]   = self._msn_detached
        self.char_cfg["anom_detached"]  = self._anom_detached
        self.char_cfg["alert_detached"] = self._alert_detached
        for key, attr in [("isk", "_isk_window"), ("dps", "_dps_window"),
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
            d.bp += a
            d.bc += 1
            if not d.fb:
                d.fb = ts
            self._anom_combat_event(ts)
            self._anom_add_bounty(ts, a)
            return

        if (m := RE_DM.search(raw)):
            d.md += 1
            self._anom_combat_event(ts)
            return

        if RE_NM.search(raw):
            d.mr += 1
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
            self.cfg["storyline_counter"] = self._storyline_ctr
            save_config(self.cfg)
            return

        m = RE_STAND.search(raw)
        if m:
            faction = m.group(1).strip()
            amt = m.group(2)
            d.standings.append((faction, amt))
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
    # Boucle de lecture des logs et chatlog (s'exécute toutes les poll_ms ms)
    def _poll(self):
        try:
            if self._st == "running":
                self._read()
                latest_chat = self._find_latest_chatlog()
                if latest_chat and latest_chat != self._chat_file:
                    self._open_chatlog()
                self._read_chatlog()
                self._check_clipboard()

            elif self._st == "paused":
                self._check_clipboard()

        except Exception:
            pass

        self.root.after(self.poll_ms, self._poll)

    # ── UI tick loop (updates labels) ────────────────────────────────
    # Boucle de mise à jour de l'UI (s'exécute toutes les poll_ms ms)
    def _tick(self):
        self._last_tick_wall = time.monotonic()
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
            main_dps = {"dps_out": self.dps_out, "dps_in": self.dps_in}
            self._update_dps_labels(main_dps, frozen=self._frozen)
            if self._isk_detached and self._isk_det_labels:
                self._update_isk_labels(self._isk_det_labels, frozen=self._frozen)
            if self._dps_detached and self._dps_det_labels:
                self._update_dps_labels(self._dps_det_labels, frozen=self._frozen)
            self.root.after(self.poll_ms, self._tick)
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
        if self._last_values.get("dps_out") != dd:
            self._last_values["dps_out"] = dd
            self.dps_out.config(text=f"{dd:,.0f}")
        if self._last_values.get("dps_in") != dr:
            self._last_values["dps_in"] = dr
            self.dps_in.config(text=f"{dr:,.0f}")

        self._update_breakdown_labels()
        self._update_mission_labels()
        self._update_alert_labels()
        if self._st == "running":
            self._anom_check_gap()
        self._update_anomaly_labels()

        # Detached windows
        if self._isk_detached and self._isk_det_labels:
            self._update_isk_labels(self._isk_det_labels)
        if self._dps_detached and self._dps_det_labels:
            self._update_dps_labels(self._dps_det_labels)

        d.trim()
        self.root.after(self.poll_ms, self._tick)

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
        self.cf = None
        self._close_chatlog()
        self._st = "stopped"
        self._update_buttons()

    # Sauvegarde la session et réinitialise pour le prochain site
    def _next_site(self):

        # Save session to history, close current site, reset everything
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
        self.cf = None
        self._close_chatlog()
        self._st = "stopped"
        self._update_buttons()

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
            with open(self.cf, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            for raw in lines:
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
                
                # Check for bounty line
                m = RE_BT.search(raw)
                if m:
                    amt = pnum(m.group(1))
                    self.data.bg += amt
                    self.data.bp += amt
                    self.data.bc += 1
                    bounties_found += 1
                    total_isk += amt
                    
                    # Track earliest bounty timestamp
                    if earliest_ts is None or ts < earliest_ts:
                        earliest_ts = ts
                    
                    # Set first bounty time if not set
                    if not self.data.fb:
                        self.data.fb = ts
            
            # Adjust session start time to earliest bounty found
            if earliest_ts:
                self.data.t0 = earliest_ts
                # Add alert about backfill
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

    # Retourne le chemin du fichier chatlog le plus récent dans le dossier EVE
    def _find_latest_chatlog(self):
        chat_dir = self.chat_path
        if not os.path.isdir(chat_dir): return None
        best = None
        best_mt = 0
        try:
            for fn in os.listdir(chat_dir):
                if RE_CHATLOG_FN.match(fn):
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
        for attr in ('_isk_window', '_dps_window', '_msn_window',
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

    def _rebuild_ui(self):

        # Full UI rebuild with current theme
        # ── Apply the new theme colors to module globals ──
        apply_theme_colors(self._current_theme)

        # ── Save volatile state ──
        saved_st = self._st

        # ── Save current geometry before hiding ──
        cur_geo = self.root.geometry()

        # ── Hide main window to avoid flicker ──
        self.root.withdraw()

        # ── Close all popup/detached windows (saving positions) ──
        for key, attr in [("isk", "_isk_window"), ("dps", "_dps_window"),
                           ("msn", "_msn_window"), ("anom", "_anom_window"),
                           ("alert", "_alert_window")]:
            try:
                win = getattr(self, attr)
                if win and win.w.winfo_exists():
                    win._save_geometry()
                    win.w.destroy()
            except Exception:
                pass
            setattr(self, attr, None)

        # Remember detached states but reset for rebuild
        isk_det = self._isk_detached
        dps_det = self._dps_detached
        msn_det = self._msn_detached
        anom_det = self._anom_detached
        alert_det = self._alert_detached
        self._isk_detached = False
        self._dps_detached = False
        self._msn_detached = False
        self._anom_detached = False
        self._alert_detached = False
        self._isk_det_labels = {}
        self._dps_det_labels = {}
        self._msn_det_labels = {}
        self._anom_det_labels = {}

        if self._sw and self._sw.w.winfo_exists():
            try: self._sw.w.destroy()
            except Exception:
                pass
            self._sw = None
        if self._hw and self._hw.w.winfo_exists():
            try: self._hw.w.destroy()
            except Exception:
                pass
            self._hw = None

        # ── Clear btn_sets (will be repopulated by _build) ──
        self._btn_sets = []

        # ── Destroy all root children ──
        for w in self.root.winfo_children():
            w.destroy()

        # ── Re-apply styles and rebuild ──
        self._style()
        self._build()

        self.root.config(highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.root.configure(bg=BG)
        self.root.attributes("-alpha", self.alpha)

        # ── Restore exact geometry and show ──
        self.root.geometry(cur_geo)
        self.root.update_idletasks()

        # ── Re-open detached windows ──
        if isk_det:
            self._detach("isk")
        if dps_det:
            self._detach("dps")
        if msn_det:
            self._detach("msn")
        if anom_det:
            self._detach("anom")
        if alert_det:
            self._detach("alert")

        # ── Restore button state ──
        self._update_buttons()

        # ── Show window (smooth reveal) ──
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)

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
        elif section == "dps" and not self._dps_detached:
            self._dps_detached = True
            self._dps_container.grid_remove()
            self._sep_anom_dps.grid_remove()
            self._dps_window = DetachedWindow(self.root, self, "DPS MONITOR", CD, "dps", lambda parent, detached: self._build_dps(parent, detached=True), char_name=self.char_name)
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
        elif section == "dps":
            self._dps_detached = False
            self._dps_window = None
            self._dps_det_labels = {}
            for w in self._dps_container.winfo_children():
                w.destroy()
            self._build_dps(self._dps_container, detached=False)
            self._dps_container.grid()
            self._sep_anom_dps.grid()
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
            d.anom_current = {"start": ts, "end": None, "kills": 0, "isk": 0, "dmg_d": 0, "dmg_r": 0, "hits": 0}
            self._anom_start_wall = time.monotonic()
        d.anom_last_combat = ts
        self._anom_last_wall = time.monotonic()

    # Ajoute les dégâts infligés à l'anomalie en cours
    def _anom_add_dmg_out(self, ts, amount):
        d = self.data
        if d.anom_current:
            d.anom_current["dmg_d"] += amount
            d.anom_current["hits"] += 1

    # Ajoute les dégâts reçus à l'anomalie en cours
    def _anom_add_dmg_in(self, ts, amount):
        d = self.data
        if d.anom_current:
            d.anom_current["dmg_r"] += amount
            d.anom_current["hits"] += 1

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
            total_time = sum((a["end"] - a["start"]).total_seconds() for a in completed if a["end"] and a["start"])
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
            self.w.geometry(f"340x290{saved}")
        else:
            self.w.geometry(
                f"340x290+{parent_root.winfo_x()+30}+{parent_root.winfo_y()+40}")

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

        ap = tk.Label(body, text="✔ APPLY",
                      font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                      bg=BG_POP, fg=CA, cursor="hand2", padx=12)
        ap.pack(side="right", pady=(6, 0))
        ap.bind("<Button-1>", lambda e: self._apply())
        ap.bind("<Enter>",    lambda e: ap.config(bg=BDG))
        ap.bind("<Leave>",    lambda e: ap.config(bg=BG_POP))

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

        try:
            v     = max(20, min(100, int(self.av.get())))
            alpha = v / 100
            cfg["alpha"] = alpha
            mu.root.attributes("-alpha", alpha)
            for win in mu._windows.values():
                win.alpha = alpha
                if win.root.winfo_exists():
                    win.root.attributes("-alpha", alpha)
                for attr in ("_isk_window", "_dps_window", "_msn_window",
                             "_anom_window", "_alert_window"):
                    dw = getattr(win, attr, None)
                    if dw and dw.w.winfo_exists():
                        dw.w.attributes("-alpha", alpha)
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
                    for attr in ('_isk_window', '_dps_window', '_msn_window',
                                 '_anom_window', '_alert_window'):
                        dw = getattr(win, attr, None)
                        if dw and dw.w.winfo_exists():
                            _walk(dw.w)
                            dw.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG)
                    for attr in ('_sw', '_hw'):
                        obj = getattr(win, attr, None)
                        if obj and obj.w.winfo_exists():
                            _walk(obj.w)
                    try:
                        win._style()
                        win._update_buttons()
                    except Exception:
                        pass

        save_config(cfg)


# ── Fleet overview ────────────────────────────────────────────────────
class MainUI:

    MAIN_W    = 360
    _COL_NAME  = 18   # character column width in chars (Consolas 8B)
    _COL_ISK   = 10   # "9.99B/hr" — raw bounty/hr
    _COL_NET   = 10   # "9.99B/hr" — net after tax + loot
    _COL_TIME  =  9   # "00:00:00"

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
        self._rows:    dict = {}   # char_id → {name, isk, net, time, btn}
        self._total_bnt_lbl   = None
        self._total_net_lbl   = None
        self._health_job      = None
        self._settings_win    = None
        self._dx = self._dy = 0
        self._rw = self._rh = self._rx = self._ry = self._wx = self._wy = 0
        self._last_clipboard  = ""  # shared across all CharacterWindows — first to see a paste wins

        self._scan_job       = None
        self._is_collapsed   = False
        self._full_height    = 0
        self._dragging       = False
        self._tray_icon      = None

        self._build()
        self._restore_geometry()
        self._scan()
        self._health_check()
        self._auto_scan()

        if _TRAY_OK:
            self.root.after(500, self._init_tray_icon)

        self.root.deiconify()
        self.root.mainloop()

    # ── Scan logs — spawn a CharacterWindow for every new character ───
    def _scan(self):
        cf = scan_logs(self.cfg.get("log_path", DEF_PATH))
        char_map = self.cfg.setdefault("chars", {})
        for char_id, log_file in cf.items():
            if char_id in self._windows:
                continue
            char_name = rlisten(log_file) or f"Unknown ({char_id})"
            win = CharacterWindow(self.root, self, char_id, char_name, log_file, self.cfg)
            self._windows[char_id] = win
            if char_map.get(char_id, {}).get("show", True):
                win.root.deiconify()
        self._rebuild_rows()

    # ── Auto-scan every 10 s so new characters appear without a button ──
    def _auto_scan(self):
        self._scan()
        self._scan_job = self.root.after(10_000, self._auto_scan)

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

        tk.Frame(body, bg=BD, height=1).pack(fill="x", pady=(0, 1))

        col_hdr = tk.Frame(body, bg=BG)
        col_hdr.pack(fill="x", pady=(0, 2))
        _ch_name = tk.Label(col_hdr, text="CHARACTER",
                            font=F8B, bg=BG, fg=TD,
                            width=self._COL_NAME, anchor="w")
        _ch_name.pack(side="left")
        _ch_isk = tk.Label(col_hdr, text="BOUNTY/HR",
                           font=F8B, bg=BG, fg=TD,
                           width=self._COL_ISK, anchor="e")
        _ch_isk.pack(side="left")
        _ch_net = tk.Label(col_hdr, text="NET/HR",
                           font=F8B, bg=BG, fg=TD,
                           width=self._COL_NET, anchor="e")
        _ch_net.pack(side="left")
        _ch_time = tk.Label(col_hdr, text="SESSION",
                            font=F8B, bg=BG, fg=TD,
                            width=self._COL_TIME, anchor="e")
        _ch_time.pack(side="left")
        self._col_hdrs = {"name": _ch_name, "isk": _ch_isk, "net": _ch_net, "time": _ch_time}

        # Scrollable rows — mousewheel only, no scrollbar widget
        self._canvas = tk.Canvas(body, bg=BG, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)
        self._rows_frame = tk.Frame(self._canvas, bg=BG)
        _win = self._canvas.create_window((0, 0), window=self._rows_frame, anchor="nw")
        self._rows_frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(_win, width=e.width))
        self._canvas.bind("<Enter>", lambda e: self._canvas.bind_all(
            "<MouseWheel>",
            lambda ev: self._canvas.yview_scroll(int(-1*(ev.delta/120)), "units")))
        self._canvas.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))

        tk.Frame(body, bg=BD, height=1).pack(fill="x", pady=(3, 0))
        total_row = tk.Frame(body, bg=BG)
        total_row.pack(fill="x", pady=(2, 0))
        self._total_name_lbl = tk.Label(total_row, text="FLEET TOTAL",
                                         font=F8B, bg=BG, fg=TD,
                                         width=self._COL_NAME, anchor="w")
        self._total_name_lbl.pack(side="left")
        self._total_bnt_lbl = tk.Label(total_row, text="",
                                        font=F8B, bg=BG, fg=CI,
                                        width=self._COL_ISK, anchor="e")
        self._total_bnt_lbl.pack(side="left")
        self._total_net_lbl = tk.Label(total_row, text="",
                                        font=F8B, bg=BG, fg=CG,
                                        width=self._COL_NET, anchor="e")
        self._total_net_lbl.pack(side="left")

        self.root.bind("<Configure>", self._on_main_resize)

    # ── Rebuild all character rows (called after scan or window close) ─
    def _rebuild_rows(self):
        for w in self._rows_frame.winfo_children():
            w.destroy()
        self._rows.clear()

        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9  = tkfont.Font(family="Consolas", size=9)

        for char_id, win in self._windows.items():
            if not win.root.winfo_exists():
                continue
            visible = win.root.winfo_viewable()
            row = tk.Frame(self._rows_frame, bg=BG)
            row.pack(fill="x", pady=1)

            raw = win.char_name
            name_text = f"★ {raw[:16]}" + ("…" if len(raw) > 16 else "")
            # Pack button first so side="right" claims its space before left-side labels
            btn_text = "◎ SHOW" if not visible else "◎ HIDE"
            btn_fg   = CI if not visible else TD
            btn = tk.Label(row, text=btn_text,
                           font=F8B, bg=BG, fg=btn_fg, cursor="hand2", padx=4)
            btn.pack(side="right")

            name_lbl = tk.Label(row, text=name_text,
                                 font=F8B, bg=BG, fg=T0,
                                 width=self._COL_NAME, anchor="w")
            name_lbl.pack(side="left")

            isk_lbl = tk.Label(row, text="—",
                                font=F9, bg=BG, fg=TD,
                                width=self._COL_ISK, anchor="e")
            isk_lbl.pack(side="left")

            net_lbl = tk.Label(row, text="—",
                                font=F9, bg=BG, fg=TD,
                                width=self._COL_NET, anchor="e")
            net_lbl.pack(side="left")

            time_lbl = tk.Label(row, text="00:00:00",
                                 font=F9, bg=BG, fg=TD,
                                 width=self._COL_TIME, anchor="e")
            time_lbl.pack(side="left")
            btn.bind("<Button-1>", lambda e, cid=char_id: self._toggle_window(cid))
            btn.bind("<Enter>",    lambda e, b=btn: b.config(fg=T0))
            btn.bind("<Leave>",    lambda e, b=btn, cid=char_id: b.config(
                fg=CI if not (w := self._windows.get(cid))
                          or not w.root.winfo_viewable() else TD))

            self._rows[char_id] = {
                "name": name_lbl, "isk": isk_lbl,
                "net": net_lbl, "time": time_lbl, "btn": btn,
            }

        self.root.update_idletasks()
        if getattr(self, "_main_last_w", 0) > 0:
            self._apply_col_widths(*self._col_widths_for(self._main_last_w))

    # ── Live stats update + frozen detection ─────────────────────────
    def _health_check(self):
        now = time.monotonic()
        total_bnt = 0.0
        total_net = 0.0
        running_n = 0

        for char_id, win in self._windows.items():
            row = self._rows.get(char_id)
            if not row:
                continue
            if not win.root.winfo_exists():
                continue   # window destroyed outside normal _quit() path

            frozen = (now - getattr(win, "_last_tick_wall", now)) > 1.5
            if frozen:
                row["name"].config(fg=CW)
                row["isk"].config( text="— NO TICK —", fg=CW)
                row["net"].config( text="—",            fg=CW)
                row["time"].config(text="—",            fg=CW)
                continue

            d   = win.data
            st  = win._st
            sec = d.secs()

            if st == "running" and sec >= 60 and d.bg > 0:
                bnt_hr = d.bg / sec * 3600
                net_hr = d.isk()
                total_bnt += bnt_hr
                total_net += net_hr
                running_n += 1
                row["name"].config(fg=T0)
                row["isk"].config( text=fisk(bnt_hr) + "/hr", fg=CI)
                row["net"].config( text=fisk(net_hr) + "/hr",  fg=CG)
                row["time"].config(text=fdur(sec),             fg=TD)
            elif st == "paused":
                row["name"].config(fg=CP)
                row["isk"].config( text="— PAUSED —", fg=CP)
                row["net"].config( text="—",           fg=CP)
                row["time"].config(text=fdur(sec),     fg=TD)
            else:
                row["name"].config(fg=T0)
                row["isk"].config( text="— STANDBY —", fg=TD)
                row["net"].config( text="—",            fg=TD)
                row["time"].config(text="00:00:00",     fg=TD)

        if running_n >= 2:
            self._total_bnt_lbl.config(text=fisk(total_bnt) + "/hr", fg=CI)
            self._total_net_lbl.config(text=fisk(total_net) + "/hr", fg=CG)
        else:
            self._total_bnt_lbl.config(text="")
            self._total_net_lbl.config(text="")

        self._health_job = self.root.after(500, self._health_check)

    # ── Show / hide a character window ───────────────────────────────
    def _toggle_window(self, char_id: str):
        win = self._windows.get(char_id)
        if not win or not win.root.winfo_exists():
            return
        char_cfg = self.cfg.setdefault("chars", {}).setdefault(char_id, {})
        row = self._rows.get(char_id)

        if win.root.winfo_viewable():
            # HIDE — withdraw main + all detached panels (keep widgets alive for _tick)
            panels = [("isk", "_isk_window"), ("dps", "_dps_window"),
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
            if row:
                row["btn"].config(text="◎ SHOW", fg=CI)
        else:
            # SHOW — restore main window and all panels that were visible before hide
            win.root.deiconify()
            win.root.lift()
            panels = [("isk", "_isk_window"), ("dps", "_dps_window"),
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
            if row:
                row["btn"].config(text="◎ HIDE", fg=TD)

        save_config(self.cfg)

    # ── Called by CharacterWindow._quit() when a window closes itself ─
    def _on_char_closed(self, char_id: str):
        self._windows.pop(char_id, None)
        if self.root.winfo_exists():
            self._rebuild_rows()

    # ── Resize grip ──────────────────────────────────────────────────
    def _resize_start(self, e):
        self._rw = self.root.winfo_width()
        self._rh = self.root.winfo_height()
        self._rx = e.x_root
        self._ry = e.y_root
        self._wx = self.root.winfo_x()
        self._wy = self.root.winfo_y()

    def _resize_drag(self, e):
        nw = max(280, self._rw + (e.x_root - self._rx))
        nh = max(100, self._rh + (e.y_root - self._ry))
        self.root.geometry(f"{nw}x{nh}+{self._wx}+{self._wy}")

    def _resize_end(self, e):
        self._save_pos()

    def _col_widths_for(self, w):
        # w is the root window width; body has padx=6 each side (12px total).
        # Button is packed first (side="right") so it always gets its space.
        CHAR_PX  = 6
        inner    = max(80, w - 24)   # body padx (12) + small border allowance (12)
        scale    = max(0.85, min(2.5, inner / 240))
        isk_ch   = max(8,  int(10 * scale))
        net_ch   = max(8,  int(10 * scale))
        time_ch  = max(7,  int(9  * scale))
        name_ch  = max(10, int(max(1, inner - (isk_ch + net_ch + time_ch) * CHAR_PX) / CHAR_PX))
        return name_ch, isk_ch, net_ch, time_ch

    def _on_main_resize(self, event):
        if event.widget is not self.root:
            return  # child widget Configure events propagate up; ignore them
        if getattr(self, "_scaling_main", False):
            return
        w = event.width
        if abs(w - getattr(self, "_main_last_w", 0)) < 3:
            return
        self._main_last_w = w
        self._scaling_main = True
        try:
            self._apply_col_widths(*self._col_widths_for(w))
        finally:
            self._scaling_main = False

    def _apply_col_widths(self, name_ch, isk_ch, net_ch, time_ch):
        hdrs = getattr(self, "_col_hdrs", {})
        if hdrs.get("name"):  hdrs["name"].config(width=name_ch)
        if hdrs.get("isk"):   hdrs["isk"].config(width=isk_ch)
        if hdrs.get("net"):   hdrs["net"].config(width=net_ch)
        if hdrs.get("time"):  hdrs["time"].config(width=time_ch)

        for lbl in (getattr(self, "_total_name_lbl", None),):
            if lbl: lbl.config(width=name_ch)
        for lbl in (getattr(self, "_total_bnt_lbl", None),):
            if lbl: lbl.config(width=isk_ch)
        for lbl in (getattr(self, "_total_net_lbl", None),):
            if lbl: lbl.config(width=net_ch)

        for row_data in getattr(self, "_rows", {}).values():
            if row_data.get("name"):  row_data["name"].config(width=name_ch)
            if row_data.get("isk"):   row_data["isk"].config(width=isk_ch)
            if row_data.get("net"):   row_data["net"].config(width=net_ch)
            if row_data.get("time"):  row_data["time"].config(width=time_ch)

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
            # Force canvas and column widths to recalculate after re-pack
            self._main_last_w = 0
        else:
            self._full_height = self.root.winfo_height()
            self._body.pack_forget()
            self.root.update_idletasks()
            w = self.root.winfo_width()
            x, y = self.root.winfo_x(), self.root.winfo_y()
            self.root.geometry(f"{w}x29+{x}+{y}")
            self._is_collapsed = True

    # ── Settings ─────────────────────────────────────────────────────
    def _settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        self._settings_win = MainUISettings(self.root, self).w

    # ── Geometry ─────────────────────────────────────────────────────
    def _save_pos(self):
        try:
            self.cfg.setdefault("main_ui", {})["geometry"] = self.root.winfo_geometry()
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
                    for attr in ("_isk_window", "_dps_window", "_msn_window",
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
        self._save_pos()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
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