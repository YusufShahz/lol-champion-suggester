"""
Data update CLI script.
Refreshes all data files (champions, roles, counters) from their sources.

Usage:
    python data/update_data.py              # Refresh all data
    python data/update_data.py --roles      # Only refresh roles
    python data/update_data.py --champions  # Only refresh champions list
    python data/update_data.py --counters   # Only scrape counter data (slow)
"""

import json
import os
import sys
import argparse

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
CHAMPIONS_FILE = os.path.join(DATA_DIR, "champions.json")
ROLES_FILE = os.path.join(DATA_DIR, "roles.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")

TAG_TO_ROLE = {
    "Support": "Support",
    "Marksman": "ADC",
    "Mage": "Mid",
    "Assassin": "Mid",
    "Fighter": "Top",
    "Tank": "Top",
}


def update_champions():
    """Fetch champion list from Data Dragon and save to JSON."""
    import requests
    from ddragon import get_latest_version

    print("Updating champions list from Data Dragon...")
    version = get_latest_version()
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    resp = requests.get(url)

    if resp.status_code != 200:
        print(f"  ERROR: HTTP {resp.status_code}")
        return False

    data = resp.json()["data"]
    champions = sorted(set(champ["name"] for champ in data.values()))

    with open(CHAMPIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(champions, f, indent=2, ensure_ascii=False)

    print(f"  OK: Saved {len(champions)} champions to {CHAMPIONS_FILE}")
    return True


def update_roles():
    """Fetch champion roles from Data Dragon tags and save to JSON."""
    import requests
    from ddragon import get_latest_version

    print("Updating roles from Data Dragon...")
    version = get_latest_version()
    url = f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
    resp = requests.get(url)

    if resp.status_code != 200:
        print(f"  ERROR: HTTP {resp.status_code}")
        return False

    data = resp.json()["data"]
    roles = {}
    for champ in data.values():
        name = champ["name"]
        tags = champ["tags"]
        role = None
        for tag in ["Support", "Marksman", "Mage", "Assassin", "Fighter", "Tank"]:
            if tag in tags:
                role = TAG_TO_ROLE[tag]
                break
        roles[name] = role or "Unknown"

    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(roles, f, indent=2, ensure_ascii=False)

    print(f"  OK: Saved roles for {len(roles)} champions to {ROLES_FILE}")
    return True


def update_counters():
    """Run the Lolalytics scraper to refresh counter data."""
    from scrape_lolalytics import main as scrape_main
    print("Updating counter data from Lolalytics (this may take several minutes)...")
    scrape_main()


def main():
    parser = argparse.ArgumentParser(description="Update all LoL data files")
    parser.add_argument("--champions", action="store_true", help="Only update champions list")
    parser.add_argument("--roles", action="store_true", help="Only update roles")
    parser.add_argument("--counters", action="store_true", help="Only update counter data (slow)")
    args = parser.parse_args()

    # If no specific flag, update everything
    update_all = not (args.champions or args.roles or args.counters)

    if update_all or args.champions:
        update_champions()

    if update_all or args.roles:
        update_roles()

    if update_all or args.counters:
        update_counters()

    print("\nDone!")


if __name__ == "__main__":
    main()
