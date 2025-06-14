# Basic champion data for suggestion logic
# This can be expanded with more detailed info, counters, and synergies

# Champions list is auto-generated from Data Dragon for up-to-date coverage
try:
    from ddragon import get_champion_id_to_name
    champions = sorted(set(get_champion_id_to_name().values()))
except Exception:
    # Fallback to static list if Data Dragon is unavailable
    champions = [
        "Aatrox", "Ahri", "Akali", "Alistar", "Amumu", "Anivia", "Annie", "Ashe", "Blitzcrank", "Brand", "Braum",
        "Caitlyn", "Camille", "Cassiopeia", "Cho'Gath", "Corki", "Darius", "Diana", "Draven", "Ekko", "Elise", "Evelynn",
        "Ezreal", "Fiora", "Fizz", "Galio", "Gangplank", "Garen", "Gnar", "Gragas", "Graves", "Hecarim", "Heimerdinger",
        "Illaoi", "Irelia", "Ivern", "Janna", "Jarvan IV", "Jax", "Jayce", "Jhin", "Jinx", "Kai'Sa", "Kalista", "Karma",
        "Karthus", "Kassadin", "Katarina", "Kayle", "Kayn", "Kennen", "Kha'Zix", "Kindred", "Kled", "Kog'Maw", "LeBlanc",
        "Lee Sin", "Leona", "Lillia", "Lissandra", "Lucian", "Lulu", "Lux", "Malphite", "Malzahar", "Maokai", "Master Yi",
        "Miss Fortune", "Mordekaiser", "Morgana", "Nami", "Nasus", "Nautilus", "Neeko", "Nidalee", "Nocturne", "Nunu & Willump",
        "Olaf", "Orianna", "Ornn", "Pantheon", "Poppy", "Pyke", "Qiyana", "Quinn", "Rakan", "Rammus", "Rek'Sai", "Renekton",
        "Rengar", "Riven", "Rumble", "Ryze", "Samira", "Sejuani", "Senna", "Seraphine", "Sett", "Shaco", "Shen", "Shyvana",
        "Singed", "Sion", "Sivir", "Skarner", "Sona", "Soraka", "Swain", "Sylas", "Syndra", "Tahm Kench", "Taliyah", "Talon",
        "Taric", "Teemo", "Thresh", "Tristana", "Trundle", "Tryndamere", "Twisted Fate", "Twitch", "Udyr", "Urgot", "Varus",
        "Vayne", "Veigar", "Vel'Koz", "Vi", "Viego", "Viktor", "Vladimir", "Volibear", "Warwick", "Wukong", "Xayah", "Xerath",
        "Xin Zhao", "Yasuo", "Yone", "Yorick", "Yuumi", "Zac", "Zed", "Ziggs", "Zilean", "Zoe", "Zyra"
    ]

# Auto-generated: all champions have at least empty counters/synergies, and a primary role.
# You can edit/expand these as needed!

# Roles are auto-generated from Data Dragon tags for all champions. Fallback to static mapping for ambiguous cases.
try:
    import requests
    from ddragon import get_champion_id_to_name, get_latest_version

    # Map Riot tags to LoL roles
    TAG_TO_ROLE = {
        'Support': 'Support',
        'Marksman': 'ADC',
        'Mage': 'Mid',
        'Assassin': 'Mid',
        'Fighter': 'Top',
        'Tank': 'Top',
    }
    version = get_latest_version()
    url = f'https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json'
    resp = requests.get(url)
    roles = {}
    if resp.status_code == 200:
        data = resp.json()['data']
        for champ in data.values():
            name = champ['name']
            tags = champ['tags']
            # Priority: Support > Marksman > Mage > Assassin > Fighter > Tank
            role = None
            for tag in ['Support', 'Marksman', 'Mage', 'Assassin', 'Fighter', 'Tank']:
                if tag in tags:
                    role = TAG_TO_ROLE[tag]
                    break
            if not role:
                role = 'Unknown'
            roles[name] = role
except Exception:
    # Fallback to static mapping if Data Dragon is unavailable
    roles = {
        "Aatrox": "Top", "Ahri": "Mid", "Akali": "Mid", "Alistar": "Support", "Amumu": "Jungle",
        "Anivia": "Mid", "Annie": "Mid", "Ashe": "ADC", "Blitzcrank": "Support", "Brand": "Support",
        "Braum": "Support", "Caitlyn": "ADC", "Camille": "Top", "Cassiopeia": "Mid", "Cho'Gath": "Top",
        "Corki": "Mid", "Darius": "Top", "Diana": "Jungle", "Draven": "ADC", "Ekko": "Jungle",
        "Elise": "Jungle", "Evelynn": "Jungle", "Ezreal": "ADC", "Fiora": "Top", "Fizz": "Mid",
        "Galio": "Mid", "Gangplank": "Top", "Garen": "Top", "Gnar": "Top", "Gragas": "Jungle",
        "Graves": "Jungle", "Hecarim": "Jungle", "Heimerdinger": "Support", "Illaoi": "Top", "Irelia": "Top",
        "Ivern": "Jungle", "Janna": "Support", "Jarvan IV": "Jungle", "Jax": "Top", "Jayce": "Top",
        "Jhin": "ADC", "Jinx": "ADC", "Kai'Sa": "ADC", "Kalista": "ADC", "Karma": "Support",
        "Karthus": "Jungle", "Kassadin": "Mid", "Katarina": "Mid", "Kayle": "Top", "Kayn": "Jungle",
        "Kennen": "Top", "Kha'Zix": "Jungle", "Kindred": "Jungle", "Kled": "Top", "Kog'Maw": "ADC",
        "LeBlanc": "Mid", "Lee Sin": "Jungle", "Leona": "Support", "Lillia": "Jungle", "Lissandra": "Mid",
        "Lucian": "ADC", "Lulu": "Support", "Lux": "Support", "Malphite": "Top", "Malzahar": "Mid",
        "Maokai": "Support", "Master Yi": "Jungle", "Miss Fortune": "ADC", "Mordekaiser": "Top",
        "Morgana": "Support", "Nami": "Support", "Nasus": "Top", "Nautilus": "Support", "Neeko": "Support",
        "Nidalee": "Jungle", "Nocturne": "Jungle", "Nunu & Willump": "Jungle", "Olaf": "Jungle",
        "Orianna": "Mid", "Ornn": "Top", "Pantheon": "Support", "Poppy": "Top", "Pyke": "Support",
        "Qiyana": "Mid", "Quinn": "Top", "Rakan": "Support", "Rammus": "Jungle", "Rek'Sai": "Jungle",
        "Renekton": "Top", "Rengar": "Jungle", "Riven": "Top", "Rumble": "Top", "Ryze": "Mid",
        "Samira": "ADC", "Sejuani": "Jungle", "Senna": "Support", "Seraphine": "Support", "Sett": "Top",
        "Shaco": "Jungle", "Shen": "Top", "Shyvana": "Jungle", "Singed": "Top", "Sion": "Top",
        "Sivir": "ADC", "Skarner": "Jungle", "Sona": "Support", "Soraka": "Support", "Swain": "Support",
        "Sylas": "Mid", "Syndra": "Mid", "Tahm Kench": "Support", "Taliyah": "Jungle", "Talon": "Mid",
        "Taric": "Support", "Teemo": "Top", "Thresh": "Support", "Tristana": "ADC", "Trundle": "Jungle",
        "Tryndamere": "Top", "Twisted Fate": "Mid", "Twitch": "ADC", "Udyr": "Jungle", "Urgot": "Top",
        "Varus": "ADC", "Vayne": "ADC", "Veigar": "Mid", "Vel'Koz": "Support", "Vi": "Jungle",
        "Viego": "Jungle", "Viktor": "Mid", "Vladimir": "Mid", "Volibear": "Top", "Warwick": "Jungle",
        "Wukong": "Top", "Xayah": "ADC", "Xerath": "Support", "Xin Zhao": "Jungle", "Yasuo": "Mid",
    "Yone": "Mid", "Yorick": "Top", "Yuumi": "Support", "Zac": "Jungle", "Zed": "Mid",
    "Ziggs": "Mid", "Zilean": "Support", "Zoe": "Mid", "Zyra": "Support"
}

# Fill counters and synergies with empty lists if missing
counters = {'Aatrox': [], 'Ahri': [], 'Akali': [], 'Alistar': [], 'Amumu': [], 'Anivia': [], 'Annie': [], 'Ashe': [], 'Blitzcrank': [], 'Brand': [], 'Braum': [], 'Caitlyn': [], 'Camille': [], 'Cassiopeia': [], "Cho'Gath": [], 'Corki': [], 'Darius': [], 'Diana': [], 'Draven': [], 'Ekko': [], 'Elise': [], 'Evelynn': [], 'Ezreal': [], 'Fiora': [], 'Fizz': [], 'Galio': [], 'Gangplank': [], 'Garen': [], 'Gnar': [], 'Gragas': [], 'Graves': [], 'Hecarim': [], 'Heimerdinger': [], 'Illaoi': [], 'Irelia': [], 'Ivern': [], 'Janna': [], 'Jarvan IV': [], 'Jax': [], 'Jayce': [], 'Jhin': [], 'Jinx': [], "Kai'Sa": [], 'Kalista': [], 'Karma': [], 'Karthus': [], 'Kassadin': [], 'Katarina': [], 'Kayle': [], 'Kayn': [], 'Kennen': [], "Kha'Zix": [], 'Kindred': [], 'Kled': [], "Kog'Maw": [], 'LeBlanc': [], 'Lee Sin': [], 'Leona': [], 'Lillia': [], 'Lissandra': [], 'Lucian': [], 'Lulu': [], 'Lux': [], 'Malphite': [], 'Malzahar': [], 'Maokai': [], 'Master Yi': [], 'Miss Fortune': [], 'Mordekaiser': [], 'Morgana': [], 'Nami': [], 'Nasus': [], 'Nautilus': [], 'Neeko': [], 'Nidalee': [], 'Nocturne': [], 'Nunu & Willump': [], 'Olaf': [], 'Orianna': [], 'Ornn': [], 'Pantheon': [], 'Poppy': [], 'Pyke': [], 'Qiyana': [], 'Quinn': [], 'Rakan': [], 'Rammus': [], "Rek'Sai": [], 'Renekton': [], 'Rengar': [], 'Riven': [], 'Rumble': [], 'Ryze': [], 'Samira': [], 'Sejuani': [], 'Senna': [], 'Seraphine': [], 'Sett': [], 'Shaco': [], 'Shen': [], 'Shyvana': [], 'Singed': [], 'Sion': [], 'Sivir': [], 'Skarner': [], 'Sona': [], 'Soraka': [], 'Swain': [], 'Sylas': [], 'Syndra': [], 'Tahm Kench': [], 'Taliyah': [], 'Talon': [], 'Taric': [], 'Teemo': [], 'Thresh': [], 'Tristana': [], 'Trundle': [], 'Tryndamere': [], 'Twisted Fate': [], 'Twitch': [], 'Udyr': [], 'Urgot': [], 'Varus': [], 'Vayne': [], 'Veigar': [], "Vel'Koz": [], 'Vi': [], 'Viego': [], 'Viktor': [], 'Vladimir': [], 'Volibear': [], 'Warwick': [], 'Wukong': [], 'Xayah': [], 'Xerath': [], 'Xin Zhao': [], 'Yasuo': [], 'Yone': [], 'Yorick': [], 'Yuumi': [], 'Zac': [], 'Zed': [], 'Ziggs': [], 'Zilean': [], 'Zoe': [], 'Zyra': []}
for champ in champions:
    if champ not in counters:
        counters[champ] = []

synergies = {'Aatrox': [], 'Ahri': [], 'Akali': [], 'Alistar': [], 'Amumu': [], 'Anivia': [], 'Annie': [], 'Ashe': [], 'Blitzcrank': [], 'Brand': [], 'Braum': [], 'Caitlyn': [], 'Camille': [], 'Cassiopeia': [], "Cho'Gath": [], 'Corki': [], 'Darius': [], 'Diana': [], 'Draven': [], 'Ekko': [], 'Elise': [], 'Evelynn': [], 'Ezreal': [], 'Fiora': [], 'Fizz': [], 'Galio': [], 'Gangplank': [], 'Garen': [], 'Gnar': [], 'Gragas': [], 'Graves': [], 'Hecarim': [], 'Heimerdinger': [], 'Illaoi': [], 'Irelia': [], 'Ivern': [], 'Janna': [], 'Jarvan IV': [], 'Jax': [], 'Jayce': [], 'Jhin': [], 'Jinx': [], "Kai'Sa": [], 'Kalista': [], 'Karma': [], 'Karthus': [], 'Kassadin': [], 'Katarina': [], 'Kayle': [], 'Kayn': [], 'Kennen': [], "Kha'Zix": [], 'Kindred': [], 'Kled': [], "Kog'Maw": [], 'LeBlanc': [], 'Lee Sin': [], 'Leona': [], 'Lillia': [], 'Lissandra': [], 'Lucian': [], 'Lulu': [], 'Lux': [], 'Malphite': [], 'Malzahar': [], 'Maokai': [], 'Master Yi': [], 'Miss Fortune': [], 'Mordekaiser': [], 'Morgana': [], 'Nami': [], 'Nasus': [], 'Nautilus': [], 'Neeko': [], 'Nidalee': [], 'Nocturne': [], 'Nunu & Willump': [], 'Olaf': [], 'Orianna': [], 'Ornn': [], 'Pantheon': [], 'Poppy': [], 'Pyke': [], 'Qiyana': [], 'Quinn': [], 'Rakan': [], 'Rammus': [], "Rek'Sai": [], 'Renekton': [], 'Rengar': [], 'Riven': [], 'Rumble': [], 'Ryze': [], 'Samira': [], 'Sejuani': [], 'Senna': [], 'Seraphine': [], 'Sett': [], 'Shaco': [], 'Shen': [], 'Shyvana': [], 'Singed': [], 'Sion': [], 'Sivir': [], 'Skarner': [], 'Sona': [], 'Soraka': [], 'Swain': [], 'Sylas': [], 'Syndra': [], 'Tahm Kench': [], 'Taliyah': [], 'Talon': [], 'Taric': [], 'Teemo': [], 'Thresh': [], 'Tristana': [], 'Trundle': [], 'Tryndamere': [], 'Twisted Fate': [], 'Twitch': [], 'Udyr': [], 'Urgot': [], 'Varus': [], 'Vayne': [], 'Veigar': [], "Vel'Koz": [], 'Vi': [], 'Viego': [], 'Viktor': [], 'Vladimir': [], 'Volibear': [], 'Warwick': [], 'Wukong': [], 'Xayah': [], 'Xerath': [], 'Xin Zhao': [], 'Yasuo': [], 'Yone': [], 'Yorick': [], 'Yuumi': [], 'Zac': [], 'Zed': [], 'Ziggs': [], 'Zilean': [], 'Zoe': [], 'Zyra': []}
for champ in champions:
    if champ not in synergies:
        synergies[champ] = []

