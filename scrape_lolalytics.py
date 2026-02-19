"""
Lolalytics Counter Data Scraper
Fetches champion counter data from Lolalytics and stores it as JSON.

Usage:
    python scrape_lolalytics.py                    # Scrape all champions
    python scrape_lolalytics.py --champion Aatrox   # Scrape a single champion
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
import argparse
from ddragon import get_champion_id_to_name


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")

REQUEST_DELAY = 2.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def get_lolalytics_slug(champ_name):
    """Convert champion display name to Lolalytics URL slug."""
    slug = champ_name.lower()
    if slug.startswith("nunu"):
        return "nunu"
    slug = slug.replace("'", "").replace(".", "").replace("&", "").replace(" ", "")
    return slug


def parse_counter_page(html_text, champion_name):
    """Parse Lolalytics counter page HTML using BeautifulSoup.
    
    Each matchup card is a div containing:
    - Champion name in a header div (class h-[20px])
    - Win rate in text-green-300 class
    - Delta1 in text-yellow-400
    - Delta2 in text-yellow-100
    - All Champs WR in text-green-500
    - Game count in text-gray-500
    - Link to /lol/{champ}/vs/{opponent}/build/
    """
    soup = BeautifulSoup(html_text, "html.parser")
    
    countered_by = []
    strong_against = []
    
    # Find all matchup cards by looking for VS links
    vs_links = soup.find_all("a", href=lambda h: h and "/vs/" in h and "/build/" in h)
    
    seen = set()
    for link in vs_links:
        # Skip non-matchup links (like the intro text links)
        container = link.parent
        if not container:
            continue
        
        # Get the full card text to parse from
        card_text = link.get_text(" ", strip=True)
        
        # Skip links that are just champion names in the intro paragraph
        if len(card_text) < 5:
            continue
        
        # Extract opponent name from the card
        # Name is in a div with class containing h-[20px]
        name_div = link.find("div", class_=lambda c: c and "h-[20px]" in c)
        if not name_div:
            continue
        
        opponent = name_div.get_text(strip=True)
        if not opponent or opponent in seen or opponent == champion_name:
            continue
        seen.add(opponent)
        
        # Extract win rate - in text-green-300 class
        wr_el = link.find("div", class_=lambda c: c and "text-green-300" in c)
        if not wr_el:
            continue
        
        wr_text = wr_el.get_text(strip=True)
        wr_match = re.search(r"([\d.]+)%", wr_text)
        if not wr_match:
            continue
        win_rate = float(wr_match.group(1))
        
        # Extract delta values
        delta1 = 0.0
        delta2 = 0.0
        
        delta1_el = link.find("span", class_=lambda c: c and "text-yellow-400" in c)
        if delta1_el:
            d1_text = delta1_el.get_text(strip=True)
            # Text is like 'Δ1-4.47' — skip 'Δ1' prefix, capture the number
            d1_match = re.search(r"Δ\d\s*([\-+]?[\d.]+)", d1_text)
            if d1_match:
                delta1 = float(d1_match.group(1))
                # Preserve negative sign: if original text has '-' before the number
                if '-' in d1_text and delta1 > 0:
                    delta1 = -delta1
        
        delta2_el = link.find("span", class_=lambda c: c and "text-yellow-100" in c)
        if delta2_el:
            d2_text = delta2_el.get_text(strip=True)
            # Text is like 'Δ2-7.88' — skip 'Δ2' prefix, capture the number
            d2_match = re.search(r"Δ\d\s*([\-+]?[\d.]+)", d2_text)
            if d2_match:
                delta2 = float(d2_match.group(1))
                if '-' in d2_text and delta2 > 0:
                    delta2 = -delta2
        
        # Extract game count
        games = 0
        games_el = link.find("div", class_=lambda c: c and "text-gray-500" in c)
        if games_el:
            g_text = games_el.get_text(strip=True)
            g_match = re.search(r"([\d,]+)", g_text)
            if g_match:
                games = int(g_match.group(1).replace(",", ""))
        
        entry = {
            "name": opponent,
            "win_rate": win_rate,
            "delta1": delta1,
            "delta2": delta2,
            "games": games
        }
        
        # Negative delta means our champion loses to this opponent (countered by)
        # Positive delta means our champion beats this opponent (strong against)
        if delta2 < 0:
            countered_by.append(entry)
        else:
            strong_against.append(entry)
    
    # Sort: countered_by by most negative delta first, strong_against by most positive
    countered_by.sort(key=lambda x: x["delta2"])
    strong_against.sort(key=lambda x: x["delta2"], reverse=True)
    
    return {
        "countered_by": countered_by[:15],
        "strong_against": strong_against[:15]
    }


def fetch_counter_data(champion_name):
    """Fetch counter data for a single champion from Lolalytics."""
    slug = get_lolalytics_slug(champion_name)
    url = f"https://lolalytics.com/lol/{slug}/counters/"
    
    print(f"  Fetching {champion_name} ({slug}) from {url}...")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"  WARNING: HTTP {resp.status_code} for {champion_name}")
            return {"countered_by": [], "strong_against": []}
        
        data = parse_counter_page(resp.text, champion_name)
        cb_count = len(data["countered_by"])
        sa_count = len(data["strong_against"])
        print(f"  OK: {champion_name}: {cb_count} counters, {sa_count} strong matchups")
        return data
        
    except requests.RequestException as e:
        print(f"  ERROR for {champion_name}: {e}")
        return {"countered_by": [], "strong_against": []}


def load_existing_data():
    """Load existing counter data if it exists."""
    if os.path.exists(COUNTERS_FILE):
        with open(COUNTERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data):
    """Save counter data to JSON file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(COUNTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved data for {len(data)} champions to {COUNTERS_FILE}")


def get_all_champion_names():
    """Get all champion names from Data Dragon."""
    mapping = get_champion_id_to_name()
    return sorted(set(mapping.values()))


def main():
    parser = argparse.ArgumentParser(description="Scrape Lolalytics counter data")
    parser.add_argument(
        "--champion", "-c",
        help="Scrape a single champion instead of all (for testing)"
    )
    parser.add_argument(
        "--delay", "-d",
        type=float,
        default=REQUEST_DELAY,
        help=f"Delay between requests in seconds (default: {REQUEST_DELAY})"
    )
    args = parser.parse_args()
    
    all_data = load_existing_data()
    
    if args.champion:
        champions = [args.champion]
    else:
        champions = get_all_champion_names()
    
    print(f"Scraping counter data for {len(champions)} champion(s)...\n")
    
    for i, champ in enumerate(champions):
        data = fetch_counter_data(champ)
        all_data[champ] = data
        
        # Save periodically in case of interruption
        if (i + 1) % 10 == 0:
            save_data(all_data)
            print(f"  [{i + 1}/{len(champions)}] Progress saved.\n")
        
        if i < len(champions) - 1:
            time.sleep(args.delay)
    
    save_data(all_data)
    
    total = len(all_data)
    with_data = sum(1 for v in all_data.values()
                    if v.get("countered_by") or v.get("strong_against"))
    print(f"\nSummary: {with_data}/{total} champions have counter data.")


if __name__ == "__main__":
    main()
