from flask import Flask, render_template, request, jsonify
from champion_data import champions, counters, synergies, roles
from lcu_api import get_champion_select

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', champions=champions)

@app.route('/suggest', methods=['POST'])
def suggest():
    data = request.get_json()
    ally_picks = data.get('ally_picks', [])[:4]  # Only allow up to 4 ally picks
    enemy_picks = data.get('enemy_picks', [])

    # Filter out already picked champions
    available = [c for c in champions if c not in ally_picks + enemy_picks]
    scores = {c: 0 for c in available}
    reasons = {c: [] for c in available}

    # Counter logic: +2 for each enemy champion this champ counters
    for champ in available:
        for enemy in enemy_picks:
            if enemy in counters.get(champ, []):
                scores[champ] += 2
                reasons[champ].append(f"Counters {enemy}")

    # Synergy logic: +1 for each ally champion this champ synergizes with
    for champ in available:
        for ally in ally_picks:
            if ally in synergies.get(champ, []):
                scores[champ] += 1
                reasons[champ].append(f"Synergizes with {ally}")

    # Fill missing role: +1 if this champ fills a missing role
    picked_roles = [roles.get(c) for c in ally_picks]
    for champ in available:
        role = roles.get(champ)
        if role and role not in picked_roles:
            scores[champ] += 1
            reasons[champ].append(f"Fills missing role: {role}")

    # Get top 3 suggestions
    top = sorted(scores, key=lambda c: scores[c], reverse=True)[:3]
    suggestions = [
        {
            'champion': champ,
            'score': scores[champ],
            'reasons': reasons[champ]
        }
        for champ in top
    ]
    return jsonify(suggestions)

import ddragon

@app.route('/read_champion_select', methods=['POST'])
def read_champion_select():
    ally_ids, enemy_ids = get_champion_select() or ([], [])
    champion_id_to_name = ddragon.get_champion_id_to_name()
    # Map IDs to names (fallback to empty string if not found)
    ally_names = [champion_id_to_name.get(cid, "") for cid in ally_ids]
    enemy_names = [champion_id_to_name.get(cid, "") for cid in enemy_ids]
    return jsonify({
        'ally_picks': ally_names,
        'enemy_picks': enemy_names
    })

if __name__ == '__main__':
    app.run(debug=True)
