"""
League Client (LCU) API integration.

Finds the running LeagueClientUx process, authenticates with its local HTTPS API
and reads champion select: locked picks and hovers, bans per team, every ally's
assigned position, whose turn it is and the phase timer. Also exposes the local
player's pickable / owned champions, champion mastery and summoner name.

Credentials are cached; the process list is only re-scanned when the client
stops answering (it gets a new port and token when it restarts).
"""

import threading
import time

import psutil
import requests
import urllib3

# The LCU serves a self-signed certificate on 127.0.0.1
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

POSITION_TO_ROLE = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "ADC",
    "utility": "Support",
}

RESCAN_INTERVAL = 3.0   # seconds between process scans while the client isn't found


def _find_client():
    """(port, token) of a running LeagueClientUx process, or None."""
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if "LeagueClientUx" not in (proc.info.get("name") or ""):
                continue
            port = token = None
            for arg in proc.info.get("cmdline") or []:
                if arg.startswith("--app-port="):
                    port = arg.split("=", 1)[1]
                elif arg.startswith("--remoting-auth-token="):
                    token = arg.split("=", 1)[1]
            if port and token:
                return port, token
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return None


class LCUClient:
    def __init__(self):
        self._lock = threading.Lock()
        self._creds = None
        self._last_scan = 0.0
        self._session = requests.Session()
        self._session.verify = False
        self._summoner = None

    def credentials(self, force=False):
        with self._lock:
            if self._creds and not force:
                return self._creds
            now = time.time()
            if not force and now - self._last_scan < RESCAN_INTERVAL:
                return self._creds
            self._last_scan = now
            creds = _find_client()
            if creds != self._creds:
                self._summoner = None
            self._creds = creds
            return creds

    def get(self, path, timeout=2.5):
        """GET an LCU endpoint; None when the client is closed or the call fails."""
        creds = self.credentials()
        for attempt in range(2):
            if not creds:
                return None
            port, token = creds
            try:
                resp = self._session.get(f"https://127.0.0.1:{port}{path}", auth=("riot", token),
                                         headers={"Accept": "application/json"}, timeout=timeout)
            except requests.RequestException:
                if attempt == 0:
                    creds = self.credentials(force=True)  # client restarted or closed
                    continue
                return None
            if resp.status_code in (401, 403) and attempt == 0:
                creds = self.credentials(force=True)
                continue
            if resp.status_code != 200:
                return None
            try:
                return resp.json()
            except ValueError:
                return None
        return None

    def is_running(self):
        return self.credentials() is not None

    def gameflow_phase(self):
        """'None', 'Lobby', 'Matchmaking', 'ReadyCheck', 'ChampSelect', 'InProgress', ..."""
        phase = self.get("/lol-gameflow/v1/gameflow-phase")
        return phase if isinstance(phase, str) else ""

    def summoner(self):
        if self._summoner is None:
            data = self.get("/lol-summoner/v1/current-summoner")
            if isinstance(data, dict):
                name = data.get("gameName") or data.get("displayName") or ""
                tag = data.get("tagLine") or ""
                self._summoner = {
                    "name": f"{name}#{tag}" if name and tag else name,
                    "summoner_id": data.get("summonerId"),
                    "puuid": data.get("puuid"),
                }
        return self._summoner

    def champ_select(self):
        """Parsed champion select session (see parse_session) or None outside champ select."""
        data = self.get("/lol-champ-select/v1/session")
        if not isinstance(data, dict) or "myTeam" not in data:
            return None
        return parse_session(data)

    def pickable_ids(self):
        ids = self.get("/lol-champ-select/v1/pickable-champion-ids")
        return [int(i) for i in ids if i] if isinstance(ids, list) else None

    def owned_ids(self):
        data = self.get("/lol-champions/v1/owned-champions-minimal")
        if not isinstance(data, list):
            return None
        out = []
        for c in data:
            own = c.get("ownership") or {}
            rental = own.get("rental") or {}
            if own.get("owned") or rental.get("rented") or c.get("freeToPlay"):
                if c.get("id", 0) > 0:
                    out.append(int(c["id"]))
        return out

    def mastery(self):
        """[{champion_id, level, points}] sorted by points, or None."""
        data = self.get("/lol-champion-mastery/v1/local-player/champion-mastery")
        if not isinstance(data, list):
            summ = self.summoner() or {}
            if summ.get("summoner_id"):
                data = self.get(f"/lol-collections/v1/inventories/{summ['summoner_id']}/champion-mastery")
        if not isinstance(data, list):
            return None
        rows = [{"champion_id": int(m.get("championId") or 0),
                 "level": int(m.get("championLevel") or 0),
                 "points": int(m.get("championPoints") or 0)} for m in data if isinstance(m, dict)]
        rows = [r for r in rows if r["champion_id"] > 0]
        rows.sort(key=lambda r: -r["points"])
        return rows


# ---------------------------------------------------------------------------
# Session parsing (pure, unit-tested)
# ---------------------------------------------------------------------------

def parse_session(data):
    """
    Turn /lol-champ-select/v1/session into:
      me:        {cell_id, champion_id, state, role}
      allies:    [{cell_id, champion_id, state, role}]  (the four other players)
      enemies:   [{cell_id, champion_id, state}]
      bans:      {"ally": [ids], "enemy": [ids]}
      phase, time_left_ms, total_time_ms, action, game_id
    state is "locked", "hovering" (selected during their turn) or "intent"
    (declared before their turn). Empty slots have champion_id 0 and state "".
    """
    local_cell = data.get("localPlayerCellId", -1)
    actions = [a for group in (data.get("actions") or []) for a in (group or []) if isinstance(a, dict)]
    picks_by_cell = {}
    for a in actions:
        if a.get("type") == "pick":
            picks_by_cell.setdefault(a.get("actorCellId"), []).append(a)

    def slot_state(slot):
        cell = slot.get("cellId")
        cid = int(slot.get("championId") or 0)
        intent = int(slot.get("championPickIntent") or 0)
        acts = picks_by_cell.get(cell, [])
        locked = any(a.get("completed") and a.get("championId") for a in acts)
        if not cid:
            done = next((a for a in acts if a.get("completed") and a.get("championId")), None)
            if done:
                cid = int(done["championId"])
        if cid and (locked or not acts):
            return cid, "locked"
        hovering = next((a for a in acts if a.get("isInProgress") and a.get("championId")), None)
        if cid or hovering:
            return cid or int(hovering["championId"]), "hovering"
        if intent:
            return intent, "intent"
        return 0, ""

    me, allies, enemies = None, [], []
    for slot in data.get("myTeam") or []:
        cid, state = slot_state(slot)
        entry = {
            "cell_id": slot.get("cellId"),
            "champion_id": cid,
            "state": state,
            "role": POSITION_TO_ROLE.get((slot.get("assignedPosition") or "").lower(), ""),
        }
        if slot.get("cellId") == local_cell:
            me = entry
        else:
            allies.append(entry)
    for slot in data.get("theirTeam") or []:
        cid, state = slot_state(slot)
        enemies.append({"cell_id": slot.get("cellId"), "champion_id": cid, "state": state})

    ally_cells = {s.get("cellId") for s in data.get("myTeam") or []}
    bans = {"ally": [], "enemy": []}
    for a in actions:
        cid = int(a.get("championId") or 0)
        if a.get("type") != "ban" or not a.get("completed") or cid <= 0:
            continue
        side = "ally" if a.get("isAllyAction") or a.get("actorCellId") in ally_cells else "enemy"
        if cid not in bans[side]:
            bans[side].append(cid)
    extra = data.get("bans") or {}
    for key, side in (("myTeamBans", "ally"), ("theirTeamBans", "enemy")):
        for cid in extra.get(key) or []:
            if cid and cid > 0 and cid not in bans[side]:
                bans[side].append(int(cid))

    in_progress = [a for a in actions if a.get("isInProgress")]
    current = next((a for a in in_progress if a.get("actorCellId") == local_cell), None) \
        or (in_progress[0] if in_progress else None)
    action = None
    if current:
        action = {
            "type": current.get("type", ""),
            "is_mine": current.get("actorCellId") == local_cell,
            "is_ally": bool(current.get("isAllyAction")) or current.get("actorCellId") in ally_cells,
        }

    timer = data.get("timer") or {}
    return {
        "me": me or {"cell_id": local_cell, "champion_id": 0, "state": "", "role": ""},
        "allies": allies,
        "enemies": enemies,
        "bans": bans,
        "phase": timer.get("phase") or "",
        "time_left_ms": timer.get("adjustedTimeLeftInPhase"),
        "total_time_ms": timer.get("totalTimeInPhase"),
        "action": action,
        "game_id": data.get("gameId"),
    }


client = LCUClient()


def get_champion_select_full():
    return client.champ_select()


def is_client_running():
    return client.is_running()
