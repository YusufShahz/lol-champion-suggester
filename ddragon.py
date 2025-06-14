import requests
import time

# Cache champion mapping in memory
_champ_cache = {
    'timestamp': 0,
    'mapping': {}
}

# How often to refresh cache (seconds)
CACHE_TTL = 60 * 60 * 6  # 6 hours


def get_latest_version():
    url = 'https://ddragon.leagueoflegends.com/api/versions.json'
    resp = requests.get(url)
    if resp.status_code == 200:
        return resp.json()[0]
    return '14.10.1'  # fallback to a recent version


def fetch_champion_id_to_name():
    version = get_latest_version()
    url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json'
    resp = requests.get(url)
    mapping = {}
    if resp.status_code == 200:
        data = resp.json()['data']
        for champ in data.values():
            champ_id = int(champ['key'])
            champ_display_name = champ['name']  # Use display name with apostrophes/spaces
            mapping[champ_id] = champ_display_name
    return mapping


def get_champion_id_to_name():
    now = time.time()
    if now - _champ_cache['timestamp'] > CACHE_TTL or not _champ_cache['mapping']:
        _champ_cache['mapping'] = fetch_champion_id_to_name()
        _champ_cache['timestamp'] = now
    return _champ_cache['mapping']
