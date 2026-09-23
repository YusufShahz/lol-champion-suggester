"""
Refresh every data file the app uses.

Usage:
    py data/update_data.py               # everything (a few minutes)
    py data/update_data.py --stats       # tier list only (a few seconds)
    py data/update_data.py --matchups    # matchups + synergy only (slow, resumes where it stopped)
    py data/update_data.py --champions   # champion list + League client metadata (Data/Community Dragon)
    py data/update_data.py --roles       # re-derive the fallback role list from stats.json

Scraper options are passed through to scrape_lolalytics.py, for example:
    py data/update_data.py --matchups --force
    py data/update_data.py --patch 16.17 --tier platinum_plus

A running app picks up new files automatically; there is no need to restart it.
"""

import argparse
import json
import os
import sys

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(DATA_DIR))

import ddragon  # noqa: E402
import scrape_lolalytics  # noqa: E402

CHAMPIONS_FILE = os.path.join(DATA_DIR, "champions.json")
ROLES_FILE = os.path.join(DATA_DIR, "roles.json")
STATS_FILE = scrape_lolalytics.STATS_FILE

LANE_TO_ROLE = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "ADC",
    "support": "Support",
}

# A lane counts as one of a champion's roles when at least this share of their
# games is played there (their most-played lane always counts).
ROLE_PCT_THRESHOLD = 10.0


def _write(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_champions():
    """Champion list from Data Dragon, damage type and playstyle ratings from Community Dragon."""
    print("Updating the champion list (Data Dragon)...")
    details = ddragon.get_champion_details()
    if not details:
        print("  ERROR: could not download the champion list")
        return False
    _write(CHAMPIONS_FILE, sorted(details))
    print(f"  OK: {len(details)} champions, patch {ddragon.get_latest_version()}")

    print("Updating champion metadata (Community Dragon)...")
    meta = ddragon.update_cdragon_details()
    if not meta:
        print("  ERROR: could not download champion metadata")
        return False
    print(f"  OK: metadata for {len(meta)} champions")
    return True


def update_roles():
    """Fallback role list (used for champions missing from the tier list), derived from lane shares."""
    print("Deriving roles from the tier list...")
    if not os.path.exists(STATS_FILE):
        print("  ERROR: stats.json not found; run with --stats first")
        return False
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        stats = json.load(f)

    roles = {}
    for name, entry in stats.get("champions", {}).items():
        lanes = entry.get("lanes", {})
        if not lanes:
            continue
        real = [l for l, s in lanes.items()
                if s.get("pct_lane", 0) >= ROLE_PCT_THRESHOLD and s.get("games", 0) >= 50]
        main = max(lanes.items(), key=lambda kv: kv[1].get("pct_lane", 0))[0]
        if main not in real:
            real.append(main)
        roles[name] = [LANE_TO_ROLE[l] for l in LANE_TO_ROLE if l in real]

    _write(ROLES_FILE, roles)
    multi = sum(1 for v in roles.values() if len(v) > 1)
    print(f"  OK: roles for {len(roles)} champions ({multi} play more than one)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Refresh the app's data files. Unrecognised options go to scrape_lolalytics.py.")
    parser.add_argument("--champions", action="store_true", help="only the champion list and client metadata")
    parser.add_argument("--stats", action="store_true", help="only the tier list (fast)")
    parser.add_argument("--matchups", action="store_true", help="only matchups and synergy (slow)")
    parser.add_argument("--roles", action="store_true", help="only re-derive roles from stats.json")
    args, scraper_args = parser.parse_known_args()
    everything = not (args.champions or args.stats or args.matchups or args.roles)

    ok = True
    if everything or args.champions:
        ok &= update_champions()

    if everything or args.stats or args.matchups:
        if args.stats and not args.matchups:
            scraper_args = ["--stats", *scraper_args]
        elif args.matchups and not args.stats:
            scraper_args = ["--matchups", *scraper_args]
        print("Scraping Lolalytics...")
        ok &= scrape_lolalytics.main(scraper_args) == 0

    if everything or args.stats or args.roles:
        ok &= update_roles()

    print("\nDone." if ok else "\nFinished with errors (see above).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
