"""
Lolalytics data scraper.

Pulls ranked Solo/Duo data from the JSON API that the lolalytics.com front end
itself uses (https://a1.lolalytics.com/mega/) and writes:

  data/stats.json     Tier list per lane: tier, rank, lane share, win / pick /
                      ban rate, pick-ban influence and games for every champion.
  data/matchups.json  Per champion, for every lane they really play: lane stats,
                      damage split, matchups against every enemy champion in
                      every lane ("vs") and synergy with every ally champion in
                      every lane ("with").

Endpoints used:
  ep=front       available patches and sample sizes
  ep=list        one lane's tier list
  ep=build-full  one champion in one lane (header stats + enemy matchup table)
  ep=build-team  one champion in one lane (ally synergy table)

Usage:
    python scrape_lolalytics.py                    # tier list + matchups
    python scrape_lolalytics.py --stats            # tier list only (5 requests)
    python scrape_lolalytics.py --matchups         # matchups + synergy only
    python scrape_lolalytics.py --champion Ahri    # one champion's matchups
    python scrape_lolalytics.py --patch 16.17      # a specific patch (default: auto)
    python scrape_lolalytics.py --tier platinum_plus
    python scrape_lolalytics.py --force            # re-fetch data that already exists
"""

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import requests

from ddragon import get_champion_id_to_name, get_latest_version

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
MATCHUPS_FILE = os.path.join(DATA_DIR, "matchups.json")

API_URL = "https://a1.lolalytics.com/mega/"
LANES = ["top", "jungle", "middle", "bottom", "support"]
DEFAULT_TIER = "emerald_plus"

# Lolalytics' numeric tiers; 0 means too few games to rank.
TIER_LETTERS = {
    0: "", 1: "S+", 2: "S", 3: "S-", 4: "A+", 5: "A", 6: "A-",
    7: "B+", 8: "B", 9: "B-", 10: "C+", 11: "C", 12: "C-",
    13: "D+", 14: "D", 15: "D-",
}

MIN_LANE_SHARE = 5.0   # fetch matchups for lanes holding >= this % of a champion's games
MIN_LANE_GAMES = 500   # ...and at least this many games there (main lane always fetched)
MIN_ROW_GAMES = 50     # matchup / synergy rows with fewer games are pure noise

DEFAULT_WORKERS = 3
DEFAULT_DELAY = 0.4    # seconds each worker waits between requests
SAVE_EVERY = 25

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://lolalytics.com/",
    "Origin": "https://lolalytics.com",
}

_local = threading.local()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers.update(HEADERS)
    return _local.session


def api_get(ep: str, **params) -> dict | None:
    """GET one mega-API endpoint. Returns the decoded JSON object or None."""
    query = {"ep": ep, "v": 1, **params, "queue": "ranked", "region": "all"}
    error = ""
    for attempt in range(4):
        try:
            resp = _session().get(API_URL, params=query, timeout=25)
        except requests.RequestException as e:
            error = str(e)
        else:
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    return None  # the API answers bad queries with a plain-text error
                return data if isinstance(data, dict) else None
            if resp.status_code not in (429, 500, 502, 503, 504):
                return None
            error = f"HTTP {resp.status_code}"
        time.sleep(2.0 * (attempt + 1))
    print(f"  giving up on {ep} {params}: {error}")
    return None


def get_lolalytics_slug(champ_name: str) -> str:
    """Champion display name -> Lolalytics URL slug ("Kai'Sa" -> "kaisa")."""
    slug = champ_name.lower()
    if slug.startswith("nunu"):
        return "nunu"
    if slug.startswith("renata"):
        return "renata"
    return slug.replace("'", "").replace(".", "").replace("&", "").replace(" ", "")


def resolve_patch(requested: str, tier: str) -> str:
    """
    "auto" -> the newest patch, unless it is only a day or two old and still has
    far fewer games than the previous one (then the previous patch is used).
    """
    if requested and requested != "auto":
        return requested
    front = api_get("front", tier=tier) or {}
    patches = front.get("patches") or []
    if patches:
        current = (front.get("current") or {}).get("analysed") or 0
        previous = (front.get("previous") or {}).get("analysed") or 0
        if len(patches) > 1 and previous and current < 0.3 * previous:
            print(f"Patch {patches[0]} has only {current:,} champion-games so far; "
                  f"using {patches[1]} instead (override with --patch)")
            return patches[1]
        return patches[0]
    version = get_latest_version()
    return ".".join(version.split(".")[:2])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Tier list
# ---------------------------------------------------------------------------

def scrape_stats(patch: str, tier: str = DEFAULT_TIER) -> dict:
    """Tier list for all five lanes, keyed by champion display name."""
    id_to_name = get_champion_id_to_name()
    stats = {
        "_meta": {
            "source": "lolalytics.com tier list",
            "tier_bracket": tier,
            "patch": patch,
            "scraped_at": _now_iso(),
            "lane_avg_wr": {},
        },
        "champions": {},
    }
    for lane in LANES:
        print(f"Tier list: {lane} ...")
        data = api_get("list", patch=patch, lane=lane, tier=tier) or {}
        rows = data.get("cid") or {}
        if not rows:
            print("  WARNING: no data")
            continue
        if data.get("avgWr"):
            stats["_meta"]["lane_avg_wr"][lane] = float(data["avgWr"])
        if data.get("analysed"):
            stats["_meta"]["analysed"] = int(data["analysed"])
        for cid, rec in rows.items():
            name = id_to_name.get(int(cid))
            if not name or not isinstance(rec, dict):
                continue
            tier_num = int(rec.get("tier") or 0)
            entry = stats["champions"].setdefault(name, {"lanes": {}})
            entry["lanes"][lane] = {
                "tier": tier_num,
                "tier_letter": TIER_LETTERS.get(tier_num, ""),
                "rank": int(rec.get("rank") or 0),
                "pct_lane": float(rec.get("pctLane") or 0),
                "win_rate": float(rec.get("wr") or 0),
                "pick_rate": float(rec.get("pr") or 0),
                "ban_rate": float(rec.get("br") or 0),
                "pbi": float(rec.get("pbi") or 0),
                "games": int(rec.get("games") or 0),
            }
        print(f"  OK: {len(rows)} champions (lane average win rate {data.get('avgWr')}%)")
    return stats


# ---------------------------------------------------------------------------
# Matchups & synergy
# ---------------------------------------------------------------------------

def lanes_to_fetch(name: str, stats: dict) -> list[str]:
    """Lanes worth fetching matchups for: meaningful share of games, plus the main lane."""
    lanes = (stats.get("champions", {}).get(name) or {}).get("lanes", {})
    if not lanes:
        return []
    main = max(lanes, key=lambda l: lanes[l].get("pct_lane", 0))
    chosen = {l for l, s in lanes.items()
              if s.get("pct_lane", 0) >= MIN_LANE_SHARE and s.get("games", 0) >= MIN_LANE_GAMES}
    chosen.add(main)
    return [l for l in LANES if l in chosen]


def _table(header: list | None, table: dict | None, id_to_name: dict) -> dict:
    """{lane: [[id, wr, d1, d2, pr, n], ...]} -> {lane: {name: [wr, d2, n]}}"""
    cols = {k: i for i, k in enumerate(header or [])}
    if not table or not all(k in cols for k in ("id", "wr", "d2", "n")):
        return {}
    i_id, i_wr, i_d2, i_n = cols["id"], cols["wr"], cols["d2"], cols["n"]
    width = max(i_id, i_wr, i_d2, i_n) + 1
    out = {}
    for lane, rows in table.items():
        if lane not in LANES or not isinstance(rows, list):
            continue
        lane_rows = {}
        for r in rows:
            if not isinstance(r, list) or len(r) < width:
                continue
            try:
                name = id_to_name.get(int(r[i_id]))
                games = int(r[i_n] or 0)
                if not name or games < MIN_ROW_GAMES:
                    continue
                lane_rows[name] = [round(float(r[i_wr]), 2), round(float(r[i_d2]), 2), games]
            except (TypeError, ValueError):
                continue
        if lane_rows:
            out[lane] = lane_rows
    return out


def _damage_split(raw: dict | None) -> dict | None:
    raw = raw or {}
    parts = {k: max(0.0, float(raw.get(k) or 0)) for k in ("physical", "magic", "true")}
    total = sum(parts.values())
    if total <= 0:
        return None
    return {k: round(v / total, 3) for k, v in parts.items()}


def fetch_champion_lane(name: str, lane: str, patch: str, tier: str,
                        id_to_name: dict, delay: float) -> dict | None:
    slug = get_lolalytics_slug(name)
    params = {"patch": patch, "c": slug, "lane": lane, "tier": tier}
    full = api_get("build-full", **params)
    time.sleep(delay)
    if not full or not isinstance(full.get("header"), dict):
        return None
    header = full["header"]
    if header.get("lane") and header["lane"] != lane:
        return None
    team = api_get("build-team", **params) or {}
    time.sleep(delay)
    return {
        "games": int(header.get("n") or 0),
        "win_rate": float(header.get("wr") or 0),
        "damage": _damage_split(header.get("damage")),
        "vs": _table(full.get("enemy_h"), full.get("enemy"), id_to_name),
        "with": _table(team.get("team_h"), team.get("team"), id_to_name),
    }


def scrape_matchups(stats: dict, patch: str, tier: str = DEFAULT_TIER, champions=None,
                    force=False, workers=DEFAULT_WORKERS, delay=DEFAULT_DELAY) -> dict:
    """Fetch (or top up) data/matchups.json. Resumable: saves progress as it goes."""
    id_to_name = get_champion_id_to_name()
    existing = _load_json(MATCHUPS_FILE)
    meta = existing.get("_meta", {})
    if meta.get("patch") != patch or meta.get("tier_bracket") != tier:
        existing = {}  # never mix patches or brackets
    data = {
        "_meta": {
            "source": "lolalytics.com champion builds (matchups + synergy)",
            "tier_bracket": tier,
            "patch": patch,
            "row_format": ["win_rate", "delta2", "games"],
            "min_row_games": MIN_ROW_GAMES,
            "scraped_at": meta.get("scraped_at", ""),
        },
        "champions": existing.get("champions", {}),
    }

    names = champions or sorted(stats.get("champions", {}))
    tasks = []
    for name in names:
        have = data["champions"].get(name, {})
        for lane in lanes_to_fetch(name, stats):
            if force or lane not in have:
                tasks.append((name, lane))
    if not tasks:
        print("Matchups are already up to date (use --force to re-fetch).")
        return data

    print(f"Fetching matchups + synergy for {len(tasks)} champion lanes "
          f"({workers} workers, patch {patch}, {tier}) ...")
    done = failed = 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(fetch_champion_lane, name, lane, patch, tier, id_to_name, delay): (name, lane)
            for name, lane in tasks
        }
        for fut in as_completed(futures):
            name, lane = futures[fut]
            try:
                result = fut.result()
            except Exception as e:  # keep going; one bad champion shouldn't kill the run
                print(f"  {name} {lane}: ERROR {e}")
                result = None
            done += 1
            if result is None:
                failed += 1
                print(f"  [{done}/{len(tasks)}] {name} {lane}: no data")
            else:
                data["champions"].setdefault(name, {})[lane] = result
                vs_rows = sum(len(v) for v in result["vs"].values())
                with_rows = sum(len(v) for v in result["with"].values())
                print(f"  [{done}/{len(tasks)}] {name} {lane}: {result['games']:,} games, "
                      f"{vs_rows} matchups, {with_rows} synergies")
            if done % SAVE_EVERY == 0:
                data["_meta"]["scraped_at"] = _now_iso()
                _save_json(MATCHUPS_FILE, data, compact=True)

    data["_meta"]["scraped_at"] = _now_iso()
    _save_json(MATCHUPS_FILE, data, compact=True)
    mins = (time.time() - started) / 60
    print(f"Saved {MATCHUPS_FILE} ({done - failed}/{len(tasks)} lanes fetched in {mins:.1f} min)")
    return data


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_json(path, data, compact=False):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        if compact:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(description="Scrape Lolalytics tier list, matchup and synergy data")
    parser.add_argument("--stats", action="store_true", help="Only scrape the tier list (fast)")
    parser.add_argument("--matchups", action="store_true", help="Only scrape matchups + synergy")
    parser.add_argument("--champion", "-c", action="append",
                        help="Only fetch matchups for this champion (repeatable)")
    parser.add_argument("--patch", default="auto", help="Patch like 16.18, or 'auto' (default)")
    parser.add_argument("--tier", default=DEFAULT_TIER,
                        help="Rank bracket, e.g. emerald_plus (default), platinum_plus, diamond_plus, all")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--delay", "-d", type=float, default=DEFAULT_DELAY)
    parser.add_argument("--force", action="store_true", help="Re-fetch matchups that already exist")
    return parser


def run(args):
    patch = resolve_patch(args.patch, args.tier)
    print(f"Using patch {patch}, bracket {args.tier}\n")
    do_all = not (args.stats or args.matchups)

    stats = _load_json(STATS_FILE)
    stats_meta = stats.get("_meta", {})
    stale = stats_meta.get("patch") != patch or stats_meta.get("tier_bracket") != args.tier
    if do_all or args.stats or (args.matchups and stale):
        stats = scrape_stats(patch, args.tier)
        if not stats["champions"]:
            print("ERROR: tier list came back empty; keeping the old data.")
            return 1
        _save_json(STATS_FILE, stats)
        print(f"Saved tier list for {len(stats['champions'])} champions to {STATS_FILE}\n")

    if args.stats:
        return 0

    names = None
    if args.champion:
        known = {n.lower(): n for n in stats.get("champions", {})}
        names = [known.get(c.lower(), c) for c in args.champion]
    scrape_matchups(stats, patch, args.tier, champions=names, force=args.force,
                    workers=args.workers, delay=args.delay)
    return 0


def main(argv=None):
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
