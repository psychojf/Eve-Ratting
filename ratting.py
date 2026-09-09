# -*- coding: utf-8 -*-
# =============================================================================
# EVE RATTING — tableau de bord PvE pour EVE Online
# =============================================================================
# L'app ne lit QUE les fichiers que le client écrit lui-même sur le disque
# (dossier Gamelogs). Pas de lecture mémoire, pas de capture réseau, pas de clé
# API : c'est ce qui la garde conforme à l'EULA, et c'est la contrainte qui
# explique presque toute l'architecture ci-dessous. Tout part de lignes de texte
# horodatées qu'il faut suivre en continu et interpréter au regex — d'où les
# lecteurs incrémentiels, les états dérivés qu'on ne peut jamais interroger
# directement, et le soin mis à ne rien perdre entre deux lectures.
#
# Le tout tient dans un seul fichier volontairement : l'app est distribuée en
# .exe PyInstaller à des joueurs qui n'ont pas Python, et un fichier unique rend
# le build et le partage triviaux.
# =============================================================================
import sys
import tkinter as tk
from tkinter import ttk, font as tkfont
import os, re, json, time, threading, urllib.request, traceback
from datetime import datetime, timedelta, timezone
from collections import deque

# Sous pythonw.exe (mode fenêtre, sans console) sys.stdout vaut None : sans ce
# test, l'exécutable livré planterait dès la première ligne. L'UTF-8 est imposé
# parce que les noms de PNJ et les libellés d'alerte contiennent des symboles
# (étoiles, flèches, crâne) que la console cp1252 refuse d'encoder.
if sys.stdout is not None:
    sys.stdout.reconfigure(encoding='utf-8')

# ── Dépendances optionnelles ─────────────────────────────────────────
# Chacune apporte un confort, aucune n'est vitale : l'app doit démarrer et
# suivre l'ISK même si toutes manquent. Les drapeaux _*_OK gardent ensuite
# chaque fonctionnalité une par une, plutôt que de faire échouer l'import.
_TRAY_OK  = False
_CLIP_OK  = False
# Verrou de presse-papiers : quand il est armé, PLUS AUCUNE lecture n'est faite.
# Le joueur l'arme le temps de copier autre chose que du butin (une cargaison à
# estimer sur un site externe, une fenêtre de contrat, une ligne de marché) —
# tout texte tabulé serait sinon compté comme du loot.
# Volontairement au niveau module, et non attribut de MainUI : les DEUX lecteurs
# doivent le consulter, et l'un d'eux (CharacterWindow._check_clipboard) tourne
# justement dans le cas où _main_ui vaut None.
# Jamais persisté : l'app démarre toujours déverrouillée, pour qu'un verrou
# oublié meure avec le processus au lieu de coûter une soirée de suivi.
_CLIP_LOCK = False
_LOOT_SPIN = ("◐", "◓", "◑", "◒")   # frames du spinner pendant l'estimation du loot
# Sentinelle distincte de None : _cset doit pouvoir mémoriser une valeur None
# sans la confondre avec « rien encore en cache ».
_UNSET = object()

try:
    import pyperclip
    _CLIP_OK = True
except ImportError:
    # Absence normale, pas une panne : on perd seulement l'estimation du loot.
    # NE PAS remplacer par _log_exc() — il est défini ~200 lignes plus bas, donc
    # l'appeler ici lèverait un NameError et l'app ne démarrerait pas du tout.
    pass

try:
    import pystray
    from PIL import Image, ImageDraw, ImageTk
    _TRAY_OK = True
except ImportError:
    # Idem : sans pystray/Pillow on perd l'icône de zone de notification.
    # Même interdiction d'appeler _log_exc ici (voir juste au-dessus).
    pass

# Lecture des logs pilotée par événement plutôt que par minuterie : le sondage
# fixe réveillait le thread UI quatre fois par seconde pour rien la plupart du
# temps. Optionnel parce que l'.exe déjà distribué n'embarque pas watchdog —
# sans lui on retombe sur le sondage, donc l'ancien binaire est inchangé.
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    _WATCHDOG_OK = True
except ImportError:
    _WATCHDOG_OK = False
    Observer = None
    # Classe de repli : _LogEventHandler hérite d'elle plus bas, donc sans ce
    # stub le fichier ne serait même pas importable quand watchdog manque.
    class FileSystemEventHandler:
        pass

# Bips d'alerte EWAR. winsound est dans la stdlib mais uniquement sous Windows :
# le try préserve la compatibilité Linux/Proton, où l'app tourne aussi.
try:
    import winsound
    _SND_OK = True
except ImportError:
    _SND_OK = False

# ── Palette ──────────────────────────────────────────────────────────
# Volontairement très sombre : l'app se pose par-dessus EVE, et un fond clair
# éblouirait le joueur en pleine session nocturne. Les tons repris de l'UI du jeu
# évitent aussi que la fenêtre paraisse étrangère au client.
# Ces noms sont RÉASSIGNÉS à chaud par apply_theme_colors() à chaque changement
# de thème : d'où des globales plutôt qu'un dictionnaire, puisque tout le code de
# construction des widgets les lit directement.
BG       = "#080808"    # Fond principal (carbone profond)
BG_P     = "#121212"    # Fond de panneau
BG_H     = "#1a1a1a"    # Fond d'en-tête
BG_C     = "#080808"    # Fond des champs et combos
BG_POP   = "#121212"    # Fond des popups
BD       = "#2a2a2a"    # Bordure standard
BDG      = "#333333"    # Bordure de survol / focus
T0       = "#8b9fa9"    # Texte accentué (bleu-gris de l'UI EVE)
T1       = "#6a7a85"    # Texte accentué secondaire
TB       = "#e5e5e5"    # Texte de base
TD       = "#777777"    # Texte atténué
# Couleurs sémantiques : chacune porte un SENS, pas juste une teinte. Le joueur
# lit la fenêtre du coin de l'œil pendant un combat, donc la couleur doit
# suffire à comprendre sans lire — vert = ce qui rentre, rouge = ce qui menace.
CD       = "#8b9fa9"    # DPS sortant / accent générique
CR       = "#cc3325"    # DPS entrant — rouge, c'est ce qui vous tue
CG       = "#d4b45d"    # Bounties et kills — l'or du gain brut
CI       = "#55a34f"    # ISK net — vert, le chiffre qu'on vient chercher
CT       = "#c45b47"    # Taxes — rougeâtre, ce que la corpo prélève
CK       = "#896a9e"    # État transitoire (calcul en cours)
CW       = "#c48b47"    # Avertissement
CM       = "#777777"    # Valeur absente ou inactive
CA       = "#55a34f"    # Session active (Play)
CP       = "#b89645"    # Session en pause
CS       = "#cc3325"    # Stop / Effacer — actions destructrices
CH       = "#5c7b8c"    # Historique
C_DETACH = "#8b9fa9"    # Bouton de détachement de panneau
C_MSN    = "#5b9bd5"    # Accent du suivi de mission
C_ALERT  = "#e07040"    # Accent d'alerte / danger
C_ESCAL  = "#d4b45d"    # Escalade détectée
C_ANOM   = "#5b8fa8"    # Accent du suivi d'anomalies
C_EWAR   = "#ff6b6b"    # Alerte EWAR (scram/web) — rouge doux

# ── Thèmes ───────────────────────────────────────────────────────────
# Les trois helpers ci-dessous existent pour qu'un thème se décrive avec DEUX
# couleurs seulement (un fond et un accent) au lieu des 28 clés d'une palette
# complète. Ajouter une faction devient une ligne, et les rapports de contraste
# restent cohérents d'un thème à l'autre puisqu'ils sont calculés, pas choisis.

# Éclaircit en ajoutant une constante à chaque canal — additif plutôt que
# multiplicatif, sinon un fond quasi noir (#080808) resterait noir.
def _lighten(hx, amt):
    h = hx.lstrip('#')
    r = min(255, int(h[0:2], 16) + amt)
    g = min(255, int(h[2:4], 16) + amt)
    b = min(255, int(h[4:6], 16) + amt)
    return f"#{r:02x}{g:02x}{b:02x}"

# Assombrit par facteur : ici le multiplicatif est le bon choix, il préserve la
# teinte de l'accent au lieu de la tirer vers le gris.
def _dim(hx, factor=0.6):
    h = hx.lstrip('#')
    r = int(int(h[0:2], 16) * factor)
    g = int(int(h[2:4], 16) * factor)
    b = int(int(h[4:6], 16) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

# Mélange linéaire de deux teintes : sert à teinter une couleur fonctionnelle
# (historique, mission, anomalie) vers l'accent du thème, pour qu'elle reste
# reconnaissable tout en appartenant visuellement à la palette choisie.
def _blend(h1, h2, t=0.5):
    a = h1.lstrip('#')
    b = h2.lstrip('#')
    r = int(int(a[0:2], 16) * (1 - t) + int(b[0:2], 16) * t)
    g = int(int(a[2:4], 16) * (1 - t) + int(b[2:4], 16) * t)
    bl = int(int(a[4:6], 16) * (1 - t) + int(b[4:6], 16) * t)
    return f"#{min(255,r):02x}{min(255,g):02x}{min(255,bl):02x}"

# Déploie les deux couleurs d'une faction en palette complète.
# Les couleurs de STATUT (rouge de danger, vert du gain, or des bounties) sont
# volontairement figées et non dérivées de l'accent : leur rôle est d'être lues
# instantanément, et elles perdraient ce sens si chaque thème les repeignait.
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

# Réécrit les globales de couleur en place. C'est un effet de bord assumé :
# les widgets Tk gardent la couleur qu'on leur a passée à la construction, donc
# changer de thème demande de repeindre chaque widget un par un (voir
# _apply_theme_live). Passer par des globales permet à ce repeignage de lire
# simplement la nouvelle valeur, sans trimballer un objet palette partout.
# Un nom inconnu retombe sur le thème par défaut plutôt que de lever : la config
# peut venir d'une version antérieure où le thème existait encore.
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

# ── Chemins et valeurs par défaut ────────────────────────────────────
# Sous PyInstaller, __file__ pointe dans le dossier temporaire d'extraction qui
# disparaît à la fermeture : config et historique y seraient perdus à chaque
# lancement. On ancre donc tout à côté de l'exécutable réel.
if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))

# Quatre fichiers distincts plutôt qu'un seul : ils n'ont ni la même durée de
# vie ni le même coût. La config change à chaque geste de l'utilisateur,
# l'historique ne fait que grandir, et les deux caches ESI sont jetables — on
# peut les supprimer sans rien perdre, ils se reconstruiront tout seuls.
CONFIG_FILE  = os.path.join(_BASE, "ratting_config.json")
HISTORY_FILE = os.path.join(_BASE, "ratting_history.json")
PRICE_CACHE  = os.path.join(_BASE, "ratting_prices.json")
NAMEID_CACHE = os.path.join(_BASE, "ratting_nameids.json")

# ── Journal de débogage ──────────────────────────────────────────────
# Ce fichier avale volontairement ~100 exceptions (une fenêtre détruite en
# plein tick ne doit pas tuer l'app), mais un `except: pass` muet rend tout
# diagnostic impossible sur la machine de l'utilisateur. _log_exc() conserve
# exactement ce comportement — l'exception reste avalée — et se contente
# d'écrire la trace dans ratting_debug.log QUAND le debug est actif.
# Désactivé : un simple test booléen, rien n'est écrit ni formaté.
# Activation : variable d'environnement EVE_RATTING_DEBUG=1, ou "debug_log":
# true dans ratting_config.json.
DEBUG_LOG_FILE = os.path.join(_BASE, "ratting_debug.log")
DEBUG_LOG_MAX  = 512 * 1024          # octets — au-delà, le fichier repart à zéro
_DEBUG_ON  = os.environ.get("EVE_RATTING_DEBUG", "") not in ("", "0")
_LOG_LOCK  = threading.Lock()

def _log_exc(context=""):
    """Consigne l'exception en cours de traitement, puis la laisse être avalée.

    Le contrat est important : cette fonction ne relance JAMAIS et ne change
    jamais le flot d'exécution. Elle s'insère dans des `except` déjà existants
    sans rien modifier au comportement de l'app.
    """
    if not _DEBUG_ON:
        return
    try:
        with _LOG_LOCK:
            try:
                if os.path.getsize(DEBUG_LOG_FILE) > DEBUG_LOG_MAX:
                    os.remove(DEBUG_LOG_FILE)
            except OSError:
                pass
            with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
                f.write("[%s] %s\n" % (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), context))
                f.write(traceback.format_exc())
                f.write("\n")
    except Exception:
        # Journaliser ne doit jamais devenir la cause d'une panne : si l'écriture
        # échoue (disque plein, dossier en lecture seule), on abandonne en
        # silence plutôt que de faire remonter une exception depuis un `except`.
        pass

# CCP demande un User-Agent descriptif sur l'ESI : les requêtes anonymes se font
# limiter puis bloquer, ce qui casserait silencieusement l'estimation du loot.
_ESI_UA = "Eve-Ratting/1.0 (+https://github.com/psychojf/Eve-Ratting)"

# Chaque CharacterWindow lance son propre thread de prix au démarrage. Sans ce
# verrou, cinq personnages = cinq téléchargements ESI simultanés du même
# catalogue et cinq écritures concurrentes sur ratting_prices.json, qui finissait
# tronqué. Ici le premier thread télécharge, les autres attendent puis relisent.
_PRICE_LOCK = threading.Lock()
# Même problème sur le cache nom→type_id, écrit par les threads de loot de
# toutes les fenêtres : le verrou permet la fusion lecture-modification-écriture
# sans qu'un thread écrase les identifiants qu'un autre vient de résoudre.
_NAMEID_LOCK = threading.Lock()

def _find_eve_log_path(subdir):
    """Premier chemin de logs EVE existant, selon l'installation.

    EVE tourne aussi sous Linux via Proton, où le client écrit dans une
    arborescence Wine complètement différente. Plutôt que de demander le chemin
    à l'utilisateur au premier lancement, on teste les emplacements connus.
    """
    candidates = [
        # Windows / macOS natif
        os.path.join(os.path.expanduser("~"), "Documents", "EVE", "logs", subdir),
        # Client Linux natif
        os.path.join(os.path.expanduser("~"), ".eve", "sharedcache", "tq", "logs", subdir),
        # Steam / Proton (bibliothèque Steam par défaut)
        os.path.join(os.path.expanduser("~"), ".local", "share", "Steam",
                     "steamapps", "compatdata", "8500", "pfx", "drive_c",
                     "users", "steamuser", "My Documents", "EVE", "logs", subdir),
        # Steam avec bibliothèque déportée sur un second disque
        os.path.join("/mnt", "ssd", "SteamLibrary", "steamapps", "compatdata",
                     "8500", "pfx", "drive_c", "users", "steamuser",
                     "My Documents", "EVE", "logs", subdir),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    # Rien trouvé : on renvoie quand même le chemin Windows. L'app démarre, la
    # liste de personnages reste vide, et l'utilisateur peut corriger le chemin
    # dans les réglages — préférable à un plantage au lancement.
    return candidates[0]

DEF_PATH     = _find_eve_log_path("Gamelogs")
DEF_POLL     = 250   # ms — assez rapide pour que le DPS paraisse continu, assez
                     # lent pour ne pas saturer le thread UI avec N personnages
DEF_TAX      = 12.5  # taux de taxe corpo le plus courant en nullsec
DEF_ALPHA    = 0.85  # légère transparence par défaut : on doit deviner le jeu
                     # derrière la fenêtre sans perdre la lisibilité
DPS_W        = 15    # s — fenêtre glissante du DPS. Trop court, le chiffre
                     # saute entre deux salves ; trop long, il ne réagit plus
WIN_W        = 290   # px — largeur pensée pour tenir dans un coin d'écran
MAX_ALERTS   = 5     # au-delà, le fil d'alertes fait grandir la fenêtre et
                     # noie l'information importante sous l'ancienne
ANOM_GAP     = 45    # s sans combat = changement de site. Couvre un warp et
                     # l'approche, sans couper une pause de rechargement
BACKFILL_MINS = 15   # au Play, on rattrape les bounties déjà tombées : le
                     # joueur lance souvent l'app après avoir commencé à ratter
MAX_HISTORY  = 1000  # sessions gardées dans ratting_history.json ; le fichier
                     # grossissait sans limite alors que la fenêtre n'en montre
                     # que 100, filtrées par personnage
DPS_GRAPH_W  = 120   # s — profondeur d'historique du graphique DPS
DPS_GRAPH_H  = 50    # px — hauteur du graphique intégré

# ── Transparence de l'overlay DPS ────────────────────────────────────
# Couleur-clé : sous Windows, -transparentcolor rend totalement invisible tout
# pixel de cette teinte exacte. C'est ce qui permet à l'overlay de n'afficher que
# les chiffres, sans cadre, comme la fenêtre « messages » d'EVE.
# Presque noir plutôt que noir pur : le lissage des polices crée un halo autour
# des lettres, et un ton sombre le fait disparaître dans le fond spatial du jeu.
OVERLAY_KEY     = "#010101"
# Fond opaque affiché UNIQUEMENT pendant le repositionnement : sans lui, il n'y
# aurait presque rien à attraper à la souris dans la vue « chiffres seuls ».
# Retour à OVERLAY_KEY dès que l'overlay est posé.
OVERLAY_MOVE_BG = "#0d0d12"

# ── Motifs de nom de fichier et d'en-tête ────────────────────────────
# EVE nomme ses gamelogs <date>_<heure>_<charID>.txt. Le charID final est la clé
# de toute l'app multi-comptes : c'est le seul identifiant stable pour rattacher
# un fichier à un personnage — le nom affiché, lui, peut changer.
RE_CF = re.compile(r'^(\d{8})_(\d{6})_(\d+)\.txt$')
# Le nom lisible n'apparaît que dans l'en-tête « Listener: », d'où une lecture
# des premières lignes du fichier pour l'obtenir (voir rlisten).
RE_LI = re.compile(r'Listener:\s*(.+)',              re.I)
# Horodatage préfixant chaque ligne. Utilisé surtout par le rattrapage, qui doit
# savoir DE QUAND date une bounty pour décider s'il la recompte.
RE_TS = re.compile(r'\[\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})\s*\]')
# Bandeau de début de fichier : reconnu pour être ignoré, pas pour être exploité.
RE_SS = re.compile(r'Session\s+Started:\s*(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})', re.I)

# ── Motifs de combat ─────────────────────────────────────────────────
# EVE écrit les lignes de combat en DEUX formats selon les réglages du client :
# soit truffées de balises HTML de couleur, soit en texte brut. D'où les motifs
# en alternance — groupes 1-3 pour la variante HTML, 4-6 pour la variante
# brute — et le `m.group(1) or m.group(4)` systématique côté appelant.
# Les faire cohabiter dans un seul motif évite de tester deux regex par ligne
# sur un flux qui peut dépasser la centaine de lignes par seconde en combat.

RE_TO = re.compile(                                            # dégâts sortants
    r'\(combat\)\s*(?:<[^>]+>)*<b>(\d+)</b>.*?\bto\b'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+?)</b>.*?-\s*(.+)$'
    r'|\(combat\)\s+(\d+)\s+to\s+([\w\s\'-]+?)\s+-\s+(.+)$',
    re.I
)
RE_FR = re.compile(                                            # dégâts entrants
    r'\(combat\)\s*(?:<[^>]+>)*<b>(\d+)</b>.*?\bfrom\b'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+?)</b>.*?-\s*(.+)$'
    r'|\(combat\)\s+(\d+)\s+from\s+([\w\s\'-]+?)\s+-\s+(.+)$',
    re.I
)
# Les tirs manqués ne changent ni le DPS ni l'ISK, mais ils prouvent qu'un
# combat est EN COURS : sans eux, une passe où l'on ne touche rien ressemblerait
# à un trou de combat et clôturerait l'anomalie à tort.
RE_NM = re.compile(r'\(combat\)\s*([\w\s\'-]+?)\s+misses\s+you\s+completely',   re.I)  # PNJ qui rate
RE_DM = re.compile(r'\(combat\)\s+Your\s+(.+?)\s+misses\s+([\w\s\'-]+?)\s+completely', re.I)  # drone qui rate

# ── Motif de paiement de bounty ──────────────────────────────────────
# Seule source de vérité sur l'ISK gagné : le client n'expose le total nulle
# part ailleurs sur le disque. Le montant est capturé en tolérant espaces,
# virgules et points, car le séparateur de milliers suit la locale du client.
RE_BT = re.compile(r'\(bounty\)\s*(?:<[^>]+>)*([\d\s,.]+)\s*ISK.*?added\s+to\s+next\s+bounty\s+payout', re.I)

# ── Mots-clés de loot de faction ─────────────────────────────────────
# Sert d'aiguillage de prix, pas de reconnaissance d'objet : un item portant un
# de ces préfixes vaut assez cher pour justifier un appel ESI sur le marché de
# Jita, alors que le reste se contente du prix moyen déjà en cache. Sans ce tri,
# une seule cargaison déclencherait des centaines de requêtes.
RE_FACTION_ITEM = re.compile(
    r'\b(Shadow|Dread|True|Dark|Sentient|Infested|'
    r'Caldari Navy|Amarr Navy|Federation Navy|Republic Fleet|'
    r'Pith|Gist|Corpus|Core|C-Type|B-Type|A-Type|X-Type)\b',
    re.I
)

# ── Motifs de mission et d'alerte (gamelog) ──────────────────────────
# Objectif rempli : le joueur peut rentrer voir l'agent. Signalé parce qu'on le
# rate facilement quand la fenêtre de mission est fermée pendant le combat.
RE_OBJ_MET  = re.compile(r'Objective accomplished\.\s*You may now return to your agent\.', re.I)
# Mission terminée. Alimente le compteur de storyline : EVE en propose une tous
# les 16 rendus, et rien dans le client ne dit où on en est dans ce cycle.
RE_MSN_COMP = re.compile(r'You completed mission\s+(\d+)',                                 re.I)
RE_STAND    = re.compile(r'Your standings with\s+(.*?)\s+have increased by\s+([\d.]+)',    re.I)
# Apparition d'un PNJ de faction sur la grille : ça vaut cher, et ça tape plus
# fort — le joueur veut le savoir avant de le découvrir dans son overview.
RE_FACTION  = re.compile(r'\(combat\).*?\b(Shadow|Dread|True|Dark|Sentient|Infested|Caldari Navy|Amarr Navy)\b\s+([\w\s]+?)\s*-\s*Hits', re.I)
# Dreadnought : menace mortelle en anomalie, l'alerte doit être immédiate.
RE_DREAD    = re.compile(r'\(notify\)\s+(.*?)\s*Dreadnought detected',                    re.I)
# Escalade : le site vient de se prolonger ailleurs, avec une fenêtre de temps
# limitée pour la suivre. Facile à manquer dans le flot du journal.
RE_ESCAL    = re.compile(r'A portion of the\s+(.*?)\s+database reveals the potential location', re.I)

# ── Motifs EWAR (scram / web) ────────────────────────────────────────
# Les deux événements qui empêchent de FUIR : sans warp, un joueur distrait
# perd son vaisseau. C'est la seule catégorie d'alerte doublée d'un bip sonore.
# Groupe 1 = attaquant en HTML, groupe 2 = attaquant en texte brut.
RE_SCRAM = re.compile(
    r'\(combat\)\s*(?:<[^>]+>)*(?:<b>)?Warp\s+scramble\s+attempt(?:</b>)?'
    r'.*?<b>(?:<[^>]+>)?([\w\s\'-]+)</b>'
    r'|\(combat\)\s+Warp\s+scramble\s+attempt\s+from\s+([\w\s\'-]+?)\s+to\s+you',
    re.I
)
# Le web arrive dans le GAMELOG, en ligne (notify), comme tous les autres
# événements de ce type. Il était autrefois cherché dans les chatlogs, où il ne
# pouvait structurellement jamais correspondre : une ligne de chat s'écrit
# « [ horodatage ] Locuteur > message » et ne porte aucune balise (notify).
# La variante balisée est tolérée par symétrie avec RE_SCRAM — seule la forme
# brute a été observée dans de vrais gamelogs, les balises sont une assurance.
RE_WEB = re.compile(
    r'\(notify\)\s*(?:<[^>]+>)*(?:<b>)?([\w\s\'-]+?)(?:</b>)?(?:<[^>]+>)*'
    r'\s+has\s+started\s+webifying\s+you',
    re.I
)

# ── Fonctions utilitaires ────────────────────────────────────────────
# Le client peut colorer ses lignes de journal en HTML ; on ne garde que le
# texte, sinon les noms de PNJ s'afficheraient avec leurs balises dans l'UI.
def shtml(t): return re.sub(r'<[^>]+>', '', t).strip()

# Lit un entier quel que soit le séparateur de milliers du client (« 1 234 567 »,
# « 1,234,567 », « 1.234.567 » selon la locale) — d'où le nettoyage préalable
# plutôt qu'un int() direct.
def pnum(s):
    # Fonction TOTALE par conception : les appelants traitent 0 comme « pas de
    # nombre exploitable » et se rabattent sur autre chose.
    # Elle levait autrefois ValueError sur du texte non numérique, ce qui tuait
    # net le thread d'estimation du loot (voir _process_loot_copy) : n'importe
    # quel presse-papiers contenant une tabulation lui parvient — une ligne de
    # tableur, un tableau copié d'une page web, du code indenté.
    cleaned = re.sub(r'[\s,.]+', '', s.strip())
    if not cleaned:
        return 0
    try:
        return int(cleaned)
    except ValueError:
        return 0

# Notation courte : les montants dépassent vite le milliard, et une colonne de
# chiffres bruts serait illisible du coin de l'œil pendant un combat.
def fisk(v):
    if v >= 1e9: return f"{v/1e9:.2f}B"
    if v >= 1e6: return f"{v/1e6:.2f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return f"{v:,.0f}"

# Forme longue, réservée au détail où le joueur veut le montant exact ; l'espace
# comme séparateur reprend la convention d'affichage du client EVE.
def fiskf(v): return f"{int(v):,}".replace(",", " ")

# Toujours en HH:MM:SS, même sous l'heure : une largeur de champ constante évite
# que les colonnes du tableau de flotte ne sautillent à chaque rafraîchissement.
def fdur(s):
    # Le max(0) protège d'une durée négative quand l'horloge système recule
    # (mise à l'heure NTP) entre le début de session et le calcul.
    s = max(0, int(s))
    h, r = divmod(s, 3600)
    m, s2 = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s2:02d}"

# La queue d'une ligne de combat porte l'arme et la qualité du coup, séparées
# par des tirets. Le repli sur « Unknown » évite qu'une ligne au format
# inattendu (module inconnu, traduction du client) fasse échouer tout le parsing
# de la ligne alors que les dégâts, eux, ont bien été lus.
def ptail(t):
    t = shtml(t)
    p = [x.strip() for x in t.split(" - ") if x.strip()]
    if len(p) >= 2: return p[0], p[-1]
    return ("Unknown", p[0]) if p else ("Unknown", "Hits")


# Dessine les polylignes d'historique DPS (OUT/IN) sur un Canvas Tk.
# Partagé par le panneau DPS détaché et l'overlay DPS autonome.
def draw_dps_graph(canvas, hist, *, is_detached=False):
    """Trace les courbes DPS sortant / entrant à partir d'un deque de
    (horodatage monotone, dps_out, dps_in). L'appelant garantit que le canvas
    existe et est affichable.

    Met à jour les objets du canvas EN PLACE plutôt que delete("all") suivi
    d'une recréation à chaque rafraîchissement : reconstruire une polyligne de
    ~480 points quatre fois par seconde est la cause classique de scintillement
    sur un canvas Tk, et on dessine ici sur un overlay transparent toujours au
    premier plan. Les objets ne sont recréés qu'au redimensionnement ou au
    changement de thème — l'ancienne approche « tout effacer » suivait les
    couleurs gratuitement, il faut donc désormais le gérer explicitement.
    """
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    # Tk renvoie 1x1 tant que le widget n'a pas été disposé : dessiner à ce
    # moment-là produirait une courbe écrasée qu'il faudrait redessiner juste
    # après. On attend simplement le prochain rafraîchissement.
    if w < 10 or h < 10:
        return

    pad_x, pad_y = 2, 3
    gw = w - pad_x * 2
    gh = h - pad_y * 2
    col_out  = CD
    col_in   = _dim(CR, 0.4)
    palette  = (col_out, col_in, BD, TD)

    items = getattr(canvas, "_dps_items", None)
    if (items is None or items["size"] != (w, h)
            or items["detached"] != is_detached or items["palette"] != palette):
        canvas.delete("all")
        items = {"size": (w, h), "detached": is_detached, "palette": palette,
                 "out": None, "in": None, "label": None, "label_text": None}
        for frac in (0.25, 0.50, 0.75):
            gy = pad_y + gh - frac * gh
            canvas.create_line(pad_x, gy, w - pad_x, gy, fill=BD, dash=(2, 4), tags="grid")
        # Créés masqués avec des coordonnées bidon : la géométrie réelle est
        # posée plus bas à chaque rafraîchissement via canvas.coords(). Créer
        # les objets une seule fois est tout l'intérêt de la manœuvre.
        items["in"]  = canvas.create_line(0, 0, 0, 0, fill=col_in, width=1,
                                          smooth=True, tags="line_in", state="hidden")
        items["out"] = canvas.create_line(0, 0, 0, 0, fill=col_out,
                                          width=2 if is_detached else 1,
                                          smooth=True, tags="line_out", state="hidden")
        if is_detached and h > 40:
            items["label"] = canvas.create_text(pad_x + 2, pad_y + 2, text="",
                                                font=("Consolas", 7), fill=TD,
                                                anchor="nw", tags="label")
        canvas._dps_items = items

    def _hide_lines():
        for key in ("out", "in"):
            if items[key] is not None:
                canvas.itemconfigure(items[key], state="hidden")

    if len(hist) < 2:
        _hide_lines()
        return
    cutoff = time.monotonic() - DPS_GRAPH_W
    pts = [(t, do, di) for t, do, di in hist if t >= cutoff]
    if len(pts) < 2:
        _hide_lines()
        return

    # Échelle automatique, avec un plancher à 100 : sans lui, un DPS résiduel de
    # 3 remplirait toute la hauteur et donnerait l'illusion d'un gros combat.
    max_dps = max(max(do for _, do, _ in pts), max(di for _, _, di in pts), 100)
    # 10 % de marge en haut pour que le pic ne colle pas au bord du cadre.
    y_max = max_dps * 1.1

    def _px(t, v):
        x = pad_x + ((t - cutoff) / DPS_GRAPH_W) * gw
        y = pad_y + gh - (v / y_max) * gh
        return x, y

    coords_out, coords_in = [], []
    any_out = any_in = False
    for t, do, di in pts:
        ox, oy = _px(t, do)
        ix, iy = _px(t, di)
        coords_out.extend([ox, oy])
        coords_in.extend([ix, iy])
        if do > 0: any_out = True
        if di > 0: any_in = True

    for key, coords, visible in (("in", coords_in, any_in), ("out", coords_out, any_out)):
        item = items[key]
        if item is None:
            continue
        if visible:
            canvas.coords(item, *coords)
            canvas.itemconfigure(item, state="normal")
        else:
            canvas.itemconfigure(item, state="hidden")

    if items["label"] is not None:
        txt = f"{max_dps:,.0f}"
        if txt != items["label_text"]:
            items["label_text"] = txt
            canvas.itemconfigure(items["label"], text=txt)

# Le nom du personnage n'existe nulle part ailleurs : le nom de fichier ne porte
# que son identifiant numérique. Il faut donc ouvrir le log pour l'afficher.
def rlisten(fp):
    try:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            # On s'arrête après quelques lignes : l'en-tête est en tête de
            # fichier, et un gamelog de plusieurs heures pèse des mégaoctets
            # qu'il serait absurde de parcourir pour une seule ligne.
            for i, l in enumerate(f):
                if i > 15: break
                m = RE_LI.search(l)
                if m: return m.group(1).strip()
    except Exception:
        _log_exc("rlisten:506")
    return None

# Point d'entrée de la détection automatique des personnages : c'est en trouvant
# un gamelog qu'on découvre qu'un pilote existe, sans rien demander au joueur.
def scan_logs(base):
    """char_id → chemin du gamelog le plus récent de ce personnage.

    os.scandir plutôt que os.walk + os.path.getmtime : sous Windows, l'objet
    DirEntry porte déjà les métadonnées issues de l'énumération du dossier, donc
    .stat() est gratuit, là où getmtime() coûte un appel système par fichier.
    EVE ne purge jamais le dossier Gamelogs, donc ce coût grandit pendant toute
    la vie de l'installation — et cette fonction tourne sur le thread Tk.

    On ne garde que le fichier le plus récent par personnage : EVE en ouvre un
    nouveau à chaque session de jeu, et seul le dernier est encore alimenté.
    """
    r  = {}         # char_id → chemin du log le plus récent
    mt = {}         # char_id → mtime de ce chemin (évite de re-stat à chaque comparaison)
    if not os.path.isdir(base): return r
    stack = [base]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                            continue
                        m = RE_CF.match(e.name)
                        if not m:
                            continue
                        c   = m.group(3)
                        fmt = e.stat().st_mtime
                        if c not in r or fmt > mt[c]:
                            r[c]  = e.path
                            mt[c] = fmt
                    except OSError:
                        # Fichier disparu ou verrouillé entre l'énumération et
                        # le stat : on l'ignore plutôt que d'interrompre tout le
                        # balayage et de perdre les autres personnages.
                        continue
        except OSError:
            continue
    return r

# Une config absente ou corrompue renvoie {} plutôt que de lever : l'app doit
# démarrer avec ses valeurs par défaut, quitte à perdre les réglages, plutôt que
# de refuser de s'ouvrir. Tous les lecteurs utilisent .get() avec un défaut.
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Deuxième moyen d'activer le journal de débogage, à côté de
            # EVE_RATTING_DEBUG : dans l'.exe livré, définir une variable
            # d'environnement est peu commode pour un utilisateur non technique.
            if cfg.get("debug_log"):
                global _DEBUG_ON
                _DEBUG_ON = True
            return cfg
        except Exception:
            _log_exc("load_config:559")
    return {}

# Écriture atomique : fichier temporaire, puis os.replace.
# open(path, "w") tronque la cible AVANT d'écrire — un plantage ou une coupure
# de courant en plein milieu laissait un ratting_config.json vide, donc toute la
# configuration perdue (géométries, sections, réglages par personnage). Le cache
# de prix et le cache nom→id suivaient déjà ce motif ; la config et l'historique
# étaient restés en écriture directe.
# Le fsync force l'écriture physique avant le remplacement : sans lui, os.replace
# peut être visible sur le disque avant les données elles-mêmes.
def _atomic_write_json(path, payload, indent=2):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=indent, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            # Ne pas laisser traîner un .tmp partiel : au prochain démarrage il
            # ressemblerait à un fichier légitime pour qui inspecte le dossier.
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            _log_exc("_atomic_write_json:581")
        return False

# Appelée depuis une trentaine d'endroits, souvent en réaction directe à un
# geste de l'utilisateur (déplacer une fenêtre, replier une section) : c'est
# précisément pour ça que l'écriture doit être atomique et bon marché.
def save_config(cfg):
    _atomic_write_json(CONFIG_FILE, cfg)

# Comme la config : un historique illisible renvoie une liste vide plutôt que
# d'empêcher l'app de démarrer — perdre l'historique est ennuyeux, ne pas
# pouvoir ratter l'est davantage.
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            _log_exc("load_history:595")
    return []

# Sauvegarde de l'historique (écriture atomique).
# Ne conserve que les MAX_HISTORY entrées les plus récentes : le fichier
# grossissait sans limite alors que la fenêtre d'historique n'en affiche que
# 100. Le plafond reste large parce que ce filtrage des 100 se fait APRÈS
# sélection du personnage : un plafond serré affamerait un pilote peu joué.
def save_history(entries):
    if len(entries) > MAX_HISTORY:
        entries = entries[-MAX_HISTORY:]
    _atomic_write_json(HISTORY_FILE, entries)

# Sauvegarde les données de la session courante dans l'historique
def save_session(data, char_name, tax_pct):
    # Rien gagné, rien tiré, rien looté : la session n'apprend rien au joueur et
    # ne ferait que polluer l'historique. Le cas est fréquent — ouvrir l'app,
    # regarder, refermer.
    if data.bg <= 0 and data.dd <= 0 and data.loot_val <= 0:
        return
    # Instantané APLATI plutôt qu'une référence à l'objet Data : la session est
    # remise à zéro juste après, et l'historique doit rester lisible tel quel
    # dans le JSON, sans dépendre de la structure interne du code.
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
        # Le max(..., 1) évite la division par zéro quand aucun site n'a été
        # bouclé ; le filtre sur end/start écarte un site encore ouvert, dont la
        # durée n'a pas de sens.
        "avg_site_time": int(sum(
            max(0, (a["end"] - a["start"]).total_seconds())
            for a in data.anom_completed if a["end"] and a["start"]
        ) / max(len(data.anom_completed), 1)),
        "avg_site_isk":  int(sum(a["isk"] for a in data.anom_completed)
                             / max(len(data.anom_completed), 1)),
        "best_site_isk": max((a["isk"] for a in data.anom_completed), default=0),
    }
    # Relecture systématique avant l'ajout : plusieurs fenêtres de personnage
    # peuvent archiver leur session à quelques secondes d'intervalle, et garder
    # une liste en mémoire ferait perdre l'entrée écrite par la précédente.
    hist = load_history()
    hist.append(entry)
    save_history(hist)


# ── Infobulles ───────────────────────────────────────────────────────
# Infobulle maison plutôt que le tooltip d'un toolkit : les fenêtres de l'app
# sont en overrideredirect (sans décoration), toujours au premier plan et
# semi-transparentes, contraintes qu'aucun widget standard ne respecte.
class Tooltip:

    # add="+" pour ne pas écraser les liaisons <Enter>/<Leave> déjà posées sur
    # le widget — beaucoup portent déjà un survol qui change leur couleur.
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    # Positionnée sous le widget et non sous le curseur : l'infobulle ne doit
    # jamais recouvrir ce que le joueur vient de survoler.
    def _show(self, e):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 2
        self.tip = tk.Toplevel(self.widget)
        self.tip.overrideredirect(True)
        # Sans -topmost, l'infobulle passerait sous les fenêtres de l'app, qui
        # sont elles-mêmes toujours au premier plan.
        self.tip.attributes("-topmost", True)
        self.tip.attributes("-alpha", 0.85)  # effet verre de l'UI EVE
        self.tip.geometry(f"+{x}+{y}")
        lbl = tk.Label(self.tip, text=self.text, bg=BG_H, fg=T0,
                       font=tkfont.Font(family="Consolas", size=8),
                       bd=1, relief="solid", highlightbackground=BDG,
                       padx=4, pady=1)
        lbl.pack()

    # Détruite plutôt que masquée : une infobulle est éphémère, et garder un
    # Toplevel par widget survolé accumulerait des fenêtres pour rien.
    def _hide(self, e):
        if self.tip:
            self.tip.destroy()
            self.tip = None


# Variante dont le texte est calculé AU SURVOL. Nécessaire pour tout ce qui
# dépend de l'état courant — détail d'un calcul d'ISK, contenu d'une session —
# qu'une chaîne figée à la construction afficherait périmé.
class DynamicTooltip:
    def __init__(self, widget, text_fn):
        self.widget = widget
        self.text_fn = text_fn
        self.tip = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    # text_fn() est appelée ici, pas à la construction : c'est tout l'intérêt.
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

    # Détruite plutôt que masquée : une infobulle est éphémère, et garder un
    # Toplevel par widget survolé accumulerait des fenêtres pour rien.
    def _hide(self, e):
        if self.tip:
            self.tip.destroy()
            self.tip = None

# Résout le chemin d'une ressource (compatible PyInstaller)
def _get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # D'abord à côté de l'exécutable ou du script, puis le dossier courant :
    # sous PyInstaller la ressource est extraite près du binaire, alors qu'en
    # développement elle vit à côté du .py.
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
        self.mission_name = None        # Toujours None : EVE n'ecrit le nom de la
                                        # mission dans aucun log (ni gamelog ni
                                        # chatlog) — conserve pour l'historique.
        self.mission_obj_met = False    # Drapeau « objectif accompli »
        self.missions_done = 0          # Missions terminées cette session
        self.alerts = deque(maxlen=MAX_ALERTS)  # [(timestamp_str, type, text), ...]

        # Suivi des anomalies
        self.anom_current = None         # dict de l'anomalie active (ou None)
        self.anom_completed = []         # liste des anomalies terminées
        # Totaux cumulés : _anom_stats() tourne à chaque tick (250 ms) et
        # faisait 3 passes O(n) sur anom_completed, qui grandit toute la session.
        self.anom_total_time = 0.0
        self.anom_total_isk  = 0
        self.anom_best_isk   = 0
        self.anom_last_combat = None     # datetime du dernier événement de combat (UTC)

        # Deque borné + somme courante : le DPS est recalculé quatre fois par
        # seconde et par personnage, donc re-sommer la fenêtre à chaque appel
        # coûterait cher. La somme est maintenue à l'ajout et au retrait, ce qui
        # rend dps() O(1) au lieu de O(n).
        # maxlen borne aussi la mémoire : un combat très long ne fait pas enfler
        # la liste indéfiniment.
        self.ed = deque(maxlen=1000)     # (horodatage, dégâts) sortants
        self.er = deque(maxlen=1000)     # (horodatage, dégâts) entrants
        self.ed_sum = 0
        self.er_sum = 0

        # Historique pour le graphique, échantillonné à chaque tick.
        # La taille est calculée pour couvrir exactement DPS_GRAPH_W secondes à
        # la cadence de rafraîchissement : le deque se purge donc tout seul.
        # Chaque entrée : (horodatage monotone, dps_out, dps_in)
        self.dps_hist = deque(maxlen=int(DPS_GRAPH_W * 1000 / DEF_POLL) + 1)

    # Durée de session = temps déjà accumulé + segment en cours. Ce découpage
    # existe pour la pause : on ferme le segment courant dans acc_sec et on met
    # t0 à None, ce qui gèle le compteur sans perdre l'historique.
    def secs(self):
        base = self.acc_sec
        if self.t0:
            base += (datetime.now(timezone.utc) - self.t0).total_seconds()
        return base

    # DPS sur la fenêtre glissante DPS_W.
    def dps(self, is_out=True):
        # Purge au fil de l'eau plutôt que balayage complet : chaque entrée
        # n'est retirée qu'une fois, ce qui garde le coût amorti constant.
        # time.monotonic() et non l'horloge murale : une correction NTP ou un
        # décalage entre l'horloge du PC et celle du serveur EVE ferait expirer
        # des entrées à l'instant même où on les ajoute.
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
        # Division par la fenêtre entière, pas par le temps réellement couvert :
        # au début d'un combat le DPS monte donc progressivement, ce qui reflète
        # mieux la réalité qu'un chiffre énorme calculé sur une seule salve.
        return total / DPS_W if deq else 0

    # ts est ignoré au profit de time.monotonic() : l'horodatage du log vient de
    # l'horloge du client EVE, qui peut dériver de celle du PC. Mélanger les deux
    # sources fausserait la fenêtre glissante.
    def add_dmg_out(self, ts, dmg):
        # Deque plein : append() évince silencieusement ed[0]. Il faut retirer sa
        # contribution AVANT, sinon ed_sum cesserait d'égaler la somme réelle du
        # deque et le DPS dériverait lentement à la hausse.
        if len(self.ed) == self.ed.maxlen:
            self.ed_sum -= self.ed[0][1]
        self.ed.append((time.monotonic(), dmg))
        self.ed_sum += dmg
        self.dd += dmg
        self.hd += 1

    # Symétrique de add_dmg_out ; on ne compte pas les « coups » entrants, seul
    # le total de dégâts subis intéresse le joueur.
    def add_dmg_in(self, ts, dmg):
        if len(self.er) == self.er.maxlen:
            self.er_sum -= self.er[0][1]
        self.er.append((time.monotonic(), dmg))
        self.er_sum += dmg
        self.dr += dmg

    # Les totaux sont cumulés ICI, à la clôture d'un site, parce que la lecture
    # est bien plus fréquente que l'écriture : les statistiques d'anomalies sont
    # relues à chaque tick, alors qu'un site ne se termine que toutes les
    # quelques minutes. _anom_stats() reste ainsi en O(1).
    def archive_anom(self, site):
        self.anom_completed.append(site)
        if site.get("end") and site.get("start"):
            self.anom_total_time += max(0, (site["end"] - site["start"]).total_seconds())
        isk = site.get("isk", 0)
        self.anom_total_isk += isk
        if isk > self.anom_best_isk:
            self.anom_best_isk = isk

    # ISK/heure net. Le seuil d'une minute évite le chiffre absurde des premiers
    # instants : une seule bounty à trois secondes de session extrapolerait à des
    # milliards par heure et n'apprendrait rien.
    def isk(self):
        s = self.secs()
        return ((self.bg * (1 - self.tax) + self.loot_val) / s * 3600) if s >= 60 else 0


# ── Fenêtre d'historique ─────────────────────────────────────────────
# L'historique répond à la seule question que le joueur se pose entre deux
# sessions : est-ce que ce vaisseau, ce site ou cette heure de jeu rapportent
# plus que les précédents ? D'où l'affichage en tableau comparatif plutôt qu'en
# résumé de la dernière session.
class HistoryWindow:
    # Table de description des colonnes : (en-tête, clé JSON, largeur, couleur).
    # Déclaratif pour que l'en-tête, la largeur et le rendu ne puissent pas se
    # désynchroniser quand on ajoute une métrique.
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

    # char_name=None affiche la flotte entière ; renseigné, il filtre sur un
    # pilote — c'est la vue utile quand on compare deux personnages.
    def __init__(self, parent, app, char_name=None):
        self.app = app
        self.char_name = char_name
        self.w = tk.Toplevel(parent)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        # Reprend l'opacité courante de l'app : une popup opaque au-dessus de
        # fenêtres translucides jurerait visuellement.
        self.w.attributes("-alpha", app.alpha)

        # Position mémorisée : la fenêtre d'historique se consulte souvent au
        # même endroit de l'écran, et la replacer à chaque ouverture serait
        # pénible. À défaut, on la décale de l'appelante pour ne pas la masquer.
        saved = app.cfg.get("history_pos")
        if saved:
            self.w.geometry(f"580x400{saved}")
        else:
            self.w.geometry(f"580x400+{parent.winfo_x() + 30}+{parent.winfo_y() + 40}")

        # Toutes les fenêtres sont en overrideredirect (aucune décoration
        # système), donc il faut réimplémenter le déplacement à la main : on
        # mémorise l'offset du clic, puis on repositionne pendant le glissé.
        # pack_propagate(False) fige la hauteur de la barre, sinon elle se
        # réduirait à la taille de son contenu.
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

        # Cumuls sur TOUT l'historique filtré, pas seulement sur les 100 lignes
        # affichées plus bas : le joueur veut son total à vie, pas un sous-total.
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

        # Sans ça, le cadre interne garde la largeur de son contenu et les
        # colonnes se tassent à gauche au lieu d'occuper la fenêtre.
        def _on_canvas_resize(e):
            canvas.itemconfig(self._canvas_win, width=e.width)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # La molette est captée globalement (bind_all), donc l'événement peut
        # encore arriver après la fermeture de la fenêtre : sans ce garde-fou,
        # Tk lèverait sur un widget détruit.
        def _safe_scroll(e):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1*(e.delta/120)), "units")
            except Exception:
                _log_exc("HistoryWindow.__init__._safe_scroll:930")
        
        # La capture globale de la molette est limitée au survol de la liste
        # (même principe que FleetManager) : sinon, ouvrir l'historique volerait
        # le défilement à toutes les autres fenêtres de l'app.
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _safe_scroll))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._canvas = canvas  # conservé pour pouvoir délier la molette à la fermeture

        F8  = tkfont.Font(family="Consolas", size=8)
        F9  = tkfont.Font(family="Consolas", size=9)
        F9B = tkfont.Font(family="Consolas", size=9, weight="bold")

        # Une seule grille pour l'en-tête ET les données : deux grilles séparées
        # dérivaient d'un ou deux pixels et les colonnes ne s'alignaient plus.
        # minsize garantit la lisibilité, weight répartit l'espace restant.
        COL_PX     = [112, 78, 48, 64, 64, 40, 40, 30]
        COL_WEIGHT = [  3,  2,  1,  2,  2,  1,  1,  1]
        for i, (px, wt) in enumerate(zip(COL_PX, COL_WEIGHT)):
            self._sf.grid_columnconfigure(i, minsize=px, weight=wt)

        grid_row = 0
        for i, (txt, key, wc, _) in enumerate(self.COLS):
            tk.Label(self._sf, text=txt, font=F8, bg=BG_H, fg=T1,
                     anchor="w", padx=3).grid(row=grid_row, column=i, sticky="ew")
        grid_row += 1

        # Les 100 plus récentes, en ordre antichronologique : au-delà, le rendu
        # de milliers de widgets Tk fige l'ouverture de la fenêtre, et les vieux
        # totaux restent de toute façon dans le bandeau de cumuls ci-dessus.
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
            _log_exc("HistoryWindow._save_geo:997")

    # Effacement ciblé : ouvert sur un personnage, on ne purge que SES sessions
    # et on laisse celles des autres pilotes intactes. Sans ce filtre, vider
    # l'historique d'un alt détruirait celui de tout le compte.
    def _clear_history(self):
        if self.char_name:
            hist = load_history()
            hist = [e for e in hist if e.get("character", "").lower() != self.char_name.lower()]
            save_history(hist)
        else:
            save_history([])
        self._close()

    def _close(self):
        self._save_geo()
        # La liaison molette était globale (bind_all) : sans ce détachement, elle
        # survivrait à la fenêtre et détournerait le défilement des autres.
        try:
            if hasattr(self, '_canvas') and self._canvas:
                self._canvas.unbind_all("<MouseWheel>")
        except Exception:
            _log_exc("HistoryWindow._close:1017")
        self.w.destroy()


# NOTE — la fenêtre de réglages « par personnage » qui vivait ici a été retirée.
# Elle était inatteignable : son unique point d'entrée était
# CharacterWindow._settings(), que personne n'appelait jamais (le bouton
# engrenage de la vue d'ensemble appartient à MainUI et ouvre MainUISettings).
# Elle écrivait de toute façon des clés de configuration PARTAGÉES, donc elle
# n'avait jamais rien de spécifique à un personnage. Ses deux champs uniques,
# UPDATE INTERVAL et SITE GAP, n'existaient nulle part ailleurs dans l'interface
# et se trouvent désormais dans MainUISettings.

# ── Panneau détaché ──────────────────────────────────────────────────
# Enveloppe générique de détachement. Le joueur n'a pas la place d'afficher tout
# le tableau de bord par-dessus EVE : il sort une seule section — l'ISK, les
# alertes — et la pose où il veut, souvent sur un second écran.
# La classe ne connaît AUCUNE section en particulier : elle reçoit build_fn et
# rappelle la même fonction de construction que la fenêtre principale, ce qui
# garantit qu'un panneau détaché reste identique à sa version intégrée.
class DetachedWindow:
    def __init__(self, parent, app, title, accent, section_key, build_fn, char_name: str = ""):
        self.app = app
        self.section_key = section_key
        self.w = tk.Toplevel(parent)
        self.w.overrideredirect(True)
        self.w.configure(bg=BG, highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self.w.attributes("-topmost", True)
        self.w.attributes("-alpha", app.alpha)

        # Position et taille sont mémorisées PAR SECTION ET PAR PERSONNAGE :
        # une disposition d'écran se construit une fois et doit se retrouver
        # telle quelle au lancement suivant.
        pos_key = f"{section_key}_detach_pos"
        saved = app.char_cfg.get(pos_key)
        if saved:
            self.w.geometry(saved)
        else:
            self.w.geometry(f"+{parent.winfo_x() + 30}+{parent.winfo_y() + 60}")

        self._dx = self._dy = 0
        self._resizing = False
        self._rw = self._rh = 0

        # En-tête : poignée de déplacement, et le X réintègre la section dans la
        # fenêtre principale au lieu de la détruire — fermer ne doit pas faire
        # disparaître la section du tableau de bord.
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

        # Barre du bas empaquetée AVANT le corps : sans ça, un contenu qui
        # grandit lui prend toute la place et la poignée devient inatteignable.
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

        # build_fn est la fonction de construction de la section, appelée avec
        # detached=True : c'est elle qui décide des quelques différences de mise
        # en page entre version intégrée et version flottante.
        self.body = tk.Frame(self.w, bg=BG)
        self.body.pack(fill="both", expand=True, padx=3, pady=3)
        build_fn(self.body, detached=True)

        # update_idletasks force Tk à calculer la mise en page maintenant :
        # sans ça, winfo_reqwidth() renverrait 1 et la fenêtre s'ouvrirait
        # minuscule avant de sauter à sa vraie taille.
        self.w.update_idletasks()
        
        # Taille déduite du contenu plutôt que de minimums codés en dur : un
        # minimum figé bloquait la mise en page des sections plus étroites.
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
        # Plancher de 60 px : en dessous, l'en-tête de déplacement et le bouton
        # de fermeture deviennent trop petits pour être cliqués, et la fenêtre
        # ne peut plus être ni bougée ni refermée.
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
            _log_exc("DetachedWindow._save_geometry:1158")

    # La géométrie est enregistrée AVANT la destruction : après destroy(), les
    # winfo_* ne renvoient plus rien d'exploitable et la position serait perdue.
    def _reattach(self):
        self._save_geometry()
        self.w.destroy()
        self.app._reattach(self.section_key)


# ── Overlay DPS autonome ─────────────────────────────────────────────
# Overlay DPS autonome, pensé pour être posé PAR-DESSUS le jeu et oublié : il
# imite le cadre « messages » d'EVE, sans fenêtre visible, pour que le joueur
# garde ses chiffres sous les yeux sans quitter le combat du regard.
# Il est délibérément indépendant du tableau de bord : on veut pouvoir masquer
# tout le reste et ne garder que ces deux nombres à l'écran.
# Deux modes : DÉPLACEMENT (cadre visible, on le pose) et POSÉ (transparent et
# traversant à la souris, les clics vont au jeu).
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
        # Opacité pleine, indépendante du réglage global : le reste de l'app
        # peut être translucide, mais des chiffres à demi transparents sur un
        # fond spatial deviennent illisibles.
        self.w.attributes("-alpha", 1.0)
        try:
            # Cœur de l'effet : Windows rend invisible tout pixel exactement de
            # cette teinte, donc seuls le texte et les courbes subsistent
            # au-dessus d'EVE. Ailleurs qu'Windows l'attribut n'existe pas et
            # l'overlay reste un rectangle opaque — dégradé acceptable.
            self.w.attributes("-transparentcolor", OVERLAY_KEY)
        except Exception:
            _log_exc("DPSOverlay.__init__:1200")

        saved_pos = self.char_cfg.get("dps_overlay_pos")
        saved_geo = self.char_cfg.get("dps_overlay_geo")
        if saved_geo and saved_pos:
            self.w.geometry(f"{saved_geo}{saved_pos}")
        elif saved_pos:
            self.w.geometry(f"230x96{saved_pos}")
        else:
            self.w.geometry(f"230x96+{main_ui.root.winfo_x()+60}+{main_ui.root.winfo_y()+60}")

        # Objets Font RÉUTILISÉS : la mise à l'échelle se contente de changer
        # leur taille, ce qui repeint les labels sans les reconstruire — créer
        # une police par redimensionnement ferait clignoter l'overlay.
        self._num_font   = tkfont.Font(family="Consolas", size=22, weight="bold")
        self._title_font = tkfont.Font(family="Consolas", size=8,  weight="bold")

        self._build_chrome()
        self._build_view()
        self.w.after(120, self._finalize_scale)
        self._refresh()

        # Un overlay tout neuf s'ouvre en mode DÉPLACEMENT : posé d'emblée, il
        # serait transparent ET traversant, donc invisible et impossible à
        # attraper. Un overlay restauré revient à l'état où il était.
        if saved_pos:
            self.locked = bool(self.char_cfg.get("dps_overlay_locked", True))
        else:
            self.locked = False
        self.w.update_idletasks()
        self._apply_mode()

    # Pas de barre de titre : elle occuperait de la place et trahirait la
    # présence d'une fenêtre. Le contour, le ✕ et la poignée n'apparaissent
    # qu'en mode déplacement, et disparaissent une fois l'overlay posé.
    def _build_chrome(self):
        self.body = tk.Frame(self.w, bg=OVERLAY_KEY)

        # Le ✕ ne ferme pas : il POSE l'overlay (sort du mode déplacement).
        # Fermer se fait depuis la vue d'ensemble, là où on l'a ouvert.
        self._xbtn = tk.Label(self.w, text="✕",
                              font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                              bg=OVERLAY_MOVE_BG, fg="#ffffff", cursor="hand2")
        self._xbtn.bind("<Button-1>", lambda e: self.toggle_lock(force=True))

        # Poignée de redimensionnement, visible seulement en déplacement.
        self._grip = tk.Label(self.w, text="⤡",
                              font=tkfont.Font(family="Consolas", size=9),
                              bg=OVERLAY_MOVE_BG, fg="#ffffff", cursor="bottom_right_corner")
        self._grip.bind("<Button-1>", self._resize_start)
        self._grip.bind("<B1-Motion>", self._resize_drag)
        self._grip.bind("<ButtonRelease-1>", self._resize_end)

        # On attrape l'overlay par son corps entier plutôt que par une zone
        # dédiée : en mode chiffres seuls, il n'y a presque rien d'autre à
        # viser. _drag ignore l'événement quand l'overlay est posé.
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
        # Les widgets qui viennent d'être créés doivent adopter le fond du mode
        # courant : sinon un cadre resté opaque dessinerait un rectangle visible
        # par-dessus le jeu.
        self._set_body_bg(OVERLAY_MOVE_BG if not self.locked else OVERLAY_KEY)

    def _build_numbers(self, parent, inline=False):
        # Conteneur des chiffres, retenu pour _apply_scale : c'est la SEULE
        # partie qui peut être rognée. Le graphique, lui, est un Canvas en
        # expand=True qui se laisse comprimer sans rien perdre (il se redessine
        # à la taille réellement allouée), donc le mesurer fausserait le calcul.
        self._num_box = parent

        def _bind_drag(*widgets):
            for _w in widgets:
                _w.bind("<Button-1>", self._drag_start)
                _w.bind("<B1-Motion>", self._drag)
                _w.bind("<ButtonRelease-1>", lambda e: self._save_geo())
        # Deux dispositions pour deux usages : CÔTE À CÔTE quand le graphique
        # occupe déjà la hauteur, EMPILÉ quand les chiffres sont seuls et
        # peuvent s'étaler. Les deux flèches ▸ ◂ pointent vers l'extérieur pour
        # suggérer le sens : ce qui sort, ce qui rentre.
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

    # Boucle propre à l'overlay, indépendante du tick du tableau de bord : il
    # doit continuer à afficher le DPS même quand la fenêtre du personnage est
    # masquée, puisque c'est justement son intérêt.
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
            _log_exc("DPSOverlay._refresh:1314")
        try:
            self._job = self.w.after(getattr(self.win, "poll_ms", DEF_POLL), self._refresh)
        except Exception:
            # Fenêtre détruite entre deux tours : on laisse la chaîne s'arrêter
            # plutôt que de replanifier sur un widget qui n'existe plus.
            self._job = None

    def _redraw_graph(self):
        try:
            # winfo_viewable() en plus de winfo_exists() : dessiner dans un
            # canvas non affiché coûte du temps pour rien, et l'overlay peut
            # être masqué alors que sa boucle tourne encore.
            if self._graph.winfo_exists() and self._graph.winfo_viewable():
                draw_dps_graph(self._graph, self.win.data.dps_hist, is_detached=True)
        except Exception:
            _log_exc("DPSOverlay._redraw_graph:1325")

    # ── Vues ──
    # Le cycle est le seul moyen de changer de vue : l'overlay n'a pas de menu
    # à lui, tout se pilote depuis la cellule DPS de la vue d'ensemble.
    def cycle_view(self):
        self.set_view((self.view + 1) % self._VIEW_COUNT)

    def set_view(self, i):
        # Modulo plutôt qu'une borne : cycle_view() peut dépasser le compte, et
        # une vue enregistrée par une version antérieure pourrait ne plus exister.
        self.view = i % self._VIEW_COUNT
        self.char_cfg["dps_overlay_view"] = self.view
        save_config(self.cfg)
        self._build_view()
        # La remise à zéro force _apply_scale à recalculer : la nouvelle vue
        # n'a ni le même nombre de rangées ni les mêmes besoins de hauteur.
        # Le léger différé laisse Tk disposer les widgets avant de les mesurer.
        self._last_scale_h = 0
        self.w.after(30, self._apply_scale)

    # ── Mise à l'échelle au redimensionnement ──
    # Le texte suit la taille de la fenêtre : l'overlay doit rester lisible
    # aussi bien en vignette dans un coin qu'agrandi sur un second écran.
    def _on_resize(self, event):
        # Garde de réentrance : changer la police provoque un <Configure>, qui
        # rappellerait cette fonction en boucle.
        if self._scaling:
            return
        h = event.height
        # Seuil de 8 px : sans lui, chaque pixel de glissé recalculerait les
        # polices et le redimensionnement deviendrait saccadé.
        if abs(h - self._last_scale_h) < 8:
            return
        self._last_scale_h = h
        self._apply_scale(h)

    # Passe finale après l'ouverture : à la construction, Tk n'a pas encore
    # attribué sa taille définitive à la fenêtre, donc le premier calcul se
    # ferait sur des dimensions provisoires.
    def _finalize_scale(self):
        try:
            if self.w.winfo_exists():
                self._last_scale_h = 0
                self._apply_scale()
        except Exception:
            _log_exc("DPSOverlay._finalize_scale:1355")

    def _apply_scale(self, h=None):
        if self._scaling:
            return
        self._scaling = True
        try:
            if h is None:
                h = self.body.winfo_height()
            if h < 8:
                return
            # La vue « chiffres seuls » EMPILE deux rangées (OUT au-dessus de
            # IN) alors que la vue combinée les met côte à côte sur une seule
            # rangée. Sa base doit donc être environ doublée, sinon la police
            # est calculée comme s'il n'y avait qu'une rangée : à 220x90 on
            # obtenait du 38 pt pour deux rangées dans 84 px, et Tk rognait le
            # chiffre IN jusqu'à le rendre illisible.
            base = 60 if self.view == self.VIEW_BOTH else 88
            scale = max(0.5, min(3.0, h / base))
            size = max(10, min(48, int(20 * scale)))
            self._num_font.configure(size=size)
            self._title_font.configure(size=max(7, min(12, int(8 * scale))))

            # Filet de sécurité : la base ci-dessus suppose une police et un DPI
            # donnés. On mesure ce que les chiffres RÉCLAMENT vraiment et on
            # réduit tant que ça dépasse, pour qu'aucun ne puisse être rogné,
            # quelle que soit la police ou la mise à l'échelle de l'écran.
            # On ne mesure QUE le bloc des chiffres : en vue combinée, le corps
            # contient aussi le Canvas du graphique, dont la hauteur DEMANDÉE
            # (plusieurs centaines de pixels) n'a rien à voir avec la place
            # qu'il occupe réellement — le prendre en compte rabotait la police
            # jusqu'au plancher à chaque redimensionnement.
            # En vue combinée on garde en plus de quoi afficher le graphique,
            # sinon les chiffres le réduiraient à rien.
            box = getattr(self, "_num_box", None)
            if box is not None:
                budget = int(h * 0.6) if self.view == self.VIEW_BOTH else h
                for _ in range(12):
                    box.update_idletasks()
                    if box.winfo_reqheight() <= budget or size <= 10:
                        break
                    size = max(10, size - 2)
                    self._num_font.configure(size=size)

            if self._graph is not None:
                self._redraw_graph()
        finally:
            self._scaling = False

    # ── Mode posé / mode déplacement ──
    def toggle_lock(self, force=None):
        """locked=True → POSÉ : texte nu, transparent, traversant à la souris.
        locked=False → DÉPLACEMENT : fond opaque, contour blanc, ✕ et poignée.

        Les deux états sont incompatibles par nature : posé, l'overlay ne reçoit
        plus aucun clic (ils vont au jeu), donc il faut un mode explicite pour
        pouvoir le rattraper et le déplacer.
        """
        self.locked = (not self.locked) if force is None else bool(force)
        self._apply_mode()
        self.char_cfg["dps_overlay_locked"] = self.locked
        save_config(self.cfg)
        try:
            self.mu._reflect_overlay_state(self.win.char_id)
        except Exception:
            _log_exc("DPSOverlay.toggle_lock:1386")

    def _set_body_bg(self, color):
        """Repeint le corps ET toute sa descendance.

        Il faut descendre l'arbre entier : la transparence par couleur-clé
        s'applique pixel par pixel, donc un seul cadre intérieur resté opaque
        dessinerait un rectangle visible au-dessus du jeu.
        Parcours itératif plutôt que récursif — la profondeur est faible, et
        cela évite d'empiler des appels dans un chemin déclenché à chaque
        changement de mode.
        """
        stack = [self.body]
        while stack:
            w = stack.pop()
            try:
                w.configure(bg=color)
            except Exception:
                _log_exc("DPSOverlay._set_body_bg:1397")
            stack.extend(w.winfo_children())

    def _apply_mode(self):
        """Applique l'habillage correspondant au mode courant."""
        move = not self.locked
        # En déplacement, le fond opaque rend TOUTE la surface attrapable ; une
        # fois posé, la couleur-clé la fait disparaître et il ne reste que le texte.
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
            _log_exc("DPSOverlay._apply_mode:1416")
        # Click-through : sans WS_EX_TRANSPARENT, l'overlay est invisible mais
        # intercepte quand même les clics, et le joueur ne pourrait plus cliquer
        # sur ce qui se trouve derrière — c'est-à-dire son propre vaisseau.
        # Uniquement en mode posé, sinon on ne pourrait plus l'attraper.
        # Windows seulement : ailleurs, l'overlay reste cliquable (dégradé).
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
                _log_exc("DPSOverlay._apply_mode:1432")

    # ── Déplacement, redimensionnement, géométrie ──
    # Les deux gardes `if self.locked` sont la deuxième ligne de défense après
    # le click-through : sous un système sans WS_EX_TRANSPARENT, elles évitent
    # qu'un overlay posé se déplace au moindre clic.
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
        # Planchers de 120x60 : en dessous, le ✕ et la poignée se chevauchent et
        # l'overlay ne peut plus être ni posé ni redimensionné.
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
            _log_exc("DPSOverlay._save_geo:1464")

    def apply_alpha(self, a):
        # VOLONTAIREMENT sans effet. La transparence de l'overlay vient de la
        # couleur-clé, pas de l'alpha de la fenêtre : lui appliquer le curseur
        # d'opacité globale ferait pâlir les chiffres eux-mêmes, alors que le
        # réglage ne vise que le fond des autres fenêtres.
        return

    # La géométrie est enregistrée AVANT destroy() : après, les winfo_* ne
    # renvoient plus rien et l'overlay rouvrirait à sa position par défaut.
    def close(self):
        if self._job:
            try: self.w.after_cancel(self._job)
            except Exception: _log_exc("DPSOverlay.close:1475")
            self._job = None
        self._save_geo()
        self.char_cfg["dps_overlay_open"] = False
        save_config(self.cfg)
        try:
            self.w.destroy()
        except Exception:
            _log_exc("DPSOverlay.close:1482")
        try:
            self.mu._on_overlay_closed(self.win.char_id)
        except Exception:
            _log_exc("DPSOverlay.close:1486")


# ── Tableau de bord d'un personnage ──────────────────────────────────
# Une fenêtre par pilote. C'est la classe centrale : elle possède le lecteur de
# log, l'état de session, l'interface et les deux boucles temporelles.
# Le découpage par personnage vient du jeu lui-même — EVE écrit un gamelog
# distinct par pilote, et le multi-comptes est la norme en PvE. Chaque fenêtre
# est donc autonome : sa session, ses totaux et ses réglages ne regardent
# qu'elle, et fermer l'une n'affecte pas les autres.
class CharacterWindow:

    def __init__(self, root_tk, main_ui, char_id: str, char_name: str, log_file: str, cfg: dict):
        top = tk.Toplevel(root_tk)
        # Masquée jusqu'à ce que MainUI décide de l'afficher : sans ça, la
        # fenêtre apparaît brièvement à sa position par défaut avant d'être
        # replacée, ce qui produit un sursaut visible au démarrage.
        top.withdraw()
        # overrideredirect : aucune décoration système. L'app doit ressembler à
        # une extension de l'UI d'EVE, pas à une application Windows posée
        # par-dessus — d'où les barres de titre et poignées réimplémentées.
        top.overrideredirect(True)
        top.configure(bg=BG)
        top.attributes("-topmost", True)
        self.root = top

        self.char_id   = char_id
        self.char_name = char_name
        self._main_ui  = main_ui
        self.cfg       = cfg
        # Sous-dictionnaire propre à ce pilote, créé au besoin. Tout ce qui est
        # personnel (géométrie, sections repliées, thème, overlay) y va ; le
        # reste de cfg est partagé par toute la flotte.
        self.char_cfg  = cfg.setdefault("chars", {}).setdefault(char_id, {})
        self.log_path  = cfg.get("log_path", DEF_PATH)
        self.poll_ms  = self.cfg.get("poll_ms",  DEF_POLL)
        self.alpha    = self.cfg.get("alpha",    DEF_ALPHA)
        self.anom_gap = self.cfg.get("anom_gap", ANOM_GAP)
        self.root.attributes("-alpha", self.alpha)

        self.data   = Data()
        self._dx = self._dy = 0
        self._st  = "stopped"
        self._main_hidden = False
        self._is_collapsed = False  # replié sur sa barre de titre (double-clic)
        self._full_height = 0       # hauteur mémorisée avant repli
        self._main_frame = None     # corps de la fenêtre, masqué au repli
        # Un glissé commence par un clic : sans ce drapeau, déplacer la fenêtre
        # déclencherait aussi le double-clic de repli.
        self._dragging = False
        # Un overlay ouvert garde le personnage en analyse même si sa fenêtre
        # est masquée — sinon l'overlay afficherait un DPS figé.
        self._overlay_active = False
        self.cf = log_file if log_file else None
        self.fh = None
        self.fp = 0
        # Report de ligne partielle et dernière taille observée. EVE vide son tampon
        # en milieu de ligne : une lecture se termine donc souvent sur une demi-ligne,
        # et la traiter comme complète (en avançant au-delà) perdait ou déformait
        # l'événement. Voir _read().
        self._read_buf     = ""
        self._read_size    = -1
        self._read_seen_fp = None
        self._last_gamelog_scan = 0.0   # monotonic ts of last gamelog-rotation scan
        self._hw = None
        self._calc_dots = 0
        # Identifiants after() des deux boucles, conservés pour pouvoir les
        # annuler à la fermeture — sinon elles se déclencheraient sur des
        # widgets détruits.
        self._poll_job = None        # boucle de lecture des logs
        self._tick_job = None        # boucle de rafraîchissement de l'UI
        # Polices d'alerte réutilisées par taille : le feed se redessine souvent,
        # et créer un objet Font par ligne à chaque passage coûte cher.
        self._alert_font_cache = {}

        # État du suivi presse-papiers et des prix
        self._last_clipboard  = ""
        self._global_prices   = {}
        # Cache Jita valable pour la session : un même objet revient souvent
        # dans plusieurs cargaisons, et chaque appel coûte une requête réseau.
        self._jita_price_cache = {}
        self._name_to_id_cache = self._load_nameid_cache()

        # État de l'indicateur d'estimation du loot
        self._loot_loading    = False
        # Une seule estimation à la fois par fenêtre : deux threads concurrents
        # entrelaceraient l'animation du spinner et pourraient additionner deux
        # fois la même cargaison.
        self._loot_inflight   = False
        self._loot_anim_job   = None
        self._loot_anim_step  = 0

        # Pile des imports de butin de la session : (montant, horodatage), le
        # dernier en fin de liste. Sert au bouton UNDO — sans elle, une cargaison
        # mal comptée restait coincée dans le total, l'ISK/heure et la ligne
        # d'historique sauvegardée, sans aucun moyen de la retirer.
        # Vidée par _reset(), donc RESET, NEXT SITE et toute nouvelle session
        # repartent d'une pile propre.
        self._loot_stack      = []
        self._loot_undo_btn   = None   # bouton UNDO du breakdown
        self._loot_hdr_lbl    = None   # en-tête « LOOT ESTIMATE », vire au rouge si verrouillé
        self._clip_btn        = None   # bouton CLIP de la barre de contrôle

        # Ajustement de largeur du breakdown (voir _brk_fit_row). Les cadres de
        # rangée et leurs en-têtes sont mémorisés pour pouvoir MESURER la place
        # réellement disponible à chaque tick, plutôt que de supposer 290 px.
        self._brk_r1          = None   # rangée BOUNTIES / EST. TAXES / KILLS
        self._brk_r3          = None   # rangée LOOT ESTIMATE / TOTAL NET
        self._brk_r1_hdrs     = []
        self._brk_r3_hdrs     = []
        self._brk_hdr_font    = None
        self._brk_val_font    = None
        # Montants exacts du dernier rafraîchissement, servis par les infobulles
        # quand la rangée a dû basculer sur la notation courte.
        self._brk_exact: dict = {}

        # Chargement des prix en tâche de fond : le catalogue ESI pèse plusieurs
        # mégaoctets et bloquerait l'ouverture de la fenêtre. En daemon pour ne
        # pas retarder la fermeture de l'app.
        threading.Thread(target=self._download_market_data, daemon=True).start()

        self._storyline_ctr = self.char_cfg.get("storyline_counter", 0)
        self.tax_var = tk.StringVar(value=self.cfg.get("tax", str(DEF_TAX)))

        self._frozen = None
        self._last_tick_wall: float = time.monotonic()
        self._session_saved = False
        self._anom_paused_secs = 0
        # Horloge MONOTONE et non horodatage de log pour la détection de fin de
        # site : une correction d'heure système clôturerait des anomalies au
        # hasard, ou empêcherait de les clôturer du tout.
        self._anom_last_wall   = 0.0  # dernier événement de combat
        self._anom_start_wall  = 0.0  # début de l'anomalie en cours
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

        # Sections activées, par personnage. Le repli sur l'ancienne valeur
        # globale sert la migration : les configs écrites avant le passage au
        # par-personnage continuent de fonctionner sans rien perdre.
        self._isk_enabled  = self.char_cfg.get("isk_enabled",  self.cfg.get("isk_enabled",  True))
        self._msn_enabled  = self.char_cfg.get("msn_enabled",  self.cfg.get("msn_enabled",  True))
        self._anom_enabled = self.char_cfg.get("anom_enabled", self.cfg.get("anom_enabled", False))

        # Missions et anomalies s'excluent : les deux décrivent « ce que le
        # joueur est en train de faire » et se disputeraient la même place.
        # En cas de conflit dans une vieille config, la mission gagne.
        if self._msn_enabled and self._anom_enabled:
            self._anom_enabled = False
            self.char_cfg["anom_enabled"] = False

        # Sections repliées (même logique de migration que ci-dessus)
        self._isk_collapsed   = self.char_cfg.get("isk_collapsed",   self.cfg.get("isk_collapsed",   False))
        self._msn_collapsed   = self.char_cfg.get("msn_collapsed",   self.cfg.get("msn_collapsed",   False))
        self._anom_collapsed  = self.char_cfg.get("anom_collapsed",  self.cfg.get("anom_collapsed",  False))
        self._alert_collapsed = self.char_cfg.get("alert_collapsed", self.cfg.get("alert_collapsed", False))
        self._brk_collapsed   = self.char_cfg.get("brk_collapsed",   self.cfg.get("brk_collapsed",   False))

        self._current_theme = self.char_cfg.get("theme", THEME_DEFAULT)
        apply_theme_colors(self._current_theme)

        # Cache des dernières valeurs affichées, pour n'écrire dans un widget
        # que lorsque son contenu change réellement (voir _cset).
        self._last_values = {}

        self._style()
        self._build()

        # update_idletasks avant de lire ou poser la géométrie : sans ça, Tk
        # n'a pas encore calculé la taille demandée par le contenu.
        self.root.update_idletasks()
        # Restauration taille ET position : le joueur compose une disposition
        # d'écran une fois et doit la retrouver telle quelle.
        saved_geom = self.char_cfg.get("geometry", "")
        if saved_geom and "+" in saved_geom:
            self.root.geometry(saved_geom)
        else:
            self._center()

        self.root.config(highlightbackground=BDG, highlightcolor=BDG, highlightthickness=1)
        self._fit()

        # Restauration de l'état replié. La hauteur pleine est relue depuis la
        # config plutôt que mesurée : la fenêtre est encore masquée à ce stade,
        # et les winfo_* ne renvoient rien d'exploitable tant qu'elle l'est.
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

    # ── Cache disque nom → type_id ─────────────────────────────────────
    # Résoudre un nom d'objet en type_id coûte un appel ESI. Le cache rend ces
    # identifiants permanents : ils ne changent jamais, donc une fois connus il
    # n'y a plus jamais de raison de les redemander, même entre deux lancements.
    def _load_nameid_cache(self):
        if os.path.exists(NAMEID_CACHE):
            try:
                with open(NAMEID_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                _log_exc("CharacterWindow._load_nameid_cache:1652")
        return {}

    # Sauvegarde le cache nom→type_id sur le disque
    def _save_nameid_cache(self):
        # Plusieurs threads de loot, et plusieurs fenêtres de personnage, se
        # partagent ce fichier unique. On fusionne sous verrou pour qu'un
        # rédacteur n'efface pas les identifiants qu'un autre vient de résoudre,
        # puis on écrit atomiquement : un lecteur ne doit jamais tomber sur un
        # fichier à moitié écrit.
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
                _log_exc("CharacterWindow._save_nameid_cache:1676")

    # ── Prix du marché (cache 24 h) ────────────────────────────────────
    # Catalogue de prix moyens de tout EVE, rafraîchi au plus une fois par jour :
    # les prix bougent lentement à cette échelle, et le fichier pèse assez lourd
    # pour qu'un téléchargement à chaque lancement soit pénible.
    def _download_market_data(self):
        # Sérialisé entre TOUTES les fenêtres : un seul thread interroge l'ESI
        # et écrit le cache partagé, les autres attendent puis relisent ce
        # qu'il a écrit. Sans ça, cinq personnages déclenchaient cinq
        # téléchargements du même catalogue et cinq écritures concurrentes, qui
        # laissaient ratting_prices.json corrompu.
        with _PRICE_LOCK:
            # Cache disque réutilisé s'il a moins de 24 h : les prix moyens
            # bougent lentement, et le fichier est trop gros pour être
            # retéléchargé à chaque lancement.
            if os.path.exists(PRICE_CACHE):
                try:
                    age_hrs = (time.time() - os.path.getmtime(PRICE_CACHE)) / 3600
                    if age_hrs < 24:
                        with open(PRICE_CACHE, "r", encoding="utf-8") as f:
                            self._global_prices = json.load(f)
                        return
                except Exception:
                    _log_exc("CharacterWindow._download_market_data:1695")

            # Cache absent ou périmé : on redemande le catalogue complet.
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

                # Écriture atomique (fichier temporaire puis os.replace) : ni
                # un autre personnage au même instant, ni le prochain
                # lancement, ne doit lire un cache tronqué.
                tmp = PRICE_CACHE + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._global_prices, f)
                os.replace(tmp, PRICE_CACHE)
            except Exception:
                _log_exc("CharacterWindow._download_market_data:1716")

    # ── Estimation du loot par presse-papiers ──────────────────────────
    # EVE n'écrit RIEN sur le loot dans ses logs : la seule façon d'en connaître
    # la valeur est que le joueur copie sa cargaison (Ctrl+A, Ctrl+C), ce que
    # l'app détecte en surveillant le presse-papiers. D'où ce chemin détourné.
    # Prend en charge un collage transmis par MainUI (qui lit le presse-papiers
    # une seule fois pour toute la flotte — voir MainUI._poll_clipboard).
    # Retourne True si cette fenêtre a bien démarré une estimation de loot.
    def _accept_clipboard(self, content):
        if self._st not in ("running", "paused"):
            return False
        # Une seule estimation à la fois par fenêtre : si une autre tourne, on
        # refuse, l'appelant laisse _last_clipboard tel quel et le collage sera
        # repris à un tour suivant. Évite deux threads concurrents sur la même
        # cargaison et un spinner dont l'état s'entrelace.
        if self._loot_inflight:
            return False
        try:
            if not self.root.winfo_exists():
                return False
            self._loot_inflight = True
            self._loot_anim_start()
            threading.Thread(target=self._process_loot_copy,
                             args=(content,), daemon=True).start()
            return True
        except Exception:
            self._loot_inflight = False
            return False

    # Chemin de repli : lecture directe du presse-papiers quand la fenêtre tourne
    # sans MainUI (cas qui n'arrive pas dans l'app actuelle, mais _main_ui est
    # déclaré optionnel — on garde donc l'ancien comportement autonome).
    def _check_clipboard(self):
        # Même verrou que dans MainUI._poll_clipboard : ce chemin de repli lit
        # le presse-papiers pour son propre compte, il doit donc le respecter
        # aussi, sinon le verrou ne tiendrait pas sans MainUI.
        if not _CLIP_OK or _CLIP_LOCK or self._st not in ("running", "paused"): return
        try:
            content = pyperclip.paste()
            if not content or "\t" not in content:
                return
            if content == self._last_clipboard:
                return
            if self._accept_clipboard(content):
                self._last_clipboard = content
        except Exception:
            _log_exc("CharacterWindow._check_clipboard:1757")

    # Le verrou est GLOBAL : on délègue à la MainUI, qui possède l'état partagé
    # et rafraîchit tous les boutons d'un coup. Sans MainUI (fenêtre autonome),
    # on bascule le drapeau nous-mêmes, avec le même instantané de presse-papiers
    # au déverrouillage — sinon le texte encore présent serait avalé au tour
    # suivant et le verrou n'aurait servi à rien.
    def _toggle_clip_lock(self):
        global _CLIP_LOCK
        mu = getattr(self, "_main_ui", None)
        if mu is not None:
            try:
                mu._set_clip_lock(not _CLIP_LOCK)
                return
            except Exception:
                _log_exc("CharacterWindow._toggle_clip_lock:2210")
        target = not _CLIP_LOCK
        if not target and _CLIP_OK:
            try:
                self._last_clipboard = pyperclip.paste() or ""
            except Exception:
                _log_exc("CharacterWindow._toggle_clip_lock:2217")
        _CLIP_LOCK = target
        self._refresh_clip_btn()

    def _refresh_clip_btn(self):
        """Aligne le bouton CLIP sur l'état du verrou.

        Le glyphe barré s'AJOUTE à la couleur : une nuance de rouge se rate d'un
        coup d'oeil, et le prix d'un verrou oublié est une soirée de butin non
        comptée. L'en-tête du breakdown porte le même avertissement.
        """
        if not self._clip_btn:
            return
        try:
            if _CLIP_LOCK:
                self._clip_btn.config(text="CLIP ⊘", fg=CS)
            else:
                self._clip_btn.config(text="CLIP", fg=CA)
        except Exception:
            _log_exc("CharacterWindow._refresh_clip_btn:2233")

    # Tourne sur un thread de travail : la résolution des noms et les appels de
    # prix peuvent prendre plusieurs secondes, ce qui figerait l'interface.
    def _process_loot_copy(self, text):
        # Tourne sur un thread démon. TOUT ce qui suit doit rester sous garde :
        # une exception qui s'échappait tuait le thread en silence, laissait
        # _loot_inflight bloqué à True, et la fenêtre ignorait alors tous les
        # collages suivants — spinner tournant indéfiniment — jusqu'au
        # redémarrage de l'app.
        total = 0
        try:
            total = self._value_loot_text(text)
        except Exception:
            total = 0
        now_str = datetime.now().strftime("%H:%M:%S")
        try:
            if total > 0:
                self.root.after(0, lambda amt=total, ts=now_str: self._apply_loot(amt, ts))
            else:
                # Nothing valued — stop spinner without flashing green
                self.root.after(0, lambda: self._loot_anim_stop(False))
        except Exception:
            # Racine déjà détruite (fenêtre fermée pendant l'estimation) : plus
            # de thread principal pour exécuter _loot_anim_stop, on libère donc
            # le verrou directement.
            self._loot_inflight = False
            self._loot_loading  = False

    # Calcule la valeur totale d'un collage d'inventaire (thread de travail).
    def _value_loot_text(self, text):
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

        # Resolve newly copied Item Names to Type IDs in bulk via ESI.
        # resolve_failed distingue « la REQUÊTE a échoué » (réseau) de « l'ESI a
        # répondu que ce n'est pas un objet ». Les deux appellent un traitement
        # différent plus bas : sans cette distinction, un nom inconnu se
        # verrait attribuer un prix comme s'il s'agissait de butin.
        resolve_failed = False
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
                    resolve_failed = True
            self._save_nameid_cache()

        # Prix : Jita pour les objets de faction (ils valent assez cher pour
        # justifier une requête), moyenne globale déjà en cache pour le reste.
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
                # Objet EVE reconnu mais sans prix de marché — on estime
                # d'après son nom.
                if price == 0:
                    price = self._get_avg_loot_price_fallback(name)
            elif resolve_failed:
                # ESI injoignable : impossible de savoir si c'est un objet du
                # jeu. On suppose que oui et on estime, comme avant.
                price = self._get_avg_loot_price_fallback(name)
            # sinon : l'ESI a répondu et ne reconnaît pas ce nom — ce n'est pas
            # un objet d'inventaire, donc il ne vaut rien. N'importe quel texte
            # contenant une tabulation arrive jusqu'ici (une ligne de tableur,
            # un tableau copié d'une page web), et l'estimation de repli
            # renvoie 200 000 pour TOUT nom inconnu : les compter inventerait
            # de l'ISK dans le total de session.

            total_session_loot += (price * qty)

        return total_session_loot

    # Le son est le seul canal qui fonctionne quand le joueur regarde le jeu et
    # non la fenêtre : scram et web sont précisément les événements qu'il ne
    # faut pas rater. Joué dans un thread parce que winsound.Beep BLOQUE le
    # temps du bip — sur le thread UI, l'app se figerait à chaque alerte.
    def _ewar_sound(self):
        if not _SND_OK:
            return
        def _beep():
            try:
                winsound.Beep(1200, 130)
                winsound.Beep(1650, 160)
            except Exception:
                _log_exc("CharacterWindow._ewar_sound._beep:1866")
        try:
            threading.Thread(target=_beep, daemon=True).start()
        except Exception:
            _log_exc("CharacterWindow._ewar_sound:1870")

    # Complément visuel du bip, pour le joueur qui coupe le son ou joue en
    # musique. Le clignotement attire l'œil là où l'alerte vient de s'écrire.
    def _flash_alert(self):
        self._ewar_sound()

        # Quick pulse flash on the alert frame for EWAR
        def _pulse(step=0):
            if step < 3:

                # Alternance clair / normal : c'est le clignotement qui attire
                # l'œil, pas la couleur elle-même.
                bg = BDG if step % 2 == 0 else BG_P
                try:
                    self._alert_frame.config(bg=bg)
                    for w in self._alert_frame.winfo_children():
                        w.config(bg=bg)
                        for c in w.winfo_children():
                            c.config(bg=bg)
                except Exception:
                    _log_exc("CharacterWindow._flash_alert._pulse:1889")
                try:
                    self.root.after(150, lambda: _pulse(step + 1))
                except Exception:
                    _log_exc("CharacterWindow._flash_alert._pulse:1893")   # root torn down mid-flash — stop the pulse chain
            else:

                # Reset to normal
                try:
                    self._alert_frame.config(bg=BG_P)
                    for w in self._alert_frame.winfo_children():
                        w.config(bg=BG_P)
                        for c in w.winfo_children():
                            c.config(bg=BG_P)
                except Exception:
                    _log_exc("CharacterWindow._flash_alert._pulse:1904")
        _pulse()

    # Repasse sur le THREAD PRINCIPAL via after() : Tk n'est pas thread-safe, et
    # écrire dans les widgets depuis le thread de loot corromprait l'affichage.
    def _apply_loot(self, amount, now_str):

        # Arrêt du spinner et éclat vert : confirme visuellement que la
        # cargaison a bien été prise en compte.
        self._loot_anim_stop(True)

        # Main thread — safe to update data + UI
        self.data.loot_val += amount
        # Empilé AVANT l'alerte : _undo_last_loot retrouve la ligne du fil par son
        # horodatage, les deux doivent donc porter exactement le même.
        self._loot_stack.append((amount, now_str))
        self._add_loot_alert(now_str, amount)
        self._refresh_undo_btn()

    # Retire le dernier import de butin. Existe parce qu'un simple Ctrl+C sur
    # autre chose qu'une cargaison (un contrat, une ligne de marché, une
    # cargaison qu'on voulait seulement faire estimer ailleurs) injectait de
    # l'ISK définitivement coincé dans le total, l'ISK/heure et l'historique.
    def _undo_last_loot(self):
        # Refus pendant une estimation : le thread de travail est sur le point
        # d'ajouter un montant, défaire maintenant retirerait le mauvais.
        if self._loot_inflight or not self._loot_stack:
            return

        amount, ts = self._loot_stack.pop()
        d = self.data
        # Plancher à zéro : un RESET concurrent a pu remettre le total à plat,
        # et un total négatif contaminerait l'ISK/heure et la ligne d'historique.
        d.loot_val = max(0, d.loot_val - amount)

        # Retrait de la ligne correspondante dans le fil d'alertes. Son absence
        # est NORMALE, pas une anomalie : le fil est plafonné à MAX_ALERTS et le
        # bouton CLR le vide entièrement.
        try:
            for i in range(len(d.alerts) - 1, -1, -1):
                if d.alerts[i][0] == ts and d.alerts[i][1] == "LOOT":
                    del d.alerts[i]
                    break
            self._update_alert_labels()
        except Exception:
            _log_exc("CharacterWindow._undo_last_loot:2395")

        # Éclat rouge, miroir de l'éclat vert de confirmation d'un import réussi.
        try:
            self._cset(self.ll, fg=CS)
            self.root.after(500, self._loot_label_restore_fg)
        except Exception:
            _log_exc("CharacterWindow._undo_last_loot:2402")

        # Les totaux de flotte et TOTAL NET dérivent de loot_val à chaque tick :
        # rien de plus à faire pour eux.
        self._refresh_undo_btn()

    def _refresh_undo_btn(self):
        """Active ou éteint le bouton UNDO selon que la pile est vide ou non."""
        btn = self._loot_undo_btn
        if not btn:
            return
        try:
            if self._loot_stack:
                btn.config(fg=CS, cursor="hand2")
            else:
                btn.config(fg=TD, cursor="")
        except Exception:
            _log_exc("CharacterWindow._refresh_undo_btn:2416")

    # Prix de vente le plus bas à Jita, plus proche du prix réellement obtenu
    # qu'une moyenne globale — ça vaut le coup pour les objets de faction, qui
    # représentent l'essentiel de la valeur d'une cargaison de ratting.
    def _get_live_esi_price(self, type_id):

        # Cache de session — au plus une requête Jita par objet. Chaque entrée
        # vaut (prix, provisoire, horodatage) : un vrai prix Jita est conservé
        # toute la session, mais une estimation écrite après un ÉCHEC n'est que
        # provisoire et sera réessayée après PROVISIONAL_TTL.
        # Auparavant, un seul dépassement de délai ESI figeait définitivement
        # l'estimation de repli, et l'objet restait mal évalué jusqu'au
        # redémarrage.
        PROVISIONAL_TTL = 60
        hit = self._jita_price_cache.get(type_id)
        if hit is not None:
            price, provisional, stamped = hit
            if not provisional or (time.monotonic() - stamped) < PROVISIONAL_TTL:
                return price
        try:
            time.sleep(0.5)  # Throttle: max ~2 requests/sec to ESI
            url = f"https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell&type_id={type_id}"
            req = urllib.request.Request(url, headers={"User-Agent": _ESI_UA})
            with urllib.request.urlopen(req, timeout=5) as response:
                orders = json.loads(response.read().decode())
                if orders:
                    price = min(order['price'] for order in orders)
                    self._jita_price_cache[type_id] = (price, False, time.monotonic())
                    return price
        except Exception:
            _log_exc("CharacterWindow._get_live_esi_price:1943")
        # Pas de cotation (panne réseau, ou réellement aucun ordre de vente) :
        # provisoire, donc réessayable.
        fallback = self._global_prices.get(str(type_id), 0)
        self._jita_price_cache[type_id] = (fallback, True, time.monotonic())
        return fallback

    # Estimation grossière par mot-clé, utilisée quand l'ESI est injoignable :
    # une valeur approximative vaut mieux qu'un zéro qui laisserait croire que
    # la cargaison ne vaut rien. N'est appliquée qu'à des objets EVE reconnus —
    # sur un texte quelconque elle inventerait de l'ISK (voir _value_loot_text).
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

        # Trace dans le fil d'alertes : le montant s'ajoute au total, et le
        # joueur doit pouvoir vérifier ce qui a été compté.
        self.data.alerts.append((now_str, "LOOT", f"Added {fisk(amount)} loot"))
        # Refresh alert display
        self._update_alert_labels()

    # ── Animation d'estimation (thread principal) ──────────────────────

    # Le spinner existe parce que l'estimation peut durer plusieurs secondes :
    # sans retour visible, le joueur croit que son collage a été ignoré et
    # recommence. Il tourne sur le label de loot lui-même, là où le résultat
    # apparaîtra.
    def _loot_anim_start(self):
        """Begin spinning 'Searching…' on the LOOT ESTIMATE label."""
        self._loot_loading   = True
        self._loot_anim_step = 0
        if self._loot_anim_job:
            self.root.after_cancel(self._loot_anim_job)
            self._loot_anim_job = None
        self._loot_anim_tick()

    def _loot_anim_tick(self):
        """Avance d'une image du spinner et se replanifie tant que l'estimation dure."""
        if not self._loot_loading:
            return
        try:
            spin = _LOOT_SPIN[self._loot_anim_step % len(_LOOT_SPIN)]
            self._cset(self.ll, text=f"{spin} Searching...", fg=CW)
        except Exception:
            _log_exc("CharacterWindow._loot_anim_tick:1991")
        self._loot_anim_step += 1
        self._loot_anim_job = self.root.after(120, self._loot_anim_tick)

    def _loot_anim_stop(self, found):
        """Arrête le spinner. found=True déclenche un éclat vert de confirmation :
        sans lui, rien ne distingue « estimation terminée » de « rien trouvé »."""
        self._loot_loading = False
        self._loot_inflight = False   # release the guard so the next paste can process
        if self._loot_anim_job:
            self.root.after_cancel(self._loot_anim_job)
            self._loot_anim_job = None
        if found:
            self._cset(self.ll, fg="#39FF14")   # éclat vert de confirmation
            self.root.after(500, lambda: self._loot_label_restore_fg())
        else:
            self._loot_label_restore_fg()

    def _loot_label_restore_fg(self):
        """Rend au label de loot sa couleur normale après l'éclat vert."""
        self._cset(self.ll, fg=CI)

    # ── Ajustement de la fenêtre au contenu ──────────────────────────────
    # La fenêtre grandit et rétrécit selon les sections actives : activer le
    # suivi d'anomalies ou replier le détail doit changer sa taille tout de
    # suite. Sans cet ajustement, une section masquée laisserait un vide.
    def _fit(self):
        self.root.update_idletasks()
        # Deuxième passe nécessaire sous Linux/X11 : la hauteur des cadres
        # imbriqués n'est correcte qu'au second calcul.
        self.root.update_idletasks()
        # +32 pour l'en-tête, plus la hauteur de la barre d'état : sans elle, la
        # poignée se retrouve coupée par le bord bas de la fenêtre.
        h = self._body.winfo_reqheight() + 32
        if getattr(self, "_grip_bar", None) is not None:
            h += 16   # barre d'état et poignée

        # Repliée, la fenêtre est bloquée à 32 px et son corps masqué. La
        # redimensionner à la hauteur (toujours pleine) du contenu laisserait
        # une bande vide sous la barre de titre — exactement le défaut qu'on
        # voyait en rattachant un panneau détaché pendant que la fenêtre était
        # repliée. On se contente donc de MÉMORISER la nouvelle hauteur pleine,
        # pour que le prochain dépliage restaure la bonne taille (section
        # rattachée comprise), et on laisse la fenêtre repliée intacte.
        if self._is_collapsed:
            self._full_height = h
            self.char_cfg["main_full_height"] = h
            return

        saved = self.char_cfg.get("geometry", "")
        if saved:
            saved_w = saved.split("x")[0] if "x" in saved else str(WIN_W)
            # re.sub ne remplace que la partie LxH et laisse ±X±Y intact : la
        # position ne doit pas bouger quand seule la hauteur change.
            new_geom = re.sub(r"^\d+x\d+", f"{saved_w}x{h}", saved)
            self.root.geometry(new_geom)
        else:
            self.root.geometry(f"{WIN_W}x{h}")
            self._center()

    # Position par défaut au bord DROIT, pas au centre : l'UI d'EVE occupe le
    # centre de l'écran, et une fenêtre qui s'ouvrirait dessus masquerait le
    # jeu à chaque premier lancement.
    def _center(self):
        self.root.update_idletasks()
        x = self.root.winfo_screenwidth()  - WIN_W - 20
        y = (self.root.winfo_screenheight() - self.root.winfo_height()) // 2
        self.root.geometry(f"+{x}+{y}")

    # Glisser réimplémenté à la main : la fenêtre est en overrideredirect, donc
    # elle n'a pas de barre de titre système pour la déplacer.
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
        # Drapeau remis à zéro avec un léger différé : le double-clic arrive
        # après le relâchement, et sans ce délai il serait pris pour un glissé.
        self.root.after(100, lambda: setattr(self, '_dragging', False))

    # Replie la fenêtre sur sa seule barre de titre. Sert pendant un trajet ou
    # une pause : on garde le personnage sous la main sans lui laisser occuper
    # l'écran. La hauteur pleine est mémorisée pour pouvoir la restaurer.
    def _toggle_window_collapse(self, event):
        # Un déplacement se termine aussi par un relâchement : sans ce test,
        # bouger la fenêtre la replierait au passage.
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
            # Repli : on masque le corps et on fait apparaître les contrôles
            # réduits dans la barre de titre, pour garder Play/Pause à portée.
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
            _log_exc("CharacterWindow._save_pos:2126")

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

    # Les widgets ttk (ici la combobox) ne suivent pas les couleurs passées aux
    # widgets tk classiques : il faut leur déclarer un style à part, sinon la
    # liste déroulante reste en gris Windows au milieu d'une UI sombre.
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

    # Construit toute l'interface une fois pour toutes. Les mises à jour
    # suivantes ne font que réécrire le texte des labels existants : on ne
    # reconstruit jamais de widgets en cours de session, car sur une surcouche
    # toujours au premier plan, cela produit un clignotement très visible.
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

        # Contrôles réduits, visibles uniquement fenêtre repliée : on doit
        # pouvoir mettre en pause sans avoir à déplier.
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
        # Enregistrés comme jeu de boutons : _update_buttons les recolore en
        # même temps que les autres, sinon les deux jeux divergeraient.
        self._hdr_btn_set = {"go": self._hdr_b_go, "pa": self._hdr_b_pa, "st": self._hdr_b_st}
        self._btn_sets.append(self._hdr_btn_set)
        # Pas encore affichés — ils n'apparaissent qu'au repli.

        # Chaque enfant de la barre de titre sert aussi de poignée : sans ça,
        # cliquer sur le texte du titre ne déplacerait pas la fenêtre.
        # Ajout (add="+") pour ne pas écraser les liaisons déjà posées.
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

        # La section DPS a disparu du tableau de bord : elle vit désormais dans
        # l'overlay autonome, bien plus utile posée sur le jeu. Le bas de la
        # fenêtre se réduit donc à une barre d'état minimale.

        # ── Barre d'état (bas) : bande fine avec une poignée décorative ──
        # Teintée comme un panneau pour se détacher de la zone de contenu.
        # La fenêtre de personnage s'ajuste à son contenu et n'est PAS
        # redimensionnable : la poignée n'est là que par cohérence visuelle avec
        # la vue d'ensemble — aucune liaison de glissé, aucun curseur de
        # redimensionnement.
        self._grip_bar = tk.Frame(self.root, bg=BG_P, height=16)
        self._grip_bar.pack(fill="x", side="bottom")
        self._grip_bar.pack_propagate(False)
        grip_bar = self._grip_bar
        grip_l = tk.Label(grip_bar, text="⤡",
                          font=tkfont.Font(family="Consolas", size=10, weight="bold"),
                          bg=BG_P, fg=T1)
        grip_l.pack(side="right", padx=4)

    # Barre de contrôle. Le découpage Play / Pause / Stop existe parce que les
    # trois répondent à des situations différentes : Pause fige le chrono le
    # temps d'un trajet, Stop gèle l'affichage pour lire les totaux, Reset
    # archive la session et repart de zéro.
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

        # Verrou de presse-papiers, à côté de RESET / NEXT SITE plutôt que dans
        # l'en-tête : celui-ci est déjà chargé, ces deux-là sont exactement le
        # même idiome de bouton texte, et c'est ici que la main du joueur se
        # trouve déjà en pleine session. L'état est GLOBAL, pas propre à ce
        # personnage — tous les boutons montrent le même verrou.
        self._clip_btn = tk.Label(ctrl_wrap, text="CLIP", fg=CA, font=F8B, bg=BG_P,
                                  cursor="hand2", bd=0, padx=6)
        self._clip_btn.pack(side="left")
        self._clip_btn.bind("<Button-1>", lambda e: self._toggle_clip_lock())
        self._clip_btn.bind("<Enter>",    lambda e: self._clip_btn.config(bg=BDG))
        self._clip_btn.bind("<Leave>",    lambda e: self._clip_btn.config(bg=BG_P))
        DynamicTooltip(self._clip_btn,
                       lambda: ("Clipboard LOCKED - loot copies ignored (click to resume)"
                                if _CLIP_LOCK else
                                "Clipboard live - click to lock before copying a fit or appraisal"))
        self._refresh_clip_btn()

        self._main_btn_set = {"go": self._b_go, "pa": self._b_pa, "st": self._b_st}
        self._btn_sets.append(self._main_btn_set)
        self._update_buttons()


    # Fil d'alertes : scram, web, escalade, dreadnought, loot. Volontairement
    # court (MAX_ALERTS) — c'est un fil d'événements récents, pas un journal ;
    # au-delà, l'important se noie dans l'ancien et la fenêtre s'allonge.
    # Le paramètre detached ajuste la mise en page pour la version flottante.
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
            # Le bouton CLR est repris dans l'en-tête détaché : vider le fil doit rester
            # possible sans revenir à la fenêtre principale.
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

    # Détaché, le fil d'alertes peut être agrandi librement : la police suit
    # pour rester lisible à distance, un panneau posé sur un second écran.
    def _on_alert_detached_resize(self, event):
        if not self._alert_detached:
            return
        h = event.height
        
        # Calculate font size based on height (base 9pt at ~80px)
        base_h = 80
        base_size = 9
        scale = max(0.8, min(2.5, h / base_h))
        new_size = max(8, min(16, int(base_size * scale)))
        
        # Uniquement si la taille a changé : ce gestionnaire se déclenche à chaque
        # pixel de glissé, et recalculer la police à chaque fois rendrait le
        # redimensionnement saccadé.
        if hasattr(self, '_alert_det_font_size') and self._alert_det_font_size == new_size:
            return
        self._alert_det_font_size = new_size
        
        # Redessin forcé : changer la taille d'une police ne suffit pas à faire
        # recalculer leur mise en page aux widgets déjà disposés.
        self._last_alert_key = None

    # Section ISK : la raison d'être de l'app. L'ISK/heure est le seul chiffre
    # qui permette de comparer deux vaisseaux, deux sites ou deux systèmes,
    # puisqu'il ramène tout à la même unité de temps.
    def _build_isk(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F7B = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [ISK TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Pas d'en-tête en version détachée : DetachedWindow fournit déjà le sien,
        # et deux barres de titre superposées seraient absurdes.
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

    # Le détail (brut, taxes, kills, loot) explique COMMENT on arrive au net.
    # Repliable parce qu'on ne le consulte qu'en fin de session : pendant le
    # combat, seul l'ISK/heure compte.
    def _build_breakdown_content(self, brk_wrap):
        F8  = tkfont.Font(family="Consolas", size=8)
        # Une seule police de valeur partagée par les cinq labels, au lieu d'un
        # objet Font par label : _brk_fit_row doit mesurer avec EXACTEMENT la
        # police utilisée à l'écran, et une référence unique le garantit.
        FVAL = tkfont.Font(family="Consolas", size=11, weight="bold")
        self._brk_hdr_font = F8
        self._brk_val_font = FVAL
        self._brk_r1_hdrs  = []
        self._brk_r3_hdrs  = []

        r1 = tk.Frame(brk_wrap, bg=BG_P)
        r1.pack(fill="x")
        self._brk_r1 = r1
        for idx, (lbl_text, c) in enumerate([("BOUNTIES", CG), ("EST. TAXES", CT), ("KILLS", CG)]):
            f = tk.Frame(r1, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")

            # Align: 0=Left(w), 1=Center(center), 2=Right(e)
            align = "w" if idx == 0 else ("center" if idx == 1 else "e")

            hdr_l = tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD)
            hdr_l.pack(anchor=align)
            self._brk_r1_hdrs.append(hdr_l)
            l = tk.Label(f, text="0" if lbl_text == "KILLS" else "0 ISK",
                         font=FVAL, bg=BG_P, fg=c)
            l.pack(anchor=align)

            if lbl_text == "BOUNTIES":
                self.gl = l
                DynamicTooltip(l, lambda: self._brk_exact.get("gross", "—"))
            elif lbl_text == "EST. TAXES":
                self.tl = l
                DynamicTooltip(hdr_l, lambda: f"Corp Tax: {self.tax_var.get()}%")
                # Infobulle fusionnée et non deux DynamicTooltip empilés : chacun
                # crée son propre Toplevel à la même position, et deux bulles
                # superposées ne laissent lire que celle du dessus.
                DynamicTooltip(l, lambda: (f"Corp Tax: {self.tax_var.get()}%\n"
                                           f"{self._brk_exact.get('taxes', '—')}"))
            else:
                self.bl = l

        tk.Frame(brk_wrap, bg=BD, height=1).pack(fill="x", pady=3)

        r3 = tk.Frame(brk_wrap, bg=BG_P)
        r3.pack(fill="x")
        self._brk_r3 = r3
        for idx, (lbl_text, c) in enumerate([("LOOT ESTIMATE (CTRL+C)", CI), ("TOTAL NET (+LOOT)", CI)]):
            f = tk.Frame(r3, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")

            # Align: 0=Left(w), 1=Right(e)
            align = "w" if idx == 0 else "e"

            hdr_l = tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD)
            hdr_l.pack(anchor=align)
            self._brk_r3_hdrs.append(hdr_l)
            l = tk.Label(f, text="0 ISK", font=FVAL, bg=BG_P, fg=c)
            l.pack(anchor=align)

            if lbl_text == "LOOT ESTIMATE (CTRL+C)":
                self.ll = l
                DynamicTooltip(l, lambda: self._brk_exact.get("loot", "—"))
                # Conservé en attribut : _update_breakdown_labels y écrit
                # « (LOCKED) » en rouge quand le presse-papiers est verrouillé.
                # L'avertissement va sur l'EN-TÊTE et non sur la valeur, pour
                # deux raisons : on verrouille justement parce qu'on manipule du
                # butin, donc masquer le total courant serait contre-productif ;
                # et _loot_label_restore_fg() repeint la valeur en CI après
                # chaque estimation, ce qui écraserait un rouge posé là.
                self._loot_hdr_lbl = hdr_l
                Tooltip(hdr_l, "Copy items from inventory (CTRL+C) to parse value")

                # UNDO : retire le dernier import. Éteint tant que la pile est
                # vide, pour qu'il ne promette pas une action indisponible.
                self._loot_undo_btn = tk.Label(
                    f, text="UNDO",
                    font=tkfont.Font(family="Consolas", size=7, weight="bold"),
                    bg=BG_P, fg=TD, padx=3)
                self._loot_undo_btn.pack(anchor=align)
                self._loot_undo_btn.bind("<Button-1>", lambda e: self._undo_last_loot())
                self._loot_undo_btn.bind("<Enter>", lambda e: self._loot_undo_btn.config(
                    bg=BDG if self._loot_stack else BG_P))
                self._loot_undo_btn.bind("<Leave>", lambda e: self._loot_undo_btn.config(bg=BG_P))
                DynamicTooltip(self._loot_undo_btn,
                               lambda: (f"Remove last loot import ({fisk(self._loot_stack[-1][0])})"
                                        if self._loot_stack else "No loot import to undo"))
                self._refresh_undo_btn()
            else:
                self.tnl = l
                DynamicTooltip(l, lambda: self._brk_exact.get("total_net", "—"))

    # Ajuste une rangée du breakdown à la place RÉELLEMENT disponible.
    #
    # Le breakdown affiche des montants exacts (fiskf) : c'est là que le joueur
    # vient chercher le chiffre au dernier ISK, et l'abréger par défaut viderait
    # la section de son intérêt. Mais trois nombres à neuf chiffres ne tiennent
    # pas dans 290 px, et pack(expand=True, fill="x") ne rétrécit pas les
    # colonnes trop larges — il sert les premières et rogne la dernière, qui
    # disparaît du bord droit (KILLS réduit à un fragment de glyphe).
    #
    # On mesure donc la rangée avant d'écrire : tant que la forme longue tient,
    # on la garde ; sinon TOUTE la rangée bascule sur fisk(), car mélanger
    # « 100 000 000 » et « -12.50M » côte à côte serait illisible. Le montant
    # exact reste accessible en infobulle sur chaque valeur.
    #
    # Mesurer la largeur courante plutôt que de coder un seuil de magnitude fait
    # que le panneau ISK détaché — et la fenêtre principale, redimensionnable
    # elle aussi — gardent les montants exacts tant qu'ils sont assez larges.
    #
    # Marge interne d'un tk.Label (padx par défaut + bordure) : mesurée à 6 px,
    # constante pour tous les labels du breakdown. Sans elle on sous-estime
    # chaque colonne et la rangée déborde encore d'un cheveu.
    _BRK_LBL_PAD = 6

    def _brk_fit_row(self, row, hdrs, cells):
        # cells : [(forme_longue, forme_courte), ...] alignées sur hdrs.
        # Renvoie la liste des chaînes à afficher.
        long_forms = [c[0] for c in cells]
        hf, vf = self._brk_hdr_font, self._brk_val_font
        if row is None or hf is None or vf is None or len(hdrs) != len(cells):
            return long_forms
        try:
            avail = row.winfo_width()
            # Avant le premier affichage Tk renvoie 1 : on ne sait rien encore,
            # donc on garde l'exact — le tick suivant tranchera pour de bon.
            if avail <= 1:
                return long_forms
            # Largeur naturelle d'une colonne = la plus large de ses deux lignes.
            need = sum(max(hf.measure(h.cget("text")), vf.measure(lng)) + self._BRK_LBL_PAD
                       for h, lng in zip(hdrs, long_forms))
        except Exception:
            _log_exc("CharacterWindow._brk_fit_row")
            return long_forms
        return long_forms if need <= avail else [c[1] for c in cells]

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

        # Redimensionnement, qu'il vienne de la fenêtre principale ou du panneau ISK
        # détaché : les deux passent par ici.
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
                _log_exc("CharacterWindow._toggle_breakdown:2584")
        else:
            self._fit()

    # Suivi de mission. Son intérêt principal est le compteur de storyline :
    # EVE en propose une tous les 16 rendus et n'indique nulle part où l'on en
    # est. Le nom de la mission, lui, reste vide — le client ne l'écrit dans
    # aucun log, donc aucun lecteur de log ne peut le connaître.
    def _build_missions(self, parent, detached=False):
        F8  = tkfont.Font(family="Consolas", size=8)
        F7B = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9  = tkfont.Font(family="Consolas", size=9)
        F9B = tkfont.Font(family="Consolas", size=9, weight="bold")
        F10B = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._msn_pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [MISSION TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Pas d'en-tête en version détachée : DetachedWindow fournit déjà le sien,
        # et deux barres de titre superposées seraient absurdes.
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

    # Suivi d'anomalies : découpe la session en sites successifs pour répondre
    # à « ce site vaut-il le temps qu'il prend ? ». EVE ne signale ni le début
    # ni la fin d'un site, d'où la déduction par silence de combat (ANOM_GAP).
    def _build_anomalies(self, parent, detached=False):
        F8   = tkfont.Font(family="Consolas", size=8)
        F7B  = tkfont.Font(family="Consolas", size=7, weight="bold")
        F8B  = tkfont.Font(family="Consolas", size=8, weight="bold")
        F9B  = tkfont.Font(family="Consolas", size=9, weight="bold")
        F10B = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._anom_pad = dict(padx=6, pady=(2, 4))

        # ── Header: [accent] [ANOMALY TRACKER] [ON/OFF] ... [▼/▶] [↱] ──
        # Pas d'en-tête en version détachée : DetachedWindow fournit déjà le sien,
        # et deux barres de titre superposées seraient absurdes.
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

        # \u2500\u2500 Butin de la passe \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        # La ligne du dessus ne compte QUE les bounties : anom_current["isk"]
        # n'est aliment\u00e9 que par _anom_add_bounty, et EVE n'\u00e9crit rien sur le
        # butin dans ses logs. Un MTU pos\u00e9 sur quatre havens puis ramass\u00e9 d'un
        # coup arrive donc comme UNE cargaison pour tout le groupe, et n'appara\u00eet
        # nulle part dans les stats par site.
        # Le groupe de sites, c'est la session : la valeur ici est le total de
        # session, et l'ISK par site le divise par les sites parcourus.
        tk.Frame(aw, bg=BD, height=1).pack(fill="x", pady=3)

        r3 = tk.Frame(aw, bg=BG_P)
        r3.pack(fill="x")
        for lbl_text, c, attr, tip in [
            ("RUN LOOT", CI, "_anom_run_loot_lbl",
             "Loot valued this session - one MTU pickup covers every site since the last reset"),
            ("ISK / SITE (+LOOT)", CG, "_anom_isk_site_lbl",
             "Session net including loot, split across the sites run.\n"
             "For MTU runs, do NOT press NEXT SITE until you have salvaged -\n"
             "it saves and resets the session, so the loot lands on one site."),
        ]:
            f = tk.Frame(r3, bg=BG_P)
            f.pack(side="left", expand=True, fill="x")
            hdr_l = tk.Label(f, text=lbl_text, font=F8, bg=BG_P, fg=TD)
            hdr_l.pack(anchor="w")
            l = tk.Label(f, text="\u2014", font=F9B, bg=BG_P, fg=c)
            l.pack(anchor="w")
            setattr(self, attr, l)
            # Le pi\u00e8ge du NEXT SITE n'est devinable par personne : il se dit ici.
            Tooltip(hdr_l, tip)
            Tooltip(l, tip)

        if detached:
            self._anom_det_labels = {"cur": self._anom_cur_lbl, "cleared": self._anom_cleared_lbl,
                                      "avg_time": self._anom_avg_time_lbl, "avg_isk": self._anom_avg_isk_lbl,
                                      "best_isk": self._anom_best_isk_lbl,
                                      "run_loot": self._anom_run_loot_lbl,
                                      "isk_site": self._anom_isk_site_lbl}
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
            for key in ("cur", "cleared", "avg_time", "avg_isk", "best_isk",
                        "run_loot", "isk_site"):
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
            
        # Mise à l'échelle sur la LARGEUR et non la hauteur : replier le détail
        # réduit brutalement la hauteur, et le texte rapetisserait sans raison alors
        # que la fenêtre est toujours aussi large.
        w = event.width
        last_w = getattr(self, '_isk_det_last_w', 0)
        if abs(w - last_w) < 5:
            return
        self._isk_det_last_w = w

        self._scaling_isk = True
        try:
            # Une largeur de référence d'environ 350 px donne un facteur proche de 1,
            # ce qui garde des tailles de texte raisonnables par défaut.
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

    # ── Historique DPS pour le graphique ─────────────────────────────────

    # Échantillonnage à chaque tick plutôt qu'à chaque événement de combat : le
    # graphique a besoin d'un pas de temps RÉGULIER, sinon une rafale de coups
    # tasserait les points et une accalmie les étirerait, rendant la courbe
    # illisible. Les creux entre deux salves font partie de l'information.
    def _sample_dps_history(self, dps_out=None, dps_in=None):
        # _tick a déjà calculé les deux valeurs pour ce tour : on les accepte en
        # paramètre plutôt que de rappeler dps() deux fois inutilement.
        d = self.data
        if dps_out is None: dps_out = d.dps(True)
        if dps_in is None:  dps_in  = d.dps(False)
        d.dps_hist.append((time.monotonic(), dps_out, dps_in))

    # ── Activation et repli des sections ─────────────────────────────────
    # Chaque joueur ne suit qu'une partie des métriques : un ratteur d'anomalies
    # n'a que faire du suivi de mission, et inversement. Désactiver une section
    # la retire de la fenêtre, qui rétrécit d'autant.
    def _toggle_enabled(self, section):
        attr = f"_{section}_enabled"
        enabled = not getattr(self, attr)

        # ── Exclusion mutuelle : missions et anomalies jamais ensemble ──
        if enabled and section in ("msn", "anom"):
            other = "anom" if section == "msn" else "msn"
            if getattr(self, f"_{other}_enabled"):
                self._force_disable(other)

        setattr(self, attr, enabled)
        self.char_cfg[f"{section}_enabled"] = enabled
        save_config(self.cfg)

        # Désactiver une section détachée doit d'abord la rattacher : sinon sa
        # fenêtre flottante resterait orpheline à l'écran.
        if not enabled:
            self._force_detach_off(section)

        # Update ON/OFF button appearance
        on_btn = getattr(self, f"_{section}_on_btn", None)
        if on_btn:
            on_btn.config(text="ON" if enabled else "OFF", fg=CA if enabled else CS)

        # Les contrôles d'en-tête suivent l'état : une section éteinte ne doit pas
        # laisser des boutons qui ne pilotent plus rien.
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

    # Missions et anomalies décrivent la même chose — l'activité en cours — et
    # se disputeraient la même place : activer l'une éteint donc l'autre.
    def _force_disable(self, section):

        # Extinction forcée, imposée par l'exclusion mutuelle.
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

    # Désactiver une section détachée doit aussi fermer sa fenêtre flottante,
    # sinon elle resterait orpheline à l'écran, sans plus rien pour la piloter.
    def _force_detach_off(self, section):

        # Rattache PUIS ferme la fenêtre flottante : fermer d'abord perdrait la
        # position enregistrée du panneau.
        detached_attr = f"_{section}_detached"
        if getattr(self, detached_attr, False):
            window_attr = f"_{section}_window"
            win = getattr(self, window_attr, None)
            if win:
                try:
                    win._save_geometry()
                    win.w.destroy()
                except Exception:
                    _log_exc("CharacterWindow._force_detach_off:2924")
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

    # Résolution par NOM de la fonction de construction : détacher, rattacher
    # et activer une section doivent tous rebâtir le même contenu, et passer par
    # une table évite d'avoir trois chaînes de if à garder synchronisées.
    def _section_build_name(self, section):
        names = {"isk": "isk", "msn": "missions", "anom": "anomalies"}
        return names.get(section, section)

    # Les marges diffèrent d'une section à l'autre : détachée ou intégrée, une
    # section n'a pas les mêmes voisines, et un espacement uniforme laissait des
    # trous visibles entre les panneaux.
    def _get_section_pad(self, section):
        return dict(padx=6, pady=(2, 4))

    # Replier une section garde son en-tête (donc son état d'un coup d'œil) tout
    # en rendant la place à l'écran. Distinct de la désactivation : replié, le
    # suivi continue ; désactivé, il s'arrête.
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

    # Fabrique d'en-têtes commune aux quatre sections : la couleur d'accent est
    # le seul repère qui permette de les distinguer du coin de l'œil, donc elles
    # doivent partager exactement la même structure.
    def _sec(self, par, title, accent):
        tb = tk.Frame(par, bg=BG_P, height=20)
        tb.pack(fill="x")
        tb.pack_propagate(False)
        tk.Frame(tb, bg=accent, width=3).pack(side="left", fill="y")
        tk.Label(tb, text=f"  {title}", font=tkfont.Font(family="Consolas", size=8, weight="bold"), bg=BG_P, fg=accent).pack(side="left")

    # Seule la COULEUR change, jamais la disposition : les boutons gardent leur
    # place quel que soit l'état, pour qu'on puisse cliquer sans regarder.
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

    # Le paramètre `frozen` sert l'état Stop : l'affichage doit rester figé sur
    # les totaux de fin de session, alors que les données continuent d'exister.
    # On passe un instantané plutôt que de geler l'objet Data lui-même.
    def _update_isk_labels(self, labels, frozen=None):
        if not labels: return
        il = labels.get("il")
        sl = labels.get("sl")
        if frozen:
            if il:
                font = self._isk_font_big if frozen["isk_font"] == "big" else self._isk_font_calc
                self._cset(il, text=frozen["isk_text"], fg=frozen["isk_fg"], font=font)
            if sl:
                self._cset(sl, text=frozen["timer"])
        else:
            d = self.data
            if il:
                if self._st == "running":
                    if d.secs() >= 60 and d.bg > 0:
                        self._cset(il, text=f"{fisk(d.isk())} ISK", fg=CI, font=self._isk_font_big)
                    else:
                        # Pas encore assez de données : l'animation CALC vaut mieux qu'un zéro,
                        # qui se lirait comme un vrai résultat.
                        self._show_calc_on(il)
                elif self._st == "paused":
                    if d.secs() >= 60 and d.bg > 0:
                        self._cset(il, text=f"{fisk(d.isk())} ISK", fg=CP, font=self._isk_font_big)
                    else:
                        self._cset(il, text="\u2014 PAUSED \u2014", fg=CP, font=self._isk_font_calc)
                elif self._st == "stopped":
                    self._cset(il, text="\u2014 STANDBY \u2014", fg=TD, font=self._isk_font_calc)
            if sl:
                dur = fdur(d.secs()) if (d.t0 or d.acc_sec > 0) else "00:00"
                self._cset(sl, text=dur)

    # Met à jour les labels du breakdown (bounties, taxes, kills, loot)
    # Configure un label uniquement si une valeur a réellement changé.
    def _cset(self, lbl, **kw):
        """Dirty-flag wrapper around Label.config().

        The per-tick updaters below used to call .config() unconditionally —
        measured at 14 calls per tick per character, 100 % of them rewriting the
        value already on screen. Same idea as MainUI._lset, but the cache lives
        ON THE WIDGET rather than in an id()-keyed dict: detached panels destroy
        and rebuild their labels, and CPython reuses id() after GC, so an
        id-keyed cache can go stale and silently freeze a label.
        """
        if lbl is None:
            return
        prev = getattr(lbl, "_last_cfg", None)
        if prev is None:
            prev = {}
            try:
                lbl._last_cfg = prev
            except Exception:
                prev = None
        if prev is None:                      # can't cache — just write through
            try: lbl.config(**kw)
            except Exception: _log_exc("CharacterWindow._cset:3053")
            return
        delta = {k: v for k, v in kw.items() if prev.get(k, _UNSET) != v}
        if not delta:
            return
        prev.update(delta)
        try:
            lbl.config(**delta)
        except Exception:
            _log_exc("CharacterWindow._cset:3061")

    def _update_breakdown_labels(self, frozen=None):
        # Les deux sources fournissent les mêmes GRANDEURS BRUTES, et le
        # formatage se fait ici, en un seul endroit : c'est lui qui décide entre
        # forme longue et courte selon la largeur (voir _brk_fit_row), et le
        # figé doit prendre exactement la même décision que le direct.
        if frozen:
            gross = frozen.get("gross_v", 0.0)
            taxes = frozen.get("taxes_v", 0.0)
            kills = frozen.get("kills", "0")
            loot  = frozen.get("loot_v", 0.0)
            net   = frozen.get("net_v", 0.0)
        else:
            d = self.data
            gross = d.bg
            taxes = d.bg * d.tax
            kills = str(d.bc)
            loot  = d.loot_val
            net   = d.bg * (1 - d.tax) + d.loot_val

        # Montants exacts servis par les infobulles, qu'on affiche la forme
        # longue ou la courte : c'est le filet de sécurité qui autorise
        # l'abréviation sans jamais rendre le chiffre exact inaccessible.
        self._brk_exact = {
            "gross":     f"{fiskf(gross)} ISK",
            "taxes":     f"-{fiskf(taxes)} ISK",
            "loot":      f"{fiskf(loot)} ISK",
            "total_net": f"{fiskf(net)} ISK",
        }

        g_txt, t_txt, k_txt = self._brk_fit_row(
            self._brk_r1, self._brk_r1_hdrs,
            [(f"{fiskf(gross)} ISK", f"{fisk(gross)} ISK"),
             (f"-{fiskf(taxes)} ISK", f"-{fisk(taxes)} ISK"),
             (kills, kills)])
        self._cset(self.gl, text=g_txt)
        self._cset(self.tl, text=t_txt)
        self._cset(self.bl, text=k_txt)

        l_txt, n_txt = self._brk_fit_row(
            self._brk_r3, self._brk_r3_hdrs,
            [(f"{fiskf(loot)} ISK", f"{fisk(loot)} ISK"),
             (f"{fiskf(net)} ISK",  f"{fisk(net)} ISK")])
        if not self._loot_loading:   # don't overwrite the spinner
            self._cset(self.ll, text=l_txt)
        self._cset(self.tnl, text=n_txt)

        # Avertissement de verrou, dans les deux branches : l'état figé du Stop
        # n'a rien à voir avec le verrou, qui reste actif fenêtre arrêtée ou non.
        # _cset ne réécrit que si la valeur change, donc pas de coût par tick.
        if self._loot_hdr_lbl:
            if _CLIP_LOCK:
                self._cset(self._loot_hdr_lbl, text="LOOT ESTIMATE (LOCKED)", fg=CS)
            else:
                self._cset(self._loot_hdr_lbl, text="LOOT ESTIMATE (CTRL+C)", fg=TD)

    # Met à jour les labels de mission (nom, objectif, compteurs)
    def _update_mission_labels(self, frozen=None):
        if frozen:
            name = frozen.get("msn_name", "\u2014 None \u2014")
            self._cset(self._msn_name_lbl, text=name[:24],
                       fg=C_MSN if name != "\u2014 None \u2014" else CM)
            obj = frozen.get("msn_obj", "\u2014")
            self._cset(self._msn_obj_lbl, text=obj, fg=CA if "\u2714" in obj else CM)
            self._cset(self._msn_done_lbl,  text=frozen.get("msn_done", "0"))
            self._cset(self._msn_story_lbl, text=frozen.get("msn_story", "0/16"))
        else:
            d = self.data
            name = d.mission_name or "\u2014 None \u2014"
            self._cset(self._msn_name_lbl, text=name[:24],
                       fg=C_MSN if d.mission_name else CM)
            if d.mission_obj_met:
                self._cset(self._msn_obj_lbl, text="\u2714 DONE", fg=CA)
            elif d.mission_name:
                self._cset(self._msn_obj_lbl, text="IN PROGRESS", fg=CP)
            else:
                self._cset(self._msn_obj_lbl, text="\u2014", fg=CM)
            self._cset(self._msn_done_lbl,  text=str(d.missions_done))
            self._cset(self._msn_story_lbl, text=f"{self._storyline_ctr}/16")

    # Le fil d'alertes est la seule zone RECONSTRUITE plutôt que mise à jour :
    # son contenu est une liste de longueur variable, pas un ensemble fixe de
    # labels. D'où la comparaison préalable — reconstruire à chaque tick ferait
    # clignoter la section en permanence.
    def _update_alert_labels(self, frozen=None):
        if frozen:
            alerts = frozen.get("msn_alerts", [])
        else:
            alerts = self.data.alerts

        alert_key = hash(tuple((t, a, x) for t, a, x in alerts)) if alerts else 0
        if not hasattr(self, '_last_alert_key') or self._last_alert_key != alert_key:
            self._last_alert_key = alert_key
            
            # Détaché, le panneau peut être agrandi : la police suit. Intégré, elle
            # reste fixe, la fenêtre s'ajustant déjà à son contenu.
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
            self._cset(self._anom_cur_lbl,
                       text=cur_time if cur_time != "\u2014" else "\u2014 Stopped \u2014",
                       fg=C_ANOM if cur_time != "\u2014" else CM)
            self._cset(self._anom_cleared_lbl,  text=str(sites))
            self._cset(self._anom_avg_time_lbl, text=avg_time)
            self._cset(self._anom_avg_isk_lbl,  text=avg_isk)
            self._cset(self._anom_best_isk_lbl, text=best_isk)
            self._cset(self._anom_run_loot_lbl, text=frozen.get("anom_run_loot", "—"))
            self._cset(self._anom_isk_site_lbl, text=frozen.get("anom_isk_site", "—"))
        else:
            d = self.data
            n, avg_time, avg_isk, best_isk, cur_secs, run_loot, isk_site = self._anom_stats()

            # En pause, on fige le chrono du site : le laisser courir pendant un trajet
            # fausserait la durée moyenne par anomalie.
            if self._st == "paused" and self._anom_paused_secs > 0:
                cur_secs = self._anom_paused_secs
            if d.anom_current and cur_secs > 0:
                self._cset(self._anom_cur_lbl, text=fdur(cur_secs),
                           fg=CP if self._st == "paused" else C_ANOM)
            elif self._st == "running":
                self._cset(self._anom_cur_lbl, text="\u2014 Warping \u2014", fg=CM)
            elif self._st == "paused":
                self._cset(self._anom_cur_lbl, text="\u2014 Paused \u2014", fg=CP)
            else:
                self._cset(self._anom_cur_lbl, text="\u2014 Idle \u2014", fg=CM)
            self._cset(self._anom_cleared_lbl,  text=str(n))
            self._cset(self._anom_avg_time_lbl, text=fdur(avg_time) if avg_time > 0 else "\u2014")
            self._cset(self._anom_avg_isk_lbl,  text=fisk(avg_isk) if avg_isk > 0 else "\u2014")
            self._cset(self._anom_best_isk_lbl, text=fisk(best_isk) if best_isk > 0 else "\u2014")
            self._cset(self._anom_run_loot_lbl, text=fisk(run_loot) if run_loot > 0 else "\u2014")
            self._cset(self._anom_isk_site_lbl, text=fisk(isk_site) if isk_site > 0 else "\u2014")

    # Pendant la première minute, l'ISK/heure n'a pas de sens (voir Data.isk) :
    # plutôt qu'un zéro trompeur, on affiche une animation qui dit clairement
    # « en cours de calcul ».
    def _show_calc(self): self._show_calc_on(self.il)

    # Affiche l'animation CALC sur un label donné
    def _show_calc_on(self, label):
        self._calc_dots = (self._calc_dots + 1) % 4
        dots = "." * self._calc_dots
        pad  = " " * (3 - self._calc_dots)
        if self._st != "running" or (self.data.t0 is None and self.data.acc_sec == 0):
            self._cset(label, text="\u2014 STANDBY \u2014", fg=TD)
        else:
            self._cset(label, text=f"\u25C8 CALC{dots}{pad}", fg=CK)

    # Fermeture d'une fenêtre de personnage. L'ordre compte : archiver la
    # session AVANT de détruire les widgets (le taux de taxe se lit dans un
    # champ), puis annuler les boucles after() — sinon elles se déclencheraient
    # sur des widgets détruits.
    def _quit(self):
        d = self.data

        # Always save session on close if there's any data worth saving
        if not self._session_saved and (d.bg > 0 or d.dd > 0 or d.loot_val > 0):

            # Le segment en cours est versé dans le temps accumulé : sans ça, arrêter une
            # session en perdrait la dernière portion.
            if d.t0:
                d.acc_sec += (datetime.now(timezone.utc) - d.t0).total_seconds()
                d.t0 = None
            try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
            except Exception:
                _log_exc("CharacterWindow._quit:3209")
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
                _log_exc("CharacterWindow._quit:3231")
        save_config(self.cfg)
        if self.fh:
            self.fh.close()
        # Cancel pending after() loops so they don't fire on destroyed widgets
        for _job in ("_poll_job", "_tick_job", "_loot_anim_job"):
            jid = getattr(self, _job, None)
            if jid:
                try: self.root.after_cancel(jid)
                except Exception: _log_exc("CharacterWindow._quit:3241")
                setattr(self, _job, None)
        self.root.destroy()   # destroys this Toplevel; MainUI root stays alive

    # ── Analyse d'une ligne de gamelog ───────────────────────────────────
    # Cœur de l'application : chaque ligne du gamelog passe ici. Appelée
    # potentiellement des centaines de fois par seconde en plein combat, d'où
    # l'ordre des tests — les événements les plus fréquents d'abord, et un
    # filtre par mots-clés en amont pour écarter d'emblée les lignes inutiles.
    def _parse(self, raw):
        d = self.data
        ts = datetime.now(timezone.utc)
        m = RE_TS.search(raw)
        if m:
            try:
                ts = datetime.strptime(m.group(1), "%Y.%m.%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                _log_exc("CharacterWindow._parse:3254")

        if RE_SS.search(raw) or raw.strip().startswith("---"): return

        # Filtre rapide : en plein combat le gamelog dépasse la centaine de lignes
        # par seconde et la plupart ne nous concernent pas. Un test d'appartenance
        # sur quelques mots-clés coûte bien moins cher que de lancer une douzaine
        # de regex sur chaque ligne.
        if not any(k in raw for k in ('(combat)', '(bounty)', '(notify)', 'Objective', 'mission', 'standings', 'Dreadnought')):
            return

        # Les événements les plus fréquents en premier : chaque test évité l'est pour
        # des centaines de lignes par seconde.
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

        # EWAR — le scram arrive en ligne (combat). Groupe 1 = variante HTML,
        # groupe 2 = variante texte brut.
        m = RE_SCRAM.search(raw)
        if m:
            npc = shtml((m.group(1) or m.group(2)).strip())
            d.alerts.append((now_str, "SCRAM", f"\u26D4 SCRAMBLED by {npc}!"))
            self._flash_alert()
            return

        # EWAR — le web arrive en ligne (notify) dans ce même gamelog. Il était
        # autrefois cherché dans les chatlogs, qui ne portent jamais de balise
        # « (notify) » : les alertes WEB ne pouvaient donc jamais se déclencher.
        # (« (notify) » figure déjà dans le filtre rapide ci-dessus, ces lignes
        # parviennent donc bien jusqu'ici.)
        m = RE_WEB.search(raw)
        if m:
            npc = shtml(m.group(1).strip())
            d.alerts.append((now_str, "WEB", f"\u26A0 WEBBED by {npc}!"))
            self._flash_alert()
            return

    # ── Boucle de lecture des logs ───────────────────────────────────────
    # Lit une fois les nouveaux logs (gamelog + detection de rotation).
    # Appelé par le timer _poll ET par le watchdog (sur événement fichier).
    def _read_logs_once(self):
        if getattr(self, "_suspended", False) or self._st != "running":
            return
        try:
            self._read()
            self._check_gamelog_rotation()
        except Exception:
            _log_exc("CharacterWindow._read_logs_once:3366")

    # Boucle de lecture des logs. Quand le watchdog est actif ce timer n'est
    # plus qu'un filet de sécurité lent (2 s) ; sinon c'est le lecteur principal
    # à poll_ms. La lecture du presse-papiers vit dans _tick pour rester réactive.
    def _poll(self):
        try:
            self._read_logs_once()
        except Exception:
            _log_exc("CharacterWindow._poll:3375")
        interval = self.poll_ms
        mu = self._main_ui
        if mu is not None and getattr(mu, "_log_observer", None) is not None:
            interval = max(self.poll_ms, 2000)
        self._poll_job = self.root.after(interval, self._poll)

    # ── UI tick loop (updates labels) ────────────────────────────────
    # Boucle de mise à jour de l'UI (s'exécute toutes les poll_ms ms)
    def _tick(self):
        self._last_tick_wall = time.monotonic()
        # Le presse-papiers est lu une seule fois pour toute la flotte par
        # MainUI._poll_clipboard ; ici on ne lit que si la fenêtre tourne seule.
        if self._main_ui is None and not getattr(self, "_suspended", False):
            self._check_clipboard()
        d = self.data
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            _log_exc("CharacterWindow._tick:3393")

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

        # Mise à jour de la fenêtre principale, uniquement là où une valeur a changé.
        live = d.secs() >= 60 and d.bg > 0
        isk_text = f"{fisk(d.isk())} ISK" if live else "\u2014 STANDBY \u2014"
        # _cset plutôt que l'ancienne garde _last_values : _show_calc_on() écrit lui
        # aussi dans self.il, et deux caches indépendants pour un même label
        # pouvaient diverger et le laisser figé sur une image de CALC périmée.
        self._cset(self.il, text=isk_text,
                   fg=CI if live else (CP if self._st == "paused" else TD),
                   font=self._isk_font_big if live else self._isk_font_calc)

        timer_text = fdur(d.secs()) if (d.t0 or d.acc_sec > 0) else "00:00"
        self._cset(self.sl, text=timer_text)

        dd = d.dps(True)
        dr = d.dps(False)
        # Le PIC de session est suivi en continu : ne le relever qu'au moment du Stop
        # ne capturait que le DPS instantané de cet instant précis, et manquait donc
        # les vrais pics du combat.
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

    # ── Arrêt de session et gel de l'affichage ───────────────────────────
    # Stop GÈLE, il n'archive pas. Le joueur veut lire ses totaux tranquillement
    # après un site sans que les chiffres continuent de bouger. L'instantané
    # `_frozen` sert exactement à ça ; c'est Reset ou Next Site qui archivent.
    def _stop(self):
        if self._st == "stopped": return
        d = self.data
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            _log_exc("CharacterWindow._stop:3451")

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

        a_n, a_avg_t, a_avg_i, a_best, _, a_loot, a_per_site = self._anom_stats()
        a_cur = self._anom_paused_secs

        self._frozen = {
            "timer":    fdur(d.secs()) if (d.acc_sec > 0) else "00:00",
            "isk_text": f"{fisk(d.isk())} ISK" if d.secs() >= 60 and d.bg > 0 else "\u2014 STOPPED \u2014",
            "isk_fg":   CI if (d.secs() >= 60 and d.bg > 0) else TD,
            "isk_font": "big" if (d.secs() >= 60 and d.bg > 0) else "calc",
            # Grandeurs BRUTES et non préformatées : _update_breakdown_labels
            # choisit la notation selon la largeur disponible, et il peut
            # devoir en changer alors que la fenêtre est déjà figée (on peut
            # toujours la redimensionner après un Stop).
            "gross_v":  float(d.bg),
            "taxes_v":  float(d.bg * d.tax),
            "kills":    str(d.bc),
            "loot_v":   float(d.loot_val),
            "net_v":    float(d.bg * (1 - d.tax) + d.loot_val),
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
            "anom_run_loot": fisk(a_loot)     if a_loot > 0     else "\u2014",
            "anom_isk_site": fisk(a_per_site) if a_per_site > 0 else "\u2014",
        }

        self._st = "stopped"
        self._update_buttons()

    # ── Gestion des sessions ─────────────────────────────────────────────
    # Archive la session puis repart de zéro. Le point de bascule entre « ce que
    # je viens de faire » et « ce que je vais faire » : c'est ici qu'une ligne
    # d'historique naît, et c'est le seul moment où les totaux sont perdus.
    def _reset(self):
        d = self.data
        char_name = self.char_name
        try: tax_pct = float(self.tax_var.get())
        except:
            tax_pct = DEF_TAX
        try: d.tax = max(0, min(float(self.tax_var.get()) / 100, 1))
        except Exception:
            _log_exc("CharacterWindow._reset:3510")
        self._anom_close_current()
        if not self._session_saved:
            save_session(d, char_name, tax_pct)
            # Ce drapeau était remis à False ici, donc il n'était jamais True nulle part
            # et la garde de _quit() ne servait à rien. Rien n'était sauvegardé deux fois,
            # mais seulement parce que data.reset() ci-dessous met à zéro les totaux que
            # _quit() teste. _go() le remet à False au début de la session suivante.
            self._session_saved = True
        self.data.reset()
        # La session sauvegardée juste au-dessus fige les imports de butin : on
        # ne peut plus les défaire sans désaccorder l'historique. La pile repart
        # donc vide, comme loot_val.
        self._loot_stack.clear()
        self._refresh_undo_btn()
        self._frozen = None
        self._anom_paused_secs = 0
        if self.fh:
            self.fh.close()
            self.fh = None
        self.fp = 0
        # On conserve self.cf, le chemin du gamelog : Play doit pouvoir relancer LE
        # MÊME personnage. Fermer le descripteur suffit à forcer _go à rouvrir le
        # fichier en sautant à la fin.
        self._st = "stopped"
        self._update_buttons()

    # Même chose que Reset, mais nommé pour l'usage réel : on enchaîne les
    # anomalies et on veut une ligne d'historique PAR SITE, pas par soirée.
    # Délègue à _reset pour que les deux ne puissent jamais diverger.
    def _next_site(self):
        # Comportement identique à RESET : archiver la session puis tout remettre à
        # zéro. Délégué à _reset pour que les deux ne puissent jamais diverger.
        self._reset()

    # Ouvre la fenêtre d'historique (ou la met au premier plan)
    def _show_history(self):
        if self._hw and self._hw.w.winfo_exists():
            self._hw.w.lift()
            return
        self._hw = HistoryWindow(self.root, self, char_name=self.char_name)

    # Rattrapage au moment du Play : dans la vraie vie, on commence à ratter
    # puis on pense à lancer l'app. Sans ça, les premières minutes de gains
    # seraient perdues et l'ISK/heure démarrerait faux.
    # Le t0 de session est reculé jusqu'à la plus ancienne bounty retrouvée,
    # sinon on diviserait des gains de 15 minutes par 10 secondes de session.
    def _backfill_bounties(self):
        """Récupère les bounties des BACKFILL_MINS dernières minutes du gamelog.

        On lance rarement l'app avant de commencer à ratter : sans ce rattrapage,
        les premières minutes de gains seraient perdues et l'ISK/heure faux.
        """
        if not self.cf or not os.path.exists(self.cf):
            return
        
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=BACKFILL_MINS)
        earliest_ts = None
        bounties_found = 0
        total_isk = 0
        
        try:
            # Lecture ligne à ligne plutôt que readlines() : le gamelog d'une longue
            # session pèse plusieurs mégaoctets, qu'on ne veut pas charger d'un bloc en
            # mémoire sur le thread de l'interface.
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

                    # On ignore ce qui précède la fenêtre de rattrapage : au-delà, ces bounties
                    # appartiennent à une session antérieure.
                    if ts < cutoff:
                        continue

                    # Vérifie si la ligne est un paiement de bounty
                    m = RE_BT.search(raw)
                    if m:
                        amt = pnum(m.group(1))
                        self.data.bg += amt
                        self.data.bc += 1
                        # La machine à états des anomalies est alimentée elle aussi, à l'identique du
                        # chemin temps réel : sans ça, les kills rattrapés laisseraient le panneau
                        # des anomalies à zéro alors que des sites ont bel et bien été faits.
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
            _log_exc("CharacterWindow._backfill_bounties:3602")

    # Lecture INCRÉMENTALE : on garde la position dans le fichier et on ne lit
    # que ce qui s'y est ajouté. Un gamelog de plusieurs heures pèse des
    # mégaoctets, le relire en entier à chaque tour serait impensable.
    def _read(self):
        fh = self.fh
        if not fh: return

        # self.fp a été repositionné ailleurs (saut en fin de fichier au Play, _reset,
        # rotation du gamelog) : la ligne partielle conservée se rapporte alors à une
        # position périmée et doit être jetée.
        if self.fp != self._read_seen_fp:
            self._read_buf  = ""
            self._read_size = -1

        try:
            # Garde contre la troncature. Si le fichier a rétréci (remplacé ou tronqué sur
            # place), la position enregistrée dépasse la fin : seek() atterrit au-delà et
            # le lecteur devient définitivement sourd. On repart donc du début.
            # La comparaison porte sur la dernière TAILLE EN OCTETS observée, et non sur
            # self.fp : en mode texte, tell() renvoie un jeton opaque, pas un décalage.
            size = os.fstat(fh.fileno()).st_size
            if 0 <= self._read_size and size < self._read_size:
                self.fp = 0
                self._read_buf = ""
            self._read_size = size

            fh.seek(self.fp)
            chunk = fh.read()
            self.fp = fh.tell()
        except Exception:
            return
        self._read_seen_fp = self.fp

        if not chunk:
            return

        # On ne transmet à _parse que des lignes COMPLÈTES, et on garde le fragment de
        # fin pour la lecture suivante. C'est devenu bien plus important depuis le
        # passage au watchdog : les lectures se déclenchent à chaque vidage de tampon
        # et non plus toutes les 250 ms, donc surprendre EVE en pleine écriture est
        # désormais courant plutôt qu'exceptionnel.
        buf = self._read_buf + chunk
        cut = buf.rfind("\n")
        if cut == -1:
            self._read_buf = buf
            return
        self._read_buf = buf[cut + 1:]
        for l in buf[:cut].split("\n"):
            l = l.rstrip("\r")
            if l.strip():
                self._parse(l)

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
            # On réutilise le balayage partagé de MainUI quand il existe : sinon chaque
            # fenêtre de personnage parcourait tout l'arbre Gamelogs pour son propre
            # contrôle de rotation toutes les 5 s — N parcours complets au lieu d'un.
            mu = self._main_ui
            if mu is not None:
                latest = mu._scan_map().get(self.char_id)
            else:
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
            _log_exc("CharacterWindow._check_gamelog_rotation:3685")
        try:
            self.fh = open(latest, "r", encoding="utf-8", errors="replace")
            self.fp = 0                       # nouveau fichier de session — lire depuis le début
            self.cf = latest
            now_str = datetime.now().strftime("%H:%M:%S")
            self.data.alerts.append((now_str, "INFO", "Switched to new gamelog"))
        except Exception:
            self.fh = None

    # NOTE — le lecteur de chatlogs qui vivait ici a été retiré.
    # Il cherchait des fichiers nommés « Agent_*.txt » pour y lire les
    # conversations d'agent, mais EVE nomme ses chatlogs d'après le CANAL
    # (« Local_<date>_<heure>_<charid>.txt »), et une conversation d'agent n'est
    # pas un canal de discussion : aucun fichier de ce nom n'est donc jamais
    # écrit. Vérifié sur cette installation — plus de 17 000 chatlogs répartis
    # sur 55 noms de canaux, zéro fichier « Agent_ ».
    # Il alimentait deux choses. Les alertes WEB, qui exigeaient une balise
    # « (notify) » qu'une ligne de chat ne porte jamais — elles vivent
    # désormais dans _parse(), sur le gamelog, là où elles fonctionnent.
    # Et Data.mission_name, pour lequel EVE n'offre aucune source : le nom de
    # la mission n'est écrit dans aucun log, donc rien ne peut le récupérer.

    # Repeint chaque widget EN PLACE plutôt que de reconstruire l'interface.
    # Sur une surcouche toujours au premier plan, une reconstruction produit un
    # clignotement très visible ; et l'état (sections repliées, session en
    # cours, position) survit gratuitement puisque rien n'est détruit.
    def _apply_theme_live(self):
        """Repeint chaque widget en place — aucune reconstruction, aucun clignotement."""

        # 1. Photographier l'ANCIENNE palette AVANT de toucher aux globales : c'est
        #    elle qui permettra de reconnaître les couleurs à remplacer.
        old = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
               T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
               CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]

        # 2. Basculer les globales sur le nouveau thème
        apply_theme_colors(self._current_theme)

        # 3. Nouvelle palette, dans le même ordre
        new = [BG, BG_P, BG_H, BG_C, BG_POP, BD, BDG,
               T0, T1, TB, TD, CD, CR, CG, CI, CT, CK, CW, CM,
               CA, CP, CS, CH, C_DETACH, C_MSN, C_ALERT, C_ESCAL, C_ANOM, C_EWAR]

        # 4. Table de correspondance ancien → nouveau, limitée aux teintes qui
        #    changent vraiment : inutile de repeindre ce qui est identique.
        remap = {o.lower(): n for o, n in zip(old, new) if o.lower() != n.lower()}
        if not remap:
            return

        # 5. Parcourir chaque widget et échanger les couleurs reconnues. C'est ce
        #    parcours qui évite de reconstruire l'interface, donc de la faire clignoter.
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
                    _log_exc("CharacterWindow._apply_theme_live._walk:3739")
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
                    _log_exc("CharacterWindow._apply_theme_live:3760")

        # L'overlay DPS appartient à MainUI : on préserve son fond en couleur-clé et
        # on réapplique l'habillage de son mode (fond, contour, ✕, poignée) après le
        # parcours, sinon le repeignage le rendrait opaque.
        try:
            _mu = getattr(self, "_main_ui", None)
            ov = _mu._overlays.get(self.char_id) if _mu else None
            if ov and ov.w.winfo_exists():
                _walk(ov.w)
                ov.w.configure(bg=OVERLAY_KEY)
                ov._apply_mode()
        except Exception:
            _log_exc("CharacterWindow._apply_theme_live:3772")

        # History Toplevel (if open)
        for attr in ('_hw',):
            obj = getattr(self, attr, None)
            if obj:
                try:
                    if obj.w.winfo_exists():
                        _walk(obj.w)
                except Exception:
                    _log_exc("CharacterWindow._apply_theme_live:3782")

        # 6. Rafraîchir le style ttk et l'état des boutons : ils ne suivent pas le
        #    parcours ci-dessus, leurs couleurs vivant dans un style à part.
        self._style()
        self._update_buttons()

    # Play, qui recouvre deux cas : DÉMARRER une session (on ouvre le log en
    # sautant à la fin, pour ne pas compter l'historique du fichier, puis on
    # rattrape les 15 dernières minutes) et REPRENDRE après une pause (on
    # reprend le chrono là où il s'était arrêté).
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

    # Pause fige le CHRONO, pas la lecture. Sert aux trajets et aux ravitaillements :
    # sans elle, dix minutes de warp feraient chuter l'ISK/heure alors que rien
    # ne s'est passé. Le temps écoulé est versé dans acc_sec et t0 remis à None.
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

    # Le détachement sert à composer sa propre disposition : on sort l'ISK sur
    # un second écran, on garde les alertes près du jeu. La section est
    # RECONSTRUITE dans la fenêtre flottante par la même fonction de
    # construction, pour que les deux versions ne puissent pas diverger.
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

    # Retour à la fenêtre principale. Les labels de la version flottante sont
    # abandonnés et la section rebâtie : garder des références vers des widgets
    # détruits ferait échouer la mise à jour suivante.
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
    # EVE ne signale NI le début NI la fin d'une anomalie. Tout le découpage en
    # sites se déduit donc d'un seul signal : « il vient de se passer quelque
    # chose de combat ». Un silence de plus de anom_gap secondes est interprété
    # comme un warp vers le site suivant, et clôture le site courant.
    def _anom_combat_event(self, ts):
        d = self.data
        if d.anom_current and d.anom_last_combat:
            gap = (ts - d.anom_last_combat).total_seconds()
            if gap > self.anom_gap:
                d.anom_current["end"] = d.anom_last_combat
                d.archive_anom(d.anom_current)
                d.anom_current = None
        if d.anom_current is None:
            d.anom_current = {"start": ts, "end": None, "kills": 0, "isk": 0}
            self._anom_start_wall = time.monotonic()
        d.anom_last_combat = ts
        self._anom_last_wall = time.monotonic()

    # L'ISK est rattachée au site EN COURS, ce qui permet de comparer les sites
    # entre eux — le seul moyen de savoir lesquels valent le détour.
    def _anom_add_bounty(self, ts, amount):
        d = self.data
        if d.anom_current:
            d.anom_current["kills"] += 1
            d.anom_current["isk"]   += amount

    # Clôture manuelle, déclenchée par Next Site ou par la fin de session :
    # le joueur sait que le site est fini avant que le silence ne le prouve.
    def _anom_close_current(self):
        d = self.data
        if d.anom_current:
            d.anom_current["end"] = d.anom_last_combat or datetime.now(timezone.utc)
            d.archive_anom(d.anom_current)
            d.anom_current = None

    # Contrôle appelé à chaque tick, en plus de celui fait à l'arrivée d'un
    # événement : sans lui, un site resterait ouvert indéfiniment après le
    # DERNIER combat, puisque plus aucune ligne ne viendrait déclencher le test.
    def _anom_check_gap(self):
        d = self.data
        if d.anom_current and self._anom_last_wall:
            gap = time.monotonic() - self._anom_last_wall
            if gap > self.anom_gap:
                d.anom_current["end"] = d.anom_last_combat
                d.archive_anom(d.anom_current)
                d.anom_current = None

    # Agrégats affichés par la section : nombre de sites, temps et ISK moyens,
    # meilleur site. Le temps du site en cours est calculé à part, sur l'horloge
    # monotone, pour qu'il défile même quand aucun combat n'a lieu.
    def _anom_stats(self):
        d = self.data
        # O(1) : les totaux sont cumulés par Data.archive_anom() à la clôture de
        # chaque site, au lieu de trois parcours complets de anom_completed à chaque
        # tick — une liste qui grandit pendant toute la session.
        n = len(d.anom_completed)
        avg_time = (d.anom_total_time / n) if n else 0
        avg_isk  = (d.anom_total_isk / n) if n else 0
        best_isk = d.anom_best_isk
        cur_secs = (time.monotonic() - self._anom_start_wall) if (d.anom_current and self._anom_start_wall) else 0

        # Butin de la passe. avg_isk ci-dessus ne voit QUE les bounties : le
        # butin d'un MTU arrive en une seule cargaison pour tout un groupe de
        # sites, il est donc impossible de l'attribuer site par site. On le
        # rapporte au niveau du groupe — c'est-à-dire de la session — plutôt que
        # d'inventer une répartition.
        run_loot = d.loot_val

        # Diviseur : sites clos PLUS celui en cours. Les bounties du site en
        # cours sont DÉJÀ dans bg, donc le laisser hors du dénominateur gonflerait
        # l'ISK par site pendant toute la durée du site.
        div = n + (1 if d.anom_current else 0)
        isk_per_site = ((d.bg * (1 - d.tax) + d.loot_val) / div) if div else 0

        return n, avg_time, avg_isk, best_isk, cur_secs, run_loot, isk_per_site

# ── Réglages globaux (bouton engrenage) ──────────────────────────────
# Unique fenêtre de réglages de l'app. Tout ce qu'elle contient est PARTAGÉ par
# toute la flotte (chemin des logs, taxe, intervalle, seuil de site) sauf le
# thème, qui se retient par personnage.
# Le bouton APPLY reste grisé tant que rien n'a changé : sans ce retour, on ne
# sait pas si un réglage a été pris en compte, et l'app le réécrirait sur le
# disque à chaque ouverture de la fenêtre.
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
        tk.Entry(body, textvariable=self.pv, width=36, **ek).pack(fill="x", pady=(0, 8))

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

        # Déplacés depuis l'ancienne fenêtre de réglages « par personnage », qui était
        # inatteignable (personne n'appelait CharacterWindow._settings) : ces deux
        # réglages restaient donc figés sur leur valeur par défaut, sans aucun moyen
        # de les changer. Tous deux écrivent des clés partagées, exactement comme le
        # faisait cette fenêtre.
        r4 = tk.Frame(body, bg=BG_POP)
        r4.pack(fill="x", pady=(0, 6))
        tk.Label(r4, text="UPDATE INTERVAL (ms)", font=lf, bg=BG_POP, fg=TD).pack(side="left")
        self.iv = tk.StringVar(value=str(cfg.get("poll_ms", DEF_POLL)))
        tk.Entry(r4, textvariable=self.iv, width=8, **ek).pack(side="right")

        r5 = tk.Frame(body, bg=BG_POP)
        r5.pack(fill="x", pady=(0, 6))
        tk.Label(r5, text="SITE GAP (sec)", font=lf, bg=BG_POP, fg=TD).pack(side="left")
        self.gv = tk.StringVar(value=str(cfg.get("anom_gap", ANOM_GAP)))
        tk.Entry(r5, textvariable=self.gv, width=8, **ek).pack(side="right")

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

        # Photographie des valeurs à l'ouverture : c'est la référence qui permet de
        # savoir s'il reste quelque chose à appliquer.
        self._snap = {
            "log":   self.pv.get(),
            "alpha": self.av.get(),
            "tax":   self.tv.get(),
            "poll":  self.iv.get(),
            "gap":   self.gv.get(),
            "theme": self._theme_var.get(),
            "bgm":   self.bgm_var.get(),
        }

        ap_font = tkfont.Font(family="Consolas", size=10, weight="bold")
        self._ap = tk.Label(body, text="✔ APPLY", font=ap_font,
                            bg=BG_POP, fg=TD, padx=12)
        self._ap.pack(side="right", pady=(6, 0))
        self._ap_dirty = False

        # Trace StringVars so any keystroke updates dirty state
        for var in (self.pv, self.av, self.tv, self.iv, self.gv, self._theme_var):
            var.trace_add("write", lambda *_: self._check_dirty())

    # Comparé à l'instantané pris à l'ouverture plutôt qu'à la config : le
    # joueur peut modifier un champ puis revenir à la valeur d'origine, et dans
    # ce cas il n'y a plus rien à appliquer.
    def _check_dirty(self):
        dirty = (
            self.pv.get()          != self._snap["log"]   or
            self.av.get()          != self._snap["alpha"] or
            self.tv.get()          != self._snap["tax"]   or
            self.iv.get()          != self._snap["poll"]  or
            self.gv.get()          != self._snap["gap"]   or
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
            _log_exc("MainUISettings._save_pos:4134")

    # Les réglages sont poussés DANS LES FENÊTRES VIVANTES en plus d'être
    # écrits sur le disque : elles ont lu la config à leur construction et ne la
    # relisent jamais, donc sans cette propagation il faudrait relancer l'app.
    def _apply(self):
        mu  = self.main_ui
        cfg = mu.cfg
        cfg["log_path"]  = self.pv.get().strip()
        try:
            cfg["poll_ms"] = max(100, int(self.iv.get()))
        except Exception:
            _log_exc("MainUISettings._apply:4143")
        try:
            cfg["anom_gap"] = max(5, int(self.gv.get()))
        except Exception:
            _log_exc("MainUISettings._apply:4147")
        for win in mu._windows.values():
            win.log_path  = cfg["log_path"]
            win.poll_ms   = cfg.get("poll_ms",  DEF_POLL)
            win.anom_gap  = cfg.get("anom_gap", ANOM_GAP)
        # On redirige l'observateur vers le nouveau dossier : il surveille un chemin
        # figé à son démarrage et ne le relit jamais.
        try:
            mu._start_log_observer()
        except Exception:
            _log_exc("MainUISettings._apply:4156")

        try:
            v     = max(20, min(100, int(self.av.get())))
            alpha = v / 100
            cfg["alpha"] = alpha
            mu.root.attributes("-alpha", alpha)
            # Appliqué à la fenêtre de réglages elle-même : elle doit refléter
            # immédiatement le changement, sinon on ne voit pas l'effet de son propre geste.
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
            _log_exc("MainUISettings._apply:4183")

        try:
            tax_str = self.tv.get().strip()
            float(tax_str)   # validate
            cfg["tax"] = tax_str
            for win in mu._windows.values():
                win.tax_var.set(tax_str)
        except Exception:
            _log_exc("MainUISettings._apply:4192")

        new_theme = self._theme_var.get()
        if new_theme != cfg.get("last_theme", THEME_DEFAULT):
            # Photographier l'ancienne palette AVANT de changer les globales, une seule
            # fois pour toutes les fenêtres : les globales étant partagées, un second
            # relevé ne verrait déjà plus que le nouveau thème.
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
                        _log_exc("MainUISettings._apply._walk:4218")
                for child in widget.winfo_children():
                    _walk(child)

            if remap:
                # Fenêtre de vue d'ensemble
                _walk(mu.root)
                # Settings popup itself
                if self.w.winfo_exists():
                    _walk(self.w)
                # Chaque fenêtre de personnage, ses panneaux détachés et ses popups ouverts :
                # tout ce qui est à l'écran doit changer de thème d'un coup.
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
                    for attr in ('_hw',):
                        obj = getattr(win, attr, None)
                        if obj and obj.w.winfo_exists():
                            _walk(obj.w)
                    try:
                        win._style()
                        win._update_buttons()
                    except Exception:
                        _log_exc("MainUISettings._apply:4254")

        cfg["bg_monitor"] = self.bgm_var.get()

        save_config(cfg)

        # Reset snapshot so APPLY goes back to grayed-out
        self._snap = {
            "log":   self.pv.get(),
            "alpha": self.av.get(),
            "tax":   self.tv.get(),
            "poll":  self.iv.get(),
            "gap":   self.gv.get(),
            "theme": self._theme_var.get(),
            "bgm":   self.bgm_var.get(),
        }
        self._check_dirty()


# ── Gestionnaire de flotte ───────────────────────────────────────────
# L'app détecte tout personnage ayant un gamelog, ce qui ramène aussi les alts
# qu'on ne joue plus, les persos de test ou ceux d'un autre compte. Ce
# gestionnaire sert à choisir lesquels comptent vraiment : un personnage ignoré
# reste sur le disque mais ne consomme plus ni fenêtre ni analyse.
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

        # Bouton de rafraîchissement : un personnage peut se connecter pendant que la
        # liste est ouverte.
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

    # Reconstruit la liste à chaque ouverture : de nouveaux personnages
    # apparaissent en cours de session, dès qu'on se connecte avec eux.
    def _populate(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        mu       = self.main_ui
        cfg      = mu.cfg
        char_map = cfg.setdefault("chars", {})
        log_path = cfg.get("log_path", DEF_PATH)

        # Balayage neuf pour retrouver TOUS les personnages connus, y compris les
        # ignorés : c'est précisément ici qu'on veut pouvoir les réactiver.
        cf = scan_logs(log_path)
        if not cf:
            tk.Label(self._list_frame, text="No characters found in logs.",
                     font=self._F9, bg=BG, fg=TD).pack(padx=10, pady=6)
            return

        # Fusion des personnages trouvés dans les logs et de ceux qui ont déjà une
        # fenêtre : un pilote dont le log a été supprimé doit rester pilotable.
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

    # Bascule actif / ignoré. Activer un personnage crée sa fenêtre
    # immédiatement, sans attendre le balayage automatique : le clic doit avoir
    # un effet visible tout de suite.
    def _toggle(self, char_id: str, char_name: str, log_file: str):
        mu       = self.main_ui
        cfg      = mu.cfg
        char_map = cfg.setdefault("chars", {})
        char_map.setdefault(char_id, {})

        currently_active = char_id in mu._windows

        if currently_active:
            # Retrait de la flotte : on ferme l'overlay et la fenêtre, puis on marque le
            # personnage comme ignoré pour qu'il ne revienne pas au prochain balayage.
            ov = mu._overlays.get(char_id)
            if ov:
                try: ov.close()
                except Exception: _log_exc("FleetManager._toggle:4426")
            win = mu._windows.pop(char_id, None)
            if win and win.root.winfo_exists():
                win._quit()
            char_map[char_id]["ignored"] = True
        else:
            # Ajout à la flotte : on lève le drapeau « ignoré » et on crée la fenêtre
            # tout de suite, pour que le clic ait un effet visible.
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
            _log_exc("FleetManager._save_pos:4449")


# ── Vue d'ensemble de la flotte ──────────────────────────────────────
# ── Réveil des lecteurs sur événement fichier (watchdog) ─────────────
class _LogEventHandler(FileSystemEventHandler):
    """Réveille les lecteurs quand EVE écrit vraiment dans un log.

    Regroupe les rafales d'événements en UNE seule lecture : le client écrit
    ligne par ligne et déclencherait autrement des dizaines de lectures par
    seconde en plein combat.
    Le travail est systématiquement renvoyé sur le thread principal via
    after() — watchdog appelle ces méthodes depuis son propre thread, et Tk
    n'est pas thread-safe.
    """
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
                _log_exc("_LogEventHandler._schedule._fire:4468")
        try:
            self._pending = self._mu.root.after(300, _fire)
        except Exception:
            self._pending = None

    def on_modified(self, event):
        if not getattr(event, "is_directory", False):
            try:
                self._mu.root.after(0, self._schedule)
            except Exception:
                _log_exc("_LogEventHandler.on_modified:4479")

    def on_created(self, event):
        self.on_modified(event)


# Le hub. Il possède la racine Tk, découvre les personnages, crée et détruit
# leurs fenêtres, et surveille leur santé.
# Une racine UNIQUE pour toute l'app : chaque personnage est un Toplevel, pas
# une application séparée. C'est ce qui permet de partager une seule boucle
# d'événements, un seul observateur de fichiers et une seule lecture du
# presse-papiers, au lieu de les multiplier par le nombre de pilotes.
class MainUI:

    MAIN_W    = 420   # largeur par défaut ET minimale
    # Largeurs fixes des colonnes ; seule la colonne du nom s'étire, parce que
    # c'est la seule dont la longueur varie d'un joueur à l'autre.
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
        self._clip_job        = None   # after() id for _poll_clipboard
        self._clip_btn        = None   # glyphe de verrou dans l'en-tête (créé par _build)

        self._scan_job       = None
        self._scan_map_cache = None   # shared scan_logs() result (see _scan_map)
        self._scan_map_ts    = 0.0
        self._is_collapsed   = False
        self._full_height    = 0
        self._dragging       = False
        self._tray_icon      = None
        self._log_observer   = None   # watchdog Observer (None ⇒ pure timer polling)

        self._build()
        self._restore_geometry()

        # Restauration de l'état replié si la vue d'ensemble a été fermée ainsi.
        # _restore_geometry() a déjà posé la bonne géométrie (position et hauteur
        # repliée). Il ne faut SURTOUT PAS appeler winfo_* ici : la fenêtre est encore
        # masquée et ne renvoie que des valeurs sans signification.
        mui = self.cfg.get("main_ui", {})
        full_h = mui.get("full_height", 0)
        if mui.get("collapsed", False) and full_h > 32:
            self._full_height = full_h
            self._body.pack_forget()
            self._is_collapsed = True

        self._scan()
        self._health_check()
        self._auto_scan()
        self._poll_clipboard()
        self._start_log_observer()

        if _TRAY_OK:
            self.root.after(500, self._init_tray_icon)

        self.root.deiconify()
        self.root.mainloop()

    # ── Détection des personnages ────────────────────────────────────────
    # Résultat de scan_logs() partagé par toutes les fenêtres de personnage.
    # Sans ce cache, chaque CharacterWindow parcourait l'arbre Gamelogs pour son
    # propre contrôle de rotation toutes les 5 s — N parcours complets au lieu d'un.
    def _scan_map(self, max_age=5.0):
        now = time.monotonic()
        if self._scan_map_cache is not None and (now - self._scan_map_ts) < max_age:
            return self._scan_map_cache
        try:
            self._scan_map_cache = scan_logs(self.cfg.get("log_path", DEF_PATH))
        except Exception:
            if self._scan_map_cache is None:
                self._scan_map_cache = {}
        self._scan_map_ts = now
        return self._scan_map_cache

    # Aucun écran de configuration au premier lancement : on trouve les pilotes
    # en lisant le dossier de logs. Un personnage déjà connu et non ignoré voit
    # sa fenêtre recréée ; un inconnu passe par le sélecteur, pour éviter
    # d'ouvrir d'office une fenêtre par alt jamais joué.
    def _scan(self):
        cf = self._scan_map()
        char_map = self.cfg.setdefault("chars", {})
        changed = False

        # On ne retient que les personnages VRAIMENT nouveaux, absents de la config :
        # les autres ont déjà été acceptés ou refusés une fois, et redemander serait
        # pénible à chaque lancement.
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

    # ── Sélecteur de nouveaux personnages ────────────────────────────────
    # Demandé UNE SEULE FOIS par personnage : le refus est mémorisé sous forme
    # de drapeau « ignoré », sinon la même question reviendrait à chaque
    # lancement pour des alts qu'on ne joue pas.
    def _show_char_picker(self, new_chars: dict) -> set:
        """Boîte modale de choix des nouveaux personnages.

        Modale à dessein : la réponse conditionne la création des fenêtres, et
        le refus est mémorisé pour ne pas reposer la question à chaque lancement.
        """
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

        # Centrée sur la fenêtre appelante : une popup qui s'ouvrirait ailleurs sur un
        # écran large passerait inaperçue.
        self.root.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()  // 2
        ry = self.root.winfo_y() + self.root.winfo_height() // 2
        dlg.update_idletasks()
        dlg.geometry(f"+{rx - dlg.winfo_width()//2}+{ry - dlg.winfo_height()//2}")

        dlg.wait_window()   # blocks until _confirm() or window closed

        return {cid for cid, v in vars_.items() if v.get()}

    # ── Balayage périodique ──────────────────────────────────────────────
    # On se connecte souvent avec un autre personnage APRÈS avoir lancé l'app :
    # le balayage évite d'avoir à la redémarrer ou à chercher un bouton.
    def _auto_scan(self):
        self._scan()
        self._scan_job = self.root.after(10_000, self._auto_scan)

    # ── Surveillance des logs par événement ──────────────────────────────
    def _start_log_observer(self):
        """Watch the gamelog dir so reads fire on real I/O.
        No-op (pure polling) when the watchdog package isn't installed."""
        obs = getattr(self, "_log_observer", None)
        if obs is not None:
            try:
                obs.stop(); obs.join(timeout=2.0)
            except Exception:
                _log_exc("MainUI._start_log_observer:4690")
            self._log_observer = None
        if not _WATCHDOG_OK:
            return
        try:
            handler = _LogEventHandler(self)
            obs = Observer()
            seen = set()
            for d in (self.cfg.get("log_path", DEF_PATH),):
                if d and os.path.isdir(d) and os.path.normcase(d) not in seen:
                    obs.schedule(handler, d, recursive=False)
                    seen.add(os.path.normcase(d))
            obs.start()
            self._log_observer = obs
        except Exception:
            self._log_observer = None

    # Un seul observateur pour toute la flotte, qui réveille chaque lecteur.
    # Le faire par personnage multiplierait les surveillances du même dossier.
    def _wake_readers(self):
        """Un fichier a bougé : chaque fenêtre vivante relit sa portion de log."""
        for win in list(self._windows.values()):
            try:
                if win.root.winfo_exists():
                    win._read_logs_once()
            except Exception:
                _log_exc("MainUI._wake_readers:4714")

    # ── Construction de la vue d'ensemble ────────────────────────────────
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

        # Verrou de presse-papiers. Le glyphe CHANGE en plus de la couleur : une
        # simple nuance de rouge se rate d'un coup d'oeil, et le prix d'un
        # verrou oublié est une soirée de butin non comptée.
        self._clip_btn = tk.Label(hdr, text="▤", font=F11B,
                                  bg=BG_H, fg=CI, padx=5, cursor="hand2")
        self._clip_btn.pack(side="right", fill="y")
        self._clip_btn.bind("<Button-1>", lambda e: self._set_clip_lock(not _CLIP_LOCK))
        DynamicTooltip(
            self._clip_btn,
            lambda: ("Clipboard LOCKED - loot copies ignored (click to resume)"
                     if _CLIP_LOCK else
                     "Clipboard live - click to lock before copying a fit or appraisal"))
        # Aligné sur l'état réel plutôt que laissé sur les valeurs de
        # construction : celles-ci supposent le verrou ouvert, ce qui est vrai au
        # démarrage normal mais ferait mentir le glyphe dès que l'en-tête est
        # reconstruit ou le verrou armé avant l'affichage. Le bouton CLIP des
        # fenêtres de personnage fait déjà pareil.
        self._refresh_clip_btn()

        tk.Frame(self.root, bg=BDG, height=1).pack(fill="x")

        # Poignée empaquetée en bas AVANT le corps extensible : dans l'autre ordre, le
        # corps prend toute la place et la poignée disparaît.
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

        # ── Treeview accordé au thème sombre d'EVE ──
        st = ttk.Style()
        st.theme_use("clam")
        # On ne retire QUE l'enveloppe de bordure extérieure. Conserver
        # Treeview.treearea (via Treeview.padding) préserve le rendu des couleurs de
        # tag, tandis que supprimer Treeview.border fait disparaître l'anneau blanc de
        # surbrillance qui jurait avec le thème sombre.
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

        # En-têtes et cellules tous centrés, sauf CHARACTER aligné à gauche : chaque
        # en-tête se retrouve ainsi centré au-dessus de sa valeur. Centre sur centre
        # s'aligne par construction et contourne le décalage de marge droite que ttk
        # applique différemment aux en-têtes et aux cellules.
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

        # Largeurs de colonnes personnalisées, restaurées d'une session à l'autre :
        # les redimensionner à chaque lancement serait vite lassant.
        self._restore_col_widths()

        # ★ verte = fenêtre visible, ★ orange = fenêtre masquée. La couleur suffit à
        # lire l'état sans ajouter de colonne.
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

    # ── Lignes du tableau ────────────────────────────────────────────────
    # Reconstruction complète des lignes, réservée aux changements de COMPOSITION
    # de la flotte (arrivée ou départ d'un pilote). Les valeurs, elles, sont
    # mises à jour cellule par cellule par _tv_set — reconstruire le tableau
    # quatre fois par seconde le ferait scintiller et perdrait la sélection.
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

    # ── Accès au tableau ─────────────────────────────────────────────────
    # Écrit une cellule seulement si sa valeur change : le contrôle de santé
    # passe sur toutes les lignes deux fois par seconde, et réécrire des valeurs
    # identiques ferait travailler Tk pour rien.
    def _tv_set(self, iid: str, col: str, value: str):
        """N'écrit une cellule que si sa valeur change vraiment.

        Le contrôle de santé parcourt toutes les lignes deux fois par seconde ;
        réécrire des valeurs identiques ferait travailler Tk pour rien.
        """
        key = (iid, col)
        if self._tv_cache.get(key) == value:
            return
        self._tv_cache[key] = value
        self._tree.set(iid, col, value)

    # L'état du pilote passe par la COULEUR de la ligne : on doit pouvoir lire
    # d'un coup d'œil qui ratte, qui est en pause et qui est masqué, sans
    # déchiffrer une colonne de texte.
    def _tv_tag(self, iid: str, state: str, visible: bool):
        """Colore la ligne selon la visibilité de la fenêtre.

        Le paramètre `state` est accepté mais pas encore exploité : il est prévu
        pour distinguer un jour actif / pause / arrêté par la couleur.
        """
        tag = "vis" if visible else "hid"
        key = (iid, "__tag__")
        if self._tv_cache.get(key) == tag:
            return
        self._tv_cache[key] = tag
        self._tree.item(iid, tags=(tag,))

    # Le Treeview ne dit pas quelle colonne a été cliquée : il faut la retrouver
    # à partir de l'abscisse. Nécessaire parce que la cellule DPS a son propre
    # comportement, distinct du reste de la ligne.
    def _tv_col_name(self, event):
        """Nom logique de la colonne sous le curseur, ou None.

        Le Treeview ne le dit pas : il faut le déduire de l'abscisse du clic.
        Nécessaire parce que la cellule DPS a son propre comportement.
        """
        try:
            cols = self._tree["columns"]
            cid = self._tree.identify_column(event.x)   # like "#5"
            idx = int(cid[1:]) - 1
            if 0 <= idx < len(cols):
                return cols[idx]
        except Exception:
            _log_exc("MainUI._tv_col_name:4934")
        return None

    def _on_row_click(self, event):
        """Clic gauche sur la cellule DPS → ouvre ou ferme l'overlay du personnage ;
        sur toute autre cellule → affiche ou masque sa fenêtre de tableau de bord.
        """
        iid = self._tree.identify_row(event.y)
        if not iid or self._tree.identify_region(event.x, event.y) != "cell":
            return
        if self._tv_col_name(event) == "dps":
            self._toggle_overlay(iid)
        else:
            self._toggle_window(iid)

    def _on_row_right(self, event):
        """Clic droit sur la cellule DPS → menu contextuel de l'overlay
        (ouvrir / repositionner / changer de vue / fermer).

        Une fois posé, l'overlay est traversant à la souris : ce menu est le
        SEUL moyen de le repiloter.
        """
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

    # ── Gestion des overlays DPS ─────────────────────────────────────────
    # L'overlay s'ouvre et se ferme depuis la cellule DPS de la vue d'ensemble :
    # une fois posé, il devient traversant à la souris, donc il ne peut PAS
    # offrir lui-même de quoi le refermer.
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
        """Rouvre l'overlay si la config du personnage indique qu'il l'était.

        Idempotent : appelé à plusieurs moments du démarrage, il ne doit jamais
        créer un second overlay pour le même pilote.
        """
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

    # Le glyphe de la cellule DPS reflète l'état réel de l'overlay : posé,
    # transparent, il est parfois invisible à l'écran, et c'est alors le seul
    # indice qu'il est toujours ouvert.
    def _reflect_overlay_state(self, char_id):
        """Met à jour le glyphe DPS de la ligne : ○ fermé, ◉ posé, ✜ déplaçable.

        Posé, l'overlay est transparent et parfois invisible à l'écran : ce
        glyphe est alors le seul indice qu'il est toujours ouvert.
        """
        if char_id not in self._rows:
            return
        ov = self._overlays.get(char_id)
        glyph = "○"
        if ov and getattr(ov, "w", None) is not None:
            try:
                if ov.w.winfo_exists():
                    glyph = "◉" if ov.locked else "✜"
            except Exception:
                _log_exc("MainUI._reflect_overlay_state:5020")
        try:
            self._tv_set(char_id, "dps", glyph)
        except Exception:
            _log_exc("MainUI._reflect_overlay_state:5024")

    def _on_row_motion(self, event):
        """Curseur main au survol d'une ligne : rien d'autre n'indique qu'elle est
        cliquable."""
        region = self._tree.identify_region(event.x, event.y)
        self._tree.configure(cursor="hand2" if region == "cell" else "")

    def _resize_char_col(self):
        """Étire la colonne CHARACTER sur toute la place laissée par les colonnes fixes.

        Calculé sur leur largeur COURANTE et non sur les valeurs par défaut, pour
        respecter les colonnes que l'utilisateur a lui-même redimensionnées.
        """
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
        """Réapplique les largeurs de colonnes enregistrées, s'il y en a."""
        saved = self.cfg.get("main_ui", {}).get("col_widths", {})
        if not saved or not self._tree:
            return
        for col in ("net", "isk_hr", "session", "dps"):
            w = saved.get(col)
            if isinstance(w, int) and w >= 20:
                try:
                    self._tree.column(col, width=w)
                except Exception:
                    _log_exc("MainUI._restore_col_widths:5056")

    def _save_col_widths(self, event=None):
        """Enregistre les largeurs après un glissé de séparateur d'en-tête.

        N'écrit la config que si une largeur a réellement changé : l'événement
        se déclenche aussi à des moments où rien n'a bougé.
        """
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
            _log_exc("MainUI._save_col_widths:5071")

    # ── Verrou de presse-papiers ─────────────────────────────────────────
    # Propriétaire de l'état partagé : la MainUI possède le drapeau global, son
    # propre glyphe et les boutons CLIP de chaque fenêtre de personnage. Tous
    # affichent LE MÊME état, donc un seul point d'entrée les rafraîchit.
    def _set_clip_lock(self, on):
        global _CLIP_LOCK
        on = bool(on)
        if on == _CLIP_LOCK:
            return

        # Déverrouillage : le texte qui a JUSTIFIÉ le verrou est toujours dans le
        # presse-papiers. _last_clipboard ne le contient pas, puisqu'on n'a rien
        # lu pendant le verrou — sans cet instantané, le tout premier tour après
        # la reprise l'avalerait comme du butin et le verrou n'aurait servi à
        # rien. C'est le détail qui porte toute la fonctionnalité.
        if not on and _CLIP_OK:
            try:
                self._last_clipboard = pyperclip.paste() or ""
            except Exception:
                # Lecture impossible : on laisse le traqueur tel quel plutôt que
                # de l'effacer, ce qui serait le pire des deux mondes.
                _log_exc("MainUI._set_clip_lock:5820")

        _CLIP_LOCK = on
        self._refresh_clip_btn()
        for win in list(self._windows.values()):
            try:
                win._refresh_clip_btn()
            except Exception:
                _log_exc("MainUI._set_clip_lock:5828")

    def _refresh_clip_btn(self):
        """Aligne le glyphe d'en-tête sur l'état du verrou."""
        if not self._clip_btn:
            return
        try:
            if _CLIP_LOCK:
                self._clip_btn.config(text="⊘", fg=CS)
            else:
                self._clip_btn.config(text="▤", fg=CI)
        except Exception:
            _log_exc("MainUI._refresh_clip_btn:5840")

    # ── Presse-papiers : une lecture pour toute la flotte ────────────────
    def _poll_clipboard(self):
        """Read the Windows clipboard ONCE per tick and offer it to the fleet.

        Each CharacterWindow used to call pyperclip.paste() from its own _tick,
        so N characters meant N clipboard opens every poll interval — all on the
        Tk thread, and each one takes the global clipboard lock, contending with
        every other app trying to copy. The dedupe tracker (_last_clipboard) was
        already shared here; now the read itself is too.
        """
        # Verrou armé : on ne lit MÊME PAS le presse-papiers. Sauter la lecture
        # plutôt que le seul ajout évite en prime de prendre le verrou global
        # Windows à chaque tour, donc de gêner la copie que le joueur est
        # précisément en train de faire.
        if _CLIP_OK and self._windows and not _CLIP_LOCK:
            try:
                content = pyperclip.paste()
            except Exception:
                content = None
            if content and "\t" in content and content != self._last_clipboard:
                # Proposé à la première fenêtre éligible. Si aucune ne le prend (aucune en
                # cours, ou la seule candidate est déjà occupée), _last_clipboard reste
                # inchangé et le collage sera repris à un tour suivant.
                for win in list(self._windows.values()):
                    try:
                        if win._accept_clipboard(content):
                            self._last_clipboard = content
                            break
                    except Exception:
                        _log_exc("MainUI._poll_clipboard:5098")
        # poll_ms est relu à chaque tour : la fenêtre de réglages l'écrit directement
        # dans le dictionnaire de config partagé, donc une valeur mise en cache à la
        # construction deviendrait périmée.
        try:
            delay = max(100, int(self.cfg.get("poll_ms", DEF_POLL)))
        except Exception:
            delay = DEF_POLL
        self._clip_job = self.root.after(delay, self._poll_clipboard)

    # ── Totaux de flotte et détection de blocage ─────────────────────────
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

    # Deux rôles à la fois : agréger les totaux de flotte et SURVEILLER chaque
    # fenêtre. Une fenêtre dont la boucle s'est arrêtée continuerait d'afficher
    # ses derniers chiffres, indiscernables de chiffres à jour — d'où la
    # comparaison d'horodatage qui bascule la ligne en « NO TICK ».
    # Les totaux ne s'affichent qu'à partir de deux pilotes actifs : à un seul,
    # ils répéteraient sa propre ligne.
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

            # Suspendu (masqué et surveillance de fond éteinte) : on affiche le dernier
            # gain connu et on marque la ligne hors ligne, pour ne pas laisser croire que
            # des chiffres figés sont à jour.
            if suspended:
                d       = win.data
                net_tot = d.bg * (1 - d.tax) + d.loot_val
                self._tv_tag(char_id, "standby", False)   # orange — offline
                self._tv_set(char_id, "net",     fisk(net_tot) if net_tot > 0 else "-")
                self._tv_set(char_id, "isk_hr",  "— OFFLINE —")
                self._tv_set(char_id, "session", fdur(d.acc_sec) if d.acc_sec > 0 else "00:00:00")
                continue

            # Masqué mais toujours surveillé : on poursuit vers l'affichage des données en
            # direct. vis=False suffit à faire choisir le style atténué par _tv_tag.

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

    # ── Affichage d'une fenêtre de personnage ────────────────────────────
    # Masquer une fenêtre ne l'arrête pas forcément : avec la surveillance en
    # arrière-plan, ou tant qu'un overlay DPS est ouvert, l'analyse continue.
    # Sinon le personnage est SUSPENDU, ce qui économise sa lecture de log —
    # c'est le seul moyen de garder l'app légère avec beaucoup de pilotes.
    def _toggle_window(self, char_id: str):
        win = self._windows.get(char_id)
        if not win or not win.root.winfo_exists():
            return
        char_cfg = self.cfg.setdefault("chars", {}).setdefault(char_id, {})

        bg_monitor = self.cfg.get("bg_monitor", False)

        if win.root.winfo_viewable():
            # MASQUER : on retire la fenêtre principale et tous les panneaux détachés, en
            # gardant les widgets VIVANTS — _tick continue de les mettre à jour, donc
            # réafficher est instantané et rien n'est perdu.
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
                        _log_exc("MainUI._toggle_window:5219")
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
            # AFFICHER : on restaure la fenêtre et uniquement les panneaux qui étaient
            # visibles avant le masquage, pas tous.
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
                            _log_exc("MainUI._toggle_window:5246")
            win._hidden_detached = []
            char_cfg["show"] = True
            win._suspended = False         # resume log reading
            if char_id in self._rows:
                self._tv_cache.pop((char_id, "__tag__"), None)
                self._tv_tag(char_id, "standby", True)
        
        save_config(self.cfg)

    # ── Rappel de fermeture d'une fenêtre ────────────────────────────────
    # Une fenêtre qui se ferme elle-même doit le SIGNALER : sans ça, le hub
    # garderait une référence morte et continuerait de l'interroger.
    def _on_char_closed(self, char_id: str):
        self._windows.pop(char_id, None)
        self._rows.pop(char_id, None)
        if self.root.winfo_exists() and self._tree:
            try:
                self._tree.delete(char_id)
            except Exception:
                _log_exc("MainUI._on_char_closed:5264")
            # purge les entrées de cache de ce personnage, sinon elles s'accumuleraient
            # pour des fenêtres qui n'existent plus
            for k in [k for k in self._tv_cache if k[0] == char_id]:
                del self._tv_cache[k]

    # ── Poignée de redimensionnement ─────────────────────────────────────
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

    # Repli sur la barre de titre, comme pour les fenêtres de personnage : la
    # vue d'ensemble reste accessible sans occuper l'écran pendant le jeu.
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

    # ── Réglages ─────────────────────────────────────────────────────────
    def _settings(self):
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.lift()
            return
        self._settings_win = MainUISettings(self.root, self).w

    # ── Gestionnaire de flotte ───────────────────────────────────────────
    def _fleet_manager(self):
        if self._fleet_mgr_win and self._fleet_mgr_win.winfo_exists():
            self._fleet_mgr_win.lift()
            return
        self._fleet_mgr_win = FleetManager(self.root, self).w

    # ── Géométrie de la fenêtre ──────────────────────────────────────────
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
            _log_exc("MainUI._save_pos:5352")

    # La largeur est bornée au minimum : une géométrie enregistrée par une
    # version antérieure, ou tronquée, rendrait les colonnes illisibles.
    def _restore_geometry(self):
        saved = self.cfg.get("main_ui", {}).get("geometry", "")
        if saved:
            self.root.geometry(saved)
        else:
            self.root.geometry(f"{self.MAIN_W}x300+10+80")

    # ── Zone de notification (une icône pour toute l'app) ────────────────
    # UNE icône pour l'app entière, pas une par personnage : cinq pilotes
    # rempliraient la zone de notification. Optionnelle — sans pystray, on perd
    # seulement la possibilité de réduire dans la barre.
    # pystray tourne sur son propre thread, donc ses actions doivent repasser
    # par la boucle Tk plutôt que toucher les widgets directement.
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

    # Restaure la vue d'ensemble ET les fenêtres qui étaient visibles avant la
    # réduction : rétablir tout le monde ferait réapparaître des pilotes que le
    # joueur avait délibérément masqués.
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
                _log_exc("MainUI._tray_restore:5407")

    def _tray_exit(self, icon=None, item=None):
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                _log_exc("MainUI._tray_exit:5414")
        self.root.after(0, self._quit)

    # ── Fermeture de l'application ───────────────────────────────────────
    # Fermeture ordonnée, et l'ORDRE compte : on annule d'abord les boucles,
    # puis on arrête l'observateur de fichiers et l'icône (qui vivent sur
    # d'autres threads), et seulement ensuite on détruit les fenêtres — chacune
    # archivant sa session au passage. Détruire d'abord ferait se déclencher les
    # boucles sur des widgets disparus.
    def _quit(self):
        if self._health_job:
            self.root.after_cancel(self._health_job)
            self._health_job = None
        if self._scan_job:
            self.root.after_cancel(self._scan_job)
            self._scan_job = None
        if self._clip_job:
            self.root.after_cancel(self._clip_job)
            self._clip_job = None
        obs = getattr(self, "_log_observer", None)
        if obs is not None:
            try:
                obs.stop(); obs.join(timeout=2.0)
            except Exception:
                _log_exc("MainUI._quit:5433")
            self._log_observer = None
        self._save_pos()
        if self._tray_icon:
            try:
                self._tray_icon.stop()
            except Exception:
                _log_exc("MainUI._quit:5440")
        for ov in list(self._overlays.values()):
            try:
                ov.close()
            except Exception:
                _log_exc("MainUI._quit:5445")
        for win in list(self._windows.values()):
            try:
                win._quit()
            except Exception:
                _log_exc("MainUI._quit:5450")
        if self.root.winfo_exists():
            self.root.destroy()


if __name__ == "__main__":
    MainUI()