"""
LoL Champion Suggester - Flask web server.

  GET  /               web UI (champion catalog and data freshness are inlined)
  GET  /api/bootstrap  champion catalog, roles, defaults and data freshness
  GET  /api/meta       data freshness only
  POST /suggest        full draft analysis: pick and ban suggestions, both teams'
                       compositions and the draft outlook
  GET  /lcu/status     one-shot League client / champion select state
  GET  /lcu/stream     Server-Sent Events with live champion select updates
  GET  /lcu/mastery    the local player's champion mastery (to import a pool)
  GET  /lcu/owned      champions the local player owns or can play for free

Run:  py app.py [--port 5000] [--host 127.0.0.1] [--open] [--debug]
"""

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import champion_data as cd
import ddragon
import suggester
from lcu_api import client as lcu

load_dotenv()

app = Flask(__name__)
app.json.sort_keys = False

DEFAULT_SUGGESTIONS = 10
MAX_SUGGESTIONS = 50
MAX_BAN_SUGGESTIONS = 12
POLL_INTERVAL = 1.0        # seconds between client polls during champion select
IDLE_POLL_INTERVAL = 3.0   # ... while the client is closed or outside champion select
HEARTBEAT = 15.0           # seconds between SSE keep-alive comments


def _name(champion_id):
    return ddragon.get_champion_id_to_name().get(champion_id, "") if champion_id else ""


def _names(ids):
    id_to_name = ddragon.get_champion_id_to_name()
    return [id_to_name[i] for i in ids or [] if i in id_to_name]


def data_meta():
    stats = cd.stats_meta
    return {
        "patch": stats.get("patch") or cd.matchups_meta.get("patch", ""),
        "tier_bracket": stats.get("tier_bracket") or cd.matchups_meta.get("tier_bracket", ""),
        "stats_updated": stats.get("scraped_at", ""),
        "matchups_updated": cd.matchups_meta.get("scraped_at", ""),
        "games_analysed": stats.get("analysed"),
        "has_stats": bool(cd.champ_stats),
        "has_matchups": cd.has_matchup_data(),
        "ddragon_version": ddragon.get_latest_version(),
        "source": "lolalytics.com",
    }


def bootstrap():
    cd.reload_if_changed()
    return {
        "roles": cd.ROLES,
        "champions": cd.champion_catalog(),
        "data": data_meta(),
        "defaults": {
            "count": DEFAULT_SUGGESTIONS,
            "max_count": MAX_SUGGESTIONS,
            "comfort": suggester.DEFAULT_COMFORT,
            "max_comfort": suggester.MAX_COMFORT,
            "niche_pick_rate": suggester.NICHE_PICK_RATE,
        },
    }


# ---------------------------------------------------------------------------
# League client state
# ---------------------------------------------------------------------------

def session_payload(session):
    """Champion select session with champion ids turned into names."""
    me = session["me"]
    return {
        "phase": session["phase"],   # PLANNING, BAN_PICK, FINALIZATION, GAME_STARTING
        "timer": {
            "left_ms": session["time_left_ms"],
            "total_ms": session["total_time_ms"],
            "at": int(time.time() * 1000),
        },
        "action": session["action"],
        "my_role": me["role"],
        "me": {"champion": _name(me["champion_id"]), "state": me["state"]},
        "allies": [{"champion": _name(a["champion_id"]), "role": a["role"], "state": a["state"]}
                   for a in session["allies"]],
        "enemies": [{"champion": _name(e["champion_id"]), "state": e["state"]}
                    for e in session["enemies"]],
        "bans": {"ally": _names(session["bans"]["ally"]), "enemy": _names(session["bans"]["enemy"])},
        "game_id": session["game_id"],
    }


def read_live_state():
    """
    {"type": "offline"} when the client isn't running,
    {"type": "connected", ...} outside champion select,
    {"type": "champ_select", ...} with the full session otherwise.
    """
    if not lcu.is_running():
        return {"type": "offline"}
    gameflow = lcu.gameflow_phase()
    summoner = (lcu.summoner() or {}).get("name", "")
    session = lcu.champ_select() if gameflow in ("ChampSelect", "") else None
    if not session:
        if not lcu.is_running():
            return {"type": "offline"}
        return {"type": "connected", "gameflow": gameflow, "summoner": summoner}
    state = {"type": "champ_select", "gameflow": gameflow, "summoner": summoner}
    state.update(session_payload(session))
    state["pickable"] = _names(lcu.pickable_ids())
    return state


class LivePoller:
    """
    Polls the League client from one background thread while at least one SSE
    client is listening, and wakes listeners only when something other than the
    countdown changes (the UI runs the countdown itself).
    """

    def __init__(self, read=read_live_state):
        self._read = read
        self._cond = threading.Condition()
        self._version = 0
        self._state = None
        self._key = None
        self._fresh = False
        self._listeners = 0
        self._thread = None

    def subscribe(self):
        with self._cond:
            if self._listeners == 0:
                self._fresh = False   # whatever we saw before the pause may be stale
            self._listeners += 1
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="lcu-poller", daemon=True)
                self._thread.start()
            self._cond.notify_all()

    def unsubscribe(self):
        with self._cond:
            self._listeners = max(0, self._listeners - 1)

    def wait(self, version, timeout):
        """(version, state) once there is a fresh state newer than `version`, else (version, None)."""
        with self._cond:
            self._cond.wait_for(lambda: self._fresh and self._version != version, timeout)
            if self._fresh and self._version != version:
                return self._version, self._state
            return version, None

    def publish(self, state):
        key = json.dumps({k: v for k, v in state.items() if k != "timer"}, sort_keys=True)
        with self._cond:
            if key != self._key or not self._fresh:
                self._key = key
                self._version += 1
                self._cond.notify_all()
            self._state = state
            self._fresh = True

    def _run(self):
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._listeners > 0)
            try:
                state = self._read()
            except Exception as e:   # never let one bad poll kill the thread
                app.logger.exception("League client poll failed")
                state = {"type": "error", "message": str(e)}
            self.publish(state)
            time.sleep(POLL_INTERVAL if state.get("type") == "champ_select" else IDLE_POLL_INTERVAL)


live = LivePoller()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", bootstrap=bootstrap())


@app.route("/api/bootstrap")
def api_bootstrap():
    return jsonify(bootstrap())


@app.route("/api/meta")
def api_meta():
    cd.reload_if_changed()
    return jsonify(data_meta())


def _int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


@app.route("/suggest", methods=["POST"])
def suggest():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object body"}), 400
    cd.reload_if_changed()
    draft = suggester.Draft.from_payload(data)
    result = suggester.analyze(
        draft,
        count=_int(data.get("count"), DEFAULT_SUGGESTIONS, 1, MAX_SUGGESTIONS),
        ban_count=_int(data.get("ban_count"), 8, 1, MAX_BAN_SUGGESTIONS),
    )
    result["patch"] = cd.stats_meta.get("patch", "")
    return jsonify(result)


@app.route("/lcu/status")
def lcu_status():
    return jsonify(read_live_state())


@app.route("/lcu/stream")
def lcu_stream():
    def generate():
        live.subscribe()
        try:
            version = 0
            yield "retry: 3000\n\n"
            while True:
                new_version, state = live.wait(version, HEARTBEAT)
                if state is None:
                    yield ": keep-alive\n\n"
                    continue
                version = new_version
                yield f"data: {json.dumps(state)}\n\n"
        finally:
            live.unsubscribe()

    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/lcu/mastery")
def lcu_mastery():
    rows = lcu.mastery()
    if rows is None:
        return jsonify({"available": False, "champions": []})
    id_to_name = ddragon.get_champion_id_to_name()
    limit = _int(request.args.get("limit"), 30, 1, 200)
    champions = [{"champion": id_to_name[r["champion_id"]], "level": r["level"], "points": r["points"]}
                 for r in rows if r["champion_id"] in id_to_name]
    return jsonify({"available": True, "champions": champions[:limit]})


@app.route("/lcu/owned")
def lcu_owned():
    ids = lcu.owned_ids()
    return jsonify({"available": ids is not None, "champions": _names(ids)})


def port_in_use(host, port):
    """True when something already accepts connections on host:port.

    Windows lets a second server bind a port that is in use, and requests then
    get split between the two, so check before starting.
    """
    target = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with socket.create_connection((target, port), timeout=0.3):
            return True
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description="LoL Champion Suggester web server")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--open", action="store_true", help="open the app in your browser")
    parser.add_argument("--debug", action="store_true", default=os.environ.get("FLASK_DEBUG") == "1",
                        help="auto-reload on code changes (never use with a public --host)")
    args, _ = parser.parse_known_args()

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}"
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        if port_in_use(args.host, args.port):
            print(f"Port {args.port} is already in use - the app may already be running at {url}")
            print("Close the other instance or start this one with a different --port.")
            sys.exit(1)
        meta = data_meta()
        print(f"LoL Champion Suggester - patch {meta['patch'] or '?'} data, "
              f"{meta['tier_bracket'].replace('_', ' ') or 'unknown bracket'}")
        if not meta["has_matchups"]:
            print("  No matchup data yet. Run:  py data/update_data.py")
        print(f"  Open {url}")
        if args.open:
            threading.Timer(1.0, webbrowser.open, (url,)).start()
    app.run(debug=args.debug, threaded=True, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
