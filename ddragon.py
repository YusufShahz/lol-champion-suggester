"""
Riot static data clients.

Data Dragon (ddragon.leagueoflegends.com):
    champion id <-> name mapping, icon keys, class tags, attack/magic ratings.
    Cached in data/ddragon_champions.json and refreshed automatically when a new
    patch is released.

Community Dragon (raw.communitydragon.org):
    the League client's own champion metadata -- damage type, melee/ranged and
    the playstyle ratings shown in the client (damage, durability, crowd control,
    mobility, utility). One request per champion, so it is only refreshed by the
    data update script and cached in data/cdragon_champions.json.
"""

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DETAILS_CACHE_FILE = os.path.join(DATA_DIR, "ddragon_champions.json")
CDRAGON_CACHE_FILE = os.path.join(DATA_DIR, "cdragon_champions.json")

DDRAGON = "https://ddragon.leagueoflegends.com"
CDRAGON_CHAMPION = ("https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/"
                    "global/default/v1/champions/{id}.json")

CACHE_TTL = 60 * 60 * 6  # 6 hours
RETRY_AFTER = 300        # seconds before retrying a failed download
TIMEOUT = 6
FALLBACK_VERSION = "16.18.1"

_version_cache = {"timestamp": 0.0, "version": None}
_champ_cache = {"timestamp": 0.0, "mapping": {}}
_details_cache = None
_details_lock = threading.Lock()
_details_failed = {"version": None, "at": 0.0}
_cdragon_cache = None


def _read_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _write_json(path, data):
    """Atomically replace `path`. Returns False when the file can't be written."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=os.path.basename(path) + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    except OSError as e:   # read-only folder, or the file is locked by another program
        print(f"Warning: could not write {path}: {e}")
        return False
    return True


def _load_details_cache():
    global _details_cache
    if _details_cache is None:
        _details_cache = _read_json(DETAILS_CACHE_FILE)
    return _details_cache


# ---------------------------------------------------------------------------
# Data Dragon
# ---------------------------------------------------------------------------

def get_latest_version():
    now = time.time()
    if _version_cache["version"] and now - _version_cache["timestamp"] < CACHE_TTL:
        return _version_cache["version"]
    try:
        resp = requests.get(f"{DDRAGON}/api/versions.json", timeout=TIMEOUT)
        if resp.status_code == 200:
            _version_cache["version"] = resp.json()[0]
            _version_cache["timestamp"] = now
            return _version_cache["version"]
    except (requests.RequestException, ValueError, IndexError):
        pass
    # Offline: remember the cached version so we don't retry on every call.
    version = _load_details_cache().get("version") or FALLBACK_VERSION
    _version_cache["version"] = version
    _version_cache["timestamp"] = now - CACHE_TTL + 300  # retry the network in 5 minutes
    return version


def get_champion_details():
    """
    {champion_name: {key, image, tags, info: {attack, defense, magic, difficulty}}}.
    Refreshes the local file cache when the game patch changes.
    """
    global _details_cache
    version = get_latest_version()
    with _details_lock:
        cache = _load_details_cache()
        if cache.get("version") == version and cache.get("champions"):
            return cache["champions"]
        # A new patch is often listed a few minutes before its files are published
        if _details_failed["version"] == version and time.time() - _details_failed["at"] < RETRY_AFTER:
            return cache.get("champions", {})

        champions = _fetch_champion_details(version)
        if not champions:
            _details_failed.update(version=version, at=time.time())
            return cache.get("champions", {})
        _details_cache = {"version": version, "champions": champions}
        _write_json(DETAILS_CACHE_FILE, _details_cache)
        return champions


def _fetch_champion_details(version):
    try:
        resp = requests.get(f"{DDRAGON}/cdn/{version}/data/en_US/champion.json", timeout=TIMEOUT * 2)
        if resp.status_code != 200:
            return None
        champions = {}
        for champ in resp.json()["data"].values():
            champions[champ["name"]] = {
                "key": champ["key"],             # numeric id as a string, e.g. "21"
                "image": champ["id"],            # icon file stem, e.g. "MissFortune"
                "tags": champ.get("tags", []),   # e.g. ["Mage", "Support"]
                "info": champ.get("info", {}),   # {attack, defense, magic, difficulty}
            }
        return champions
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None


def get_champion_id_to_name():
    now = time.time()
    if _champ_cache["mapping"] and now - _champ_cache["timestamp"] < CACHE_TTL:
        return _champ_cache["mapping"]
    details = get_champion_details()
    mapping = {int(d["key"]): name for name, d in details.items() if d.get("key")}
    if mapping:
        _champ_cache["mapping"] = mapping
        _champ_cache["timestamp"] = now
    return _champ_cache["mapping"]


def get_champion_icon_keys():
    """{display_name: icon_file_stem}, e.g. 'Miss Fortune' -> 'MissFortune'."""
    return {name: d["image"] for name, d in get_champion_details().items() if d.get("image")}


def classify_damage_type(name, details=None):
    """
    Rough 'AD' / 'AP' / 'Mixed' guess from Data Dragon's attack/magic ratings.
    Only a fallback: Lolalytics damage splits and Community Dragon damage types
    are far more accurate.
    """
    details = details if details is not None else get_champion_details()
    d = details.get(name)
    if not d:
        return "Mixed"
    info = d.get("info", {})
    attack, magic = info.get("attack", 0), info.get("magic", 0)
    if magic >= attack + 2:
        return "AP"
    if attack >= magic + 2:
        return "AD"
    tags = d.get("tags", [])
    if "Mage" in tags:
        return "AP"
    if "Marksman" in tags:
        return "AD"
    return "Mixed"


# ---------------------------------------------------------------------------
# Community Dragon
# ---------------------------------------------------------------------------

def get_cdragon_details(refresh=False):
    """{champion_name: {damage_type, attack_type, roles, playstyle, difficulty}} from the cache file."""
    global _cdragon_cache
    if _cdragon_cache is None or refresh:
        _cdragon_cache = _read_json(CDRAGON_CACHE_FILE).get("champions", {})
    return _cdragon_cache


def _fetch_cdragon_champion(champ_id):
    try:
        resp = requests.get(CDRAGON_CHAMPION.format(id=champ_id), timeout=TIMEOUT * 3)
        if resp.status_code != 200:
            return None
        d = resp.json()
    except (requests.RequestException, ValueError):
        return None
    tactical = d.get("tacticalInfo") or {}
    return {
        "damage_type": tactical.get("damageType", ""),   # kPhysical / kMagic / kMixed
        "attack_type": tactical.get("attackType", ""),   # melee / ranged
        "difficulty": tactical.get("difficulty"),
        "roles": d.get("roles") or [],                   # e.g. ["tank", "support"]
        "playstyle": d.get("playstyleInfo") or {},       # damage/durability/crowdControl/mobility/utility (1-3)
    }


def update_cdragon_details(workers=8):
    """Download Community Dragon metadata for every champion and cache it."""
    global _cdragon_cache
    id_to_name = get_champion_id_to_name()
    champions = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for name, info in zip(id_to_name.values(), pool.map(_fetch_cdragon_champion, id_to_name.keys())):
            if info:
                champions[name] = info
    if champions:
        _write_json(CDRAGON_CACHE_FILE, {"version": get_latest_version(), "champions": champions})
        _cdragon_cache = champions
    return champions
