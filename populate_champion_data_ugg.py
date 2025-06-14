import requests
from bs4 import BeautifulSoup
import time
import re

# Use the display names from your champion_data.py
from champion_data import champions

def normalize_name(name):
    # U.GG uses no apostrophes and sometimes no spaces, e.g. KaiSa, KhaZix, ChoGath
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()

def get_lolalytics_slug(champ_name):
    # Lolalytics uses lowercase, spaces to -, remove apostrophes
    slug = champ_name.lower().replace("'", "").replace(" ", "-")
    return slug

def extract_champ_names_from_text(text, limit=5):
    # Find all [Champion...](...) markdown links
    links = re.findall(r'\[([^\[\]]+?)\]\(https://lolalytics.com/lol/.*?/vs/([a-z0-9\-]+)/build/\)', text)
    names = []
    for link in links:
        champ = link[0]
        # Champion name is the first word/phrase before any digit or %
        champ_clean = re.split(r'[0-9%]', champ)[0].strip()
        # Remove trailing 'middle', 'top', etc. if present
        champ_clean = re.sub(r'\s+(top|middle|jungle|adc|support)$', '', champ_clean, flags=re.IGNORECASE)
        if champ_clean and champ_clean not in names:
            names.append(champ_clean)
        if len(names) >= limit:
            break
    return names

def fetch_lolalytics_data(champ_slug):
    headers = {"User-Agent": "Mozilla/5.0"}
    # Counters
    url_counters = f"https://lolalytics.com/lol/{champ_slug}/counters/"
    resp_counters = requests.get(url_counters, headers=headers)
    counters = []
    if resp_counters.status_code == 200:
        counters = extract_champ_names_from_text(resp_counters.text, limit=5)
    # Synergies
    url_synergy = f"https://lolalytics.com/lol/{champ_slug}/synergy/"
    resp_synergy = requests.get(url_synergy, headers=headers)
    synergies = []
    if resp_synergy.status_code == 200:
        synergies = extract_champ_names_from_text(resp_synergy.text, limit=5)
    return counters, synergies

def build_full_data():
    all_counters = {}
    all_synergies = {}
    for champ in champions:
        slug = get_lolalytics_slug(champ)
        print(f"Fetching {champ} ({slug}) from Lolalytics...")
        try:
            counters, synergies = fetch_lolalytics_data(slug)
            all_counters[champ] = counters[:5]
            all_synergies[champ] = synergies[:5]
        except Exception as e:
            print(f"Error for {champ}: {e}")
            all_counters[champ] = []
            all_synergies[champ] = []
        time.sleep(1.5)  # Be polite to Lolalytics
    return all_counters, all_synergies

def update_champion_data_py(counters, synergies, path="champion_data.py"):
    import re
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Replace counters dict
    content = re.sub(
        r"counters\s*=\s*\{.*?\}\n",
        f"counters = {repr(counters)}\n",
        content,
        flags=re.DOTALL
    )
    # Replace synergies dict
    content = re.sub(
        r"synergies\s*=\s*\{.*?\}\n",
        f"synergies = {repr(synergies)}\n",
        content,
        flags=re.DOTALL
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"champion_data.py updated with {len(counters)} counters and {len(synergies)} synergies.")

def main():
    all_counters, all_synergies = build_full_data()
    update_champion_data_py(all_counters, all_synergies, path="champion_data.py")

if __name__ == "__main__":
    main()
