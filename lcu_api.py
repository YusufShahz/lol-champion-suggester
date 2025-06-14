import requests
import psutil
import base64
import os
import sys
import time

def get_lcu_credentials():
    """
    Finds the LeagueClientUx process and extracts port/token for LCU API auth.
    Returns (port, password) or (None, None) if not found.
    """
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if proc.info['name'] and 'LeagueClientUx.exe' in proc.info['name']:
                for arg in proc.info['cmdline']:
                    if arg.startswith('--app-port='):
                        port = arg.split('=')[1]
                    if arg.startswith('--remoting-auth-token='):
                        password = arg.split('=')[1]
                return port, password
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None, None

def lcu_request(path):
    port, password = get_lcu_credentials()
    if not port or not password:
        return None
    url = f"https://127.0.0.1:{port}{path}"
    auth = base64.b64encode(f"riot:{password}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Accept': 'application/json',
    }
    try:
        response = requests.get(url, headers=headers, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None

def get_champion_select():
    # This endpoint returns all info about current champ select
    data = lcu_request('/lol-champ-select/v1/session')
    if not data:
        return None
    # Parse ally/enemy picks
    ally_picks = []
    enemy_picks = []
    my_team = data.get('myTeam', [])
    their_team = data.get('theirTeam', [])
    # championId is 0 if not picked yet
    for slot in my_team:
        champ_id = slot.get('championId', 0)
        if champ_id:
            ally_picks.append(champ_id)
    for slot in their_team:
        champ_id = slot.get('championId', 0)
        if champ_id:
            enemy_picks.append(champ_id)
    return ally_picks, enemy_picks
