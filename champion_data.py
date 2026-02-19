"""
Champion data module.
Loads champion list, roles, counters, and synergies from JSON data files.
Data files are in data/ directory and can be refreshed with data/update_data.py.
"""

import json
import os

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load_json(filename, default=None):
    """Load a JSON file from the data directory. Returns default if missing."""
    filepath = os.path.join(_DATA_DIR, filename)
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Could not load {filepath}: {e}")
    return default if default is not None else {}


# --- Champion List ---
# Load from data/champions.json, fallback to Data Dragon API, then static list
_champions_data = _load_json("champions.json")
if _champions_data:
    champions = _champions_data
else:
    try:
        from ddragon import get_champion_id_to_name
        champions = sorted(set(get_champion_id_to_name().values()))
    except Exception:
        champions = [
            "Aatrox", "Ahri", "Akali", "Alistar", "Amumu", "Anivia", "Annie", "Ashe",
            "Blitzcrank", "Brand", "Braum", "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath",
            "Corki", "Darius", "Diana", "Draven", "Ekko", "Elise", "Evelynn", "Ezreal",
            "Fiora", "Fizz", "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves",
            "Hecarim", "Heimerdinger", "Illaoi", "Irelia", "Ivern", "Janna", "Jarvan IV",
            "Jax", "Jayce", "Jhin", "Jinx", "Kai'Sa", "Kalista", "Karma", "Karthus",
            "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred",
            "Kled", "Kog'Maw", "LeBlanc", "Lee Sin", "Leona", "Lillia", "Lissandra",
            "Lucian", "Lulu", "Lux", "Malphite", "Malzahar", "Maokai", "Master Yi",
            "Miss Fortune", "Mordekaiser", "Morgana", "Nami", "Nasus", "Nautilus", "Neeko",
            "Nidalee", "Nocturne", "Nunu & Willump", "Olaf", "Orianna", "Ornn", "Pantheon",
            "Poppy", "Pyke", "Qiyana", "Quinn", "Rakan", "Rammus", "Rek'Sai", "Renekton",
            "Rengar", "Riven", "Rumble", "Ryze", "Samira", "Sejuani", "Senna", "Seraphine",
            "Sett", "Shaco", "Shen", "Shyvana", "Singed", "Sion", "Sivir", "Skarner",
            "Sona", "Soraka", "Swain", "Sylas", "Syndra", "Tahm Kench", "Taliyah", "Talon",
            "Taric", "Teemo", "Thresh", "Tristana", "Trundle", "Tryndamere", "Twisted Fate",
            "Twitch", "Udyr", "Urgot", "Varus", "Vayne", "Veigar", "Vel'Koz", "Vi", "Viego",
            "Viktor", "Vladimir", "Volibear", "Warwick", "Wukong", "Xayah", "Xerath",
            "Xin Zhao", "Yasuo", "Yone", "Yorick", "Yuumi", "Zac", "Zed", "Ziggs",
            "Zilean", "Zoe", "Zyra"
        ]


# --- Roles ---
# Load from data/roles.json, fallback to Data Dragon API, then static mapping
_roles_data = _load_json("roles.json")
if _roles_data:
    roles = _roles_data
else:
    try:
        import requests
        from ddragon import get_latest_version
        _TAG_TO_ROLE = {
            'Support': 'Support', 'Marksman': 'ADC', 'Mage': 'Mid',
            'Assassin': 'Mid', 'Fighter': 'Top', 'Tank': 'Top',
        }
        _version = get_latest_version()
        _url = f'https://ddragon.leagueoflegends.com/cdn/{_version}/data/en_US/champion.json'
        _resp = requests.get(_url)
        roles = {}
        if _resp.status_code == 200:
            for champ in _resp.json()['data'].values():
                role = None
                for tag in ['Support', 'Marksman', 'Mage', 'Assassin', 'Fighter', 'Tank']:
                    if tag in champ['tags']:
                        role = _TAG_TO_ROLE[tag]
                        break
                roles[champ['name']] = role or 'Unknown'
    except Exception:
        roles = {
            "Aatrox": "Top", "Ahri": "Mid", "Akali": "Mid", "Alistar": "Support",
            "Amumu": "Jungle", "Anivia": "Mid", "Annie": "Mid", "Ashe": "ADC",
            "Blitzcrank": "Support", "Brand": "Support", "Braum": "Support",
            "Caitlyn": "ADC", "Darius": "Top", "Ezreal": "ADC", "Garen": "Top",
            "Jinx": "ADC", "Lee Sin": "Jungle", "Lux": "Support", "Thresh": "Support",
            "Yasuo": "Mid", "Yone": "Mid", "Zed": "Mid",
        }


# --- Counter Data (from data/counters.json, populated by scrape_lolalytics.py) ---
_counter_data = _load_json("counters.json", default={})

# Build the counters dict: {champion: [list of champions this champion is strong against]}
counters = {}
for champ in champions:
    champ_data = _counter_data.get(champ, {})
    strong_against = champ_data.get("strong_against", [])
    counters[champ] = [entry["name"] for entry in strong_against]

# Full counter data for weighted scoring
counter_details = _counter_data


# --- Synergy Data (placeholder - no reliable data source yet) ---
synergies = {champ: [] for champ in champions}
