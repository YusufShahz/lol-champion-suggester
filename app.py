import os
import json
import time
import threading
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from champion_data import champions, counters, synergies, roles, counter_details
from lcu_api import get_champion_select_full, is_client_running
import ddragon

app = Flask(__name__)

# Pre-compute a lookup: for each champion, what champions counter THEM
_countered_by_lookup = {}
for champ, details in counter_details.items():
    for entry in details.get("countered_by", []):
        opponent = entry["name"]
        if opponent not in _countered_by_lookup:
            _countered_by_lookup[opponent] = {}
        _countered_by_lookup[opponent][champ] = entry

# Pre-compute average win rate per champion from their strong_against matchups
_avg_win_rates = {}
for champ, details in counter_details.items():
    strong = details.get("strong_against", [])
    if strong:
        _avg_win_rates[champ] = sum(e["win_rate"] for e in strong) / len(strong)


ROLES = ["Top", "Jungle", "Mid", "ADC", "Support"]
_id_to_name = ddragon.get_champion_id_to_name()

# Cache ddragon version and champion key map for frontend icon URLs
_ddragon_version = ddragon.get_latest_version()
_champion_icon_keys = {}
try:
    import requests as _req
    _dd_resp = _req.get(f"https://ddragon.leagueoflegends.com/cdn/{_ddragon_version}/data/en_US/champion.json")
    if _dd_resp.status_code == 200:
        for key, val in _dd_resp.json()["data"].items():
            _champion_icon_keys[val["name"]] = key  # e.g. "Miss Fortune" -> "MissFortune"
except Exception:
    pass


@app.route('/api/ddragon')
def ddragon_info():
    """Return Data Dragon version and champion icon key mapping."""
    return jsonify({
        'version': _ddragon_version,
        'icon_keys': _champion_icon_keys
    })


@app.route('/')
def index():
    return render_template('index.html', champions=champions, roles=ROLES)


def _compute_suggestions(ally_picks, enemy_picks, role_filter='', count=5):
    """Core suggestion logic, extracted for reuse by both /suggest and SSE."""
    available = [c for c in champions if c not in ally_picks + enemy_picks]

    if role_filter and role_filter in ROLES:
        available = [c for c in available if roles.get(c) == role_filter]

    scores = {}
    reasons = {}

    for champ in available:
        score = 0.0
        champ_reasons = []
        champ_details = counter_details.get(champ, {})

        # Counter scoring (weighted by delta2)
        strong_against = {e["name"]: e for e in champ_details.get("strong_against", [])}
        for enemy in enemy_picks:
            if enemy in strong_against:
                entry = strong_against[enemy]
                delta = abs(entry.get("delta2", 0))
                weight = min(delta / 5.0, 4.0)
                bonus = 2.0 + weight
                score += bonus
                wr = entry.get("win_rate", 0)
                champ_reasons.append(f"Counters {enemy} ({wr:.1f}% WR, \u0394{delta:+.1f})")

        # Countered-by penalty
        countered_by = {e["name"]: e for e in champ_details.get("countered_by", [])}
        for enemy in enemy_picks:
            if enemy in countered_by:
                entry = countered_by[enemy]
                delta = abs(entry.get("delta2", 0))
                penalty = min(delta / 5.0, 3.0)
                score -= penalty
                wr = entry.get("win_rate", 0)
                champ_reasons.append(f"Countered by {enemy} ({wr:.1f}% WR, \u0394{entry.get('delta2', 0):+.1f})")

        # Synergy scoring
        for ally in ally_picks:
            if ally in synergies.get(champ, []):
                score += 1.5
                champ_reasons.append(f"Synergizes with {ally}")

        # Role fill bonus
        picked_roles = [roles.get(c) for c in ally_picks]
        champ_role = roles.get(champ)
        if champ_role and champ_role not in picked_roles:
            score += 1.0
            champ_reasons.append(f"Fills {champ_role} role")

        # Win rate tiebreaker
        avg_wr = _avg_win_rates.get(champ, 50.0)
        wr_bonus = (avg_wr - 50.0) / 10.0
        score += wr_bonus

        scores[champ] = score
        reasons[champ] = champ_reasons

    # Normalize scores to 0-100
    if scores:
        raw_scores = list(scores.values())
        min_score = min(raw_scores)
        max_score = max(raw_scores)
        score_range = max_score - min_score

        if score_range > 0:
            for champ in scores:
                scores[champ] = round(((scores[champ] - min_score) / score_range) * 100, 1)
        else:
            for champ in scores:
                scores[champ] = 50.0

    top = sorted(scores, key=lambda c: scores[c], reverse=True)[:count]
    return [
        {
            'champion': champ,
            'score': scores[champ],
            'role': roles.get(champ, 'Unknown'),
            'reasons': reasons[champ]
        }
        for champ in top
    ]


@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json()
    ally_picks = data.get('ally_picks', [])[:4]
    enemy_picks = data.get('enemy_picks', [])
    role_filter = data.get('role', '')
    count = min(int(data.get('count', 5)), 20)

    suggestions = _compute_suggestions(ally_picks, enemy_picks, role_filter, count)
    return jsonify(suggestions)


@app.route('/lcu/status')
def lcu_status():
    """Check if the League client is running and if we're in champ select."""
    running = is_client_running()
    session = None
    if running:
        session = get_champion_select_full()

    result = {'client_running': running, 'in_champ_select': False}

    if session:
        result['in_champ_select'] = True
        result['phase'] = session.get('phase', '')
        result['assigned_position'] = session.get('assigned_position', '')
        result['ally_picks'] = [_id_to_name.get(cid, '') for cid in session['ally_ids']]
        result['enemy_picks'] = [_id_to_name.get(cid, '') for cid in session['enemy_ids']]

    return jsonify(result)


@app.route('/lcu/stream')
def lcu_stream():
    """
    Server-Sent Events (SSE) endpoint that polls LCU every 2 seconds
    and pushes champion select updates to the frontend.
    """
    def generate():
        last_state = None
        while True:
            try:
                session = get_champion_select_full()
                if session:
                    ally_names = [_id_to_name.get(cid, '') for cid in session['ally_ids']]
                    enemy_names = [_id_to_name.get(cid, '') for cid in session['enemy_ids']]
                    current_state = {
                        'type': 'champ_select',
                        'ally_picks': ally_names,
                        'enemy_picks': enemy_names,
                        'assigned_position': session.get('assigned_position', ''),
                        'phase': session.get('phase', ''),
                    }
                else:
                    current_state = {'type': 'idle'}

                # Only send if state changed
                state_key = json.dumps(current_state, sort_keys=True)
                if state_key != last_state:
                    last_state = state_key
                    yield f"data: {json.dumps(current_state)}\n\n"

            except GeneratorExit:
                return
            except Exception:
                yield f"data: {json.dumps({'type': 'error', 'message': 'LCU poll error'})}\n\n"

            time.sleep(2)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/read_champion_select', methods=['POST'])
def read_champion_select():
    session = get_champion_select_full()
    if not session:
        return jsonify({'ally_picks': [], 'enemy_picks': [], 'assigned_position': ''})

    ally_names = [_id_to_name.get(cid, '') for cid in session['ally_ids']]
    enemy_names = [_id_to_name.get(cid, '') for cid in session['enemy_ids']]
    return jsonify({
        'ally_picks': ally_names,
        'enemy_picks': enemy_names,
        'assigned_position': session.get('assigned_position', '')
    })


if __name__ == '__main__':
    app.run(debug=True, threaded=True)
