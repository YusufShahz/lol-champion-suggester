"""
League Client Update (LCU) API integration.
Detects the League client process, authenticates, and reads champion select data.
"""

import requests
import psutil
import base64
import urllib3

# Suppress SSL warnings for LCU self-signed cert
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# LCU position names → our role names
_POSITION_MAP = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "ADC",
    "utility": "Support",
    "": "",
}


def get_lcu_credentials():
    """
    Find the LeagueClientUx process and extract port/token for LCU API auth.
    Returns (port, password) or (None, None) if not found.
    """
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if proc.info['name'] and 'LeagueClientUx' in proc.info['name']:
                port = None
                password = None
                for arg in (proc.info['cmdline'] or []):
                    if arg.startswith('--app-port='):
                        port = arg.split('=')[1]
                    elif arg.startswith('--remoting-auth-token='):
                        password = arg.split('=')[1]
                if port and password:
                    return port, password
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None, None


def lcu_request(path):
    """Make an authenticated GET request to the LCU API."""
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
        response = requests.get(url, headers=headers, verify=False, timeout=3)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception:
        return None


def get_champion_select():
    """
    Get current champion select session data.
    Returns (ally_ids, enemy_ids) or None if not in champ select.
    """
    data = lcu_request('/lol-champ-select/v1/session')
    if not data:
        return None
    ally_picks = []
    enemy_picks = []
    for slot in data.get('myTeam', []):
        champ_id = slot.get('championId', 0) or slot.get('championPickIntent', 0)
        if champ_id:
            ally_picks.append(champ_id)
    for slot in data.get('theirTeam', []):
        champ_id = slot.get('championId', 0)
        if champ_id:
            enemy_picks.append(champ_id)
    return ally_picks, enemy_picks


def get_champion_select_full():
    """
    Get full champion select session data including assigned role.
    Returns dict with:
      - ally_ids: list of allied champion IDs
      - enemy_ids: list of enemy champion IDs
      - assigned_position: player's assigned role (Top/Jungle/Mid/ADC/Support)
      - phase: current phase (e.g. 'BAN_PICK', 'PLANNING', 'FINALIZATION')
      - in_progress: whether champ select is active
    Or None if not in champ select.
    """
    data = lcu_request('/lol-champ-select/v1/session')
    if not data:
        return None

    ally_picks = []
    enemy_picks = []
    assigned_position = ""

    local_player_cell_id = data.get('localPlayerCellId', -1)

    for slot in data.get('myTeam', []):
        champ_id = slot.get('championId', 0) or slot.get('championPickIntent', 0)
        if champ_id:
            ally_picks.append(champ_id)
        # Find our assigned position
        if slot.get('cellId') == local_player_cell_id:
            raw_pos = slot.get('assignedPosition', '')
            assigned_position = _POSITION_MAP.get(raw_pos.lower(), '')

    for slot in data.get('theirTeam', []):
        champ_id = slot.get('championId', 0)
        if champ_id:
            enemy_picks.append(champ_id)

    # Determine the current phase from timer
    timer = data.get('timer', {})
    phase = timer.get('phase', 'UNKNOWN')

    return {
        'ally_ids': ally_picks,
        'enemy_ids': enemy_picks,
        'assigned_position': assigned_position,
        'phase': phase,
        'in_progress': True
    }


def is_client_running():
    """Check if the League client process is running."""
    port, password = get_lcu_credentials()
    return port is not None and password is not None
