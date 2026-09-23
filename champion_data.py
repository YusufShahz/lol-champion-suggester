"""
Champion data layer.

Loads the local data files and exposes fast lookups:

  data/stats.json              per-lane tier list: tier, win / pick / ban rate,
                               pick-ban influence, games and lane share
  data/matchups.json           per champion and lane: damage split, matchups vs
                               every enemy champion in every lane ("vs") and
                               synergy with every ally champion in every lane ("with")
  data/cdragon_champions.json  damage type, melee/ranged and playstyle ratings
  data/ddragon_champions.json  icons and class tags
  data/roles.json              fallback role list when stats are missing

Files are re-read automatically when they change on disk (see reload_if_changed),
so refreshing data does not require restarting the server.
"""

import json
import os
import time

import ddragon

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_WATCHED = ("stats.json", "matchups.json", "cdragon_champions.json", "roles.json")

ROLES = ["Top", "Jungle", "Mid", "ADC", "Support"]
LANES = ["top", "jungle", "middle", "bottom", "support"]
ROLE_TO_LANE = dict(zip(ROLES, LANES))
LANE_TO_ROLE = dict(zip(LANES, ROLES))

# A champion "plays" a lane when at least this share of their games are there.
PLAYABLE_SHARE = 8.0

_CDRAGON_DAMAGE = {
    "kPhysical": {"physical": 0.85, "magic": 0.1, "true": 0.05},
    "kMagic": {"physical": 0.1, "magic": 0.85, "true": 0.05},
    "kMixed": {"physical": 0.5, "magic": 0.45, "true": 0.05},
}
_DDRAGON_DAMAGE = {
    "AD": _CDRAGON_DAMAGE["kPhysical"],
    "AP": _CDRAGON_DAMAGE["kMagic"],
    "Mixed": _CDRAGON_DAMAGE["kMixed"],
}

# Populated by load()
champions = []
stats_meta = {}
matchups_meta = {}
champ_stats = {}
ddragon_details = {}
cdragon_details = {}
_matchups = {}
_roles_fallback = {}
_lane_avg = {}
_attr_cache = {}
_mtimes = {}
_last_check = 0.0


def _load_json(filename, default=None):
    path = os.path.join(_DATA_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: could not load {path}: {e}")
    return default if default is not None else {}


def _file_mtimes():
    out = {}
    for name in _WATCHED:
        try:
            out[name] = os.path.getmtime(os.path.join(_DATA_DIR, name))
        except OSError:
            out[name] = None
    return out


def load():
    """(Re)load every data file into module state."""
    global champions, stats_meta, matchups_meta, champ_stats, ddragon_details
    global cdragon_details, _matchups, _roles_fallback, _lane_avg, _attr_cache, _mtimes

    ddragon_details = ddragon.get_champion_details()
    cdragon_details = ddragon.get_cdragon_details(refresh=True)

    stats_file = _load_json("stats.json", {})
    stats_meta = stats_file.get("_meta", {})
    champ_stats = stats_file.get("champions", {})

    matchups_file = _load_json("matchups.json", {})
    matchups_meta = matchups_file.get("_meta", {})
    _matchups = matchups_file.get("champions", {})

    _roles_fallback = {}
    for name, val in _load_json("roles.json", {}).items():
        if isinstance(val, list):
            _roles_fallback[name] = [r for r in val if r in ROLE_TO_LANE]
        elif isinstance(val, str) and val in ROLE_TO_LANE:
            _roles_fallback[name] = [val]

    names = set(ddragon_details) | set(champ_stats)
    champions = sorted(names) if names else _load_json("champions.json", [])

    # Games-weighted lane average win rate, for stats files that don't record it
    _lane_avg = {}
    for lane in LANES:
        games = wins = 0.0
        for entry in champ_stats.values():
            s = entry.get("lanes", {}).get(lane)
            if s and s.get("games"):
                games += s["games"]
                wins += s["games"] * s.get("win_rate", 50.0)
        _lane_avg[lane] = wins / games if games else 50.0

    _attr_cache = {}
    _mtimes = _file_mtimes()


def reload_if_changed(min_interval=5.0):
    """Reload data files if any changed on disk (checked at most every min_interval s)."""
    global _last_check
    now = time.time()
    if now - _last_check < min_interval:
        return False
    _last_check = now
    if _file_mtimes() != _mtimes:
        load()
        return True
    return False


# ---------------------------------------------------------------------------
# Tier list / lanes
# ---------------------------------------------------------------------------

def lane_avg_wr(lane):
    """Average win rate in a lane for the scraped bracket (e.g. 51.7% for Emerald+)."""
    avg = (stats_meta.get("lane_avg_wr") or {}).get(lane)
    return float(avg) if avg else _lane_avg.get(lane, 50.0)


def lane_stats(name, lane):
    """Tier list stats for a champion in a lane, or None without games there."""
    s = champ_stats.get(name, {}).get("lanes", {}).get(lane)
    return s if s and s.get("games", 0) > 0 else None


def lane_shares(name):
    """{lane: % of the champion's games played there}."""
    lanes = champ_stats.get(name, {}).get("lanes", {})
    return {l: float(lanes[l].get("pct_lane", 0.0)) for l in LANES if l in lanes}


def lane_distribution(name, floor=0.0):
    """P(champion plays each lane). `floor` (in % points) keeps rare lanes possible."""
    shares = lane_shares(name)
    if not shares or sum(shares.values()) <= 0:
        fallback = [ROLE_TO_LANE[r] for r in _roles_fallback.get(name, [])]
        shares = {l: (100.0 if l in fallback else 0.0) for l in LANES} if fallback else {}
    raw = {l: shares.get(l, 0.0) + floor for l in LANES}
    total = sum(raw.values())
    if total <= 0:
        return {l: 1.0 / len(LANES) for l in LANES}
    return {l: v / total for l, v in raw.items()}


def main_lane(name):
    shares = lane_shares(name)
    if shares and max(shares.values()) > 0:
        return max(shares, key=shares.get)
    fallback = _roles_fallback.get(name)
    return ROLE_TO_LANE[fallback[0]] if fallback else None


def playable_lanes(name, min_share=PLAYABLE_SHARE):
    """Lanes the champion genuinely plays, most-played first (main lane always included)."""
    shares = lane_shares(name)
    if not shares or max(shares.values()) <= 0:
        return [ROLE_TO_LANE[r] for r in _roles_fallback.get(name, [])]
    main = max(shares, key=shares.get)
    lanes = [l for l in LANES if shares.get(l, 0) >= min_share or l == main]
    return sorted(lanes, key=lambda l: -shares.get(l, 0))


def roles_of(name):
    return [LANE_TO_ROLE[l] for l in playable_lanes(name)]


def main_role(name):
    lane = main_lane(name)
    return LANE_TO_ROLE.get(lane) if lane else None


# ---------------------------------------------------------------------------
# Matchups & synergy
# ---------------------------------------------------------------------------

def has_matchup_data():
    return bool(_matchups)


def lane_entry(name, lane):
    """Raw matchups.json entry for a champion in a lane (games, win_rate, damage, vs, with)."""
    return _matchups.get(name, {}).get(lane)


def matchup(champ, lane, opp, opp_lane):
    """
    (win_rate, delta2, games) for `champ` in `lane` against `opp` in `opp_lane`,
    read from either champion's table. None when they rarely meet.
    """
    row = _matchups.get(champ, {}).get(lane, {}).get("vs", {}).get(opp_lane, {}).get(opp)
    if row:
        return row[0], row[1], row[2]
    row = _matchups.get(opp, {}).get(opp_lane, {}).get("vs", {}).get(lane, {}).get(champ)
    if row:
        # Each table is written from its own champion's side of the bracket, so the two
        # win rates of a pair sum to about twice the bracket average, not 100.
        return round(lane_avg_wr(lane) + lane_avg_wr(opp_lane) - row[0], 2), -row[1], row[2]
    return None


def synergy(champ, lane, ally, ally_lane):
    """(win_rate_together, delta2, games) for two allies, or None."""
    row = _matchups.get(champ, {}).get(lane, {}).get("with", {}).get(ally_lane, {}).get(ally)
    if not row:
        row = _matchups.get(ally, {}).get(ally_lane, {}).get("with", {}).get(lane, {}).get(champ)
    return (row[0], row[1], row[2]) if row else None


def lane_opponents(champ, lane):
    """{opponent: [win_rate, delta2, games]} for same-lane opponents."""
    return _matchups.get(champ, {}).get(lane, {}).get("vs", {}).get(lane, {})


# ---------------------------------------------------------------------------
# Champion attributes (team composition)
# ---------------------------------------------------------------------------

def damage_profile(name, lane=None):
    """{"physical", "magic", "true"} damage fractions, measured per lane when available."""
    lanes = _matchups.get(name, {})
    entry = lanes.get(lane) if lane else None
    if not (entry and entry.get("damage")):
        shares = lane_shares(name)
        for l in sorted(lanes, key=lambda l: -shares.get(l, 0.0)):
            if lanes[l].get("damage"):
                entry = lanes[l]
                break
    if entry and entry.get("damage"):
        return dict(entry["damage"])
    dt = cdragon_details.get(name, {}).get("damage_type")
    if dt in _CDRAGON_DAMAGE:
        return dict(_CDRAGON_DAMAGE[dt])
    return dict(_DDRAGON_DAMAGE[ddragon.classify_damage_type(name, ddragon_details)])


def damage_type(name, lane=None):
    """'AD', 'AP' or 'Mixed'."""
    d = damage_profile(name, lane)
    if d["physical"] >= 0.65:
        return "AD"
    if d["magic"] >= 0.65:
        return "AP"
    return "Mixed"


def tags_of(name):
    return ddragon_details.get(name, {}).get("tags", [])


def attributes(name):
    """
    Playstyle ratings (1-3) from the League client's data, with Data Dragon class
    tags as a fallback: durability, crowd_control, mobility, damage, utility,
    plus attack_type ("melee"/"ranged"/"") and class roles.
    """
    if name in _attr_cache:
        return _attr_cache[name]
    cd = cdragon_details.get(name) or {}
    ps = cd.get("playstyle") or {}
    tags = set(tags_of(name))

    def rating(key, fallback):
        v = ps.get(key)
        return int(v) if isinstance(v, (int, float)) and v > 0 else fallback

    attrs = {
        "durability": rating("durability", 3 if "Tank" in tags else 2 if "Fighter" in tags else 1),
        "crowd_control": rating("crowdControl", 2 if tags & {"Tank", "Support", "Mage"} else 1),
        "mobility": rating("mobility", 3 if "Assassin" in tags else 2 if "Fighter" in tags else 1),
        "damage": rating("damage", 1 if tags & {"Tank", "Support"} and not tags & {"Mage", "Marksman"} else 3),
        "utility": rating("utility", 3 if "Support" in tags else 1),
        "attack_type": cd.get("attack_type") or ("ranged" if "Marksman" in tags else ""),
        "roles": cd.get("roles") or sorted(t.lower() for t in tags),
    }
    _attr_cache[name] = attrs
    return attrs


def is_frontline(name):
    a = attributes(name)
    return a["durability"] >= 3 or "tank" in a["roles"]


# ---------------------------------------------------------------------------
# Catalog for the front end
# ---------------------------------------------------------------------------

def champion_catalog():
    """Everything the UI needs to render pickers: icons, roles, lane shares, class."""
    icon_keys = ddragon.get_champion_icon_keys()
    out = []
    for name in champions:
        shares = lane_shares(name)
        attrs = attributes(name)
        out.append({
            "name": name,
            "icon": icon_keys.get(name, ""),
            "roles": roles_of(name),
            "lanes": {l: round(v, 1) for l, v in shares.items() if v >= 1.0},
            "damage": damage_type(name),
            "attack_type": attrs["attack_type"],
            "classes": attrs["roles"],
        })
    return out


load()
