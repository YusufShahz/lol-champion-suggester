"""
Draft suggestion engine.

Each candidate gets an estimated win rate for the current draft, normalised so
an average champion in an average draft sits at 50%:

    estimate = 50 + meta + matchups + synergy + composition + blind_risk + comfort

  meta         lane win rate minus the bracket's average win rate
  matchups     Lolalytics delta2 against every enemy, weighted by the chance
               that enemy plays each lane
  synergy      delta2 with every ally, weighted the same way
  composition  damage-type balance, frontline and crowd-control gaps
  blind_risk   expected loss to a counter-pick while the lane opponent is unknown
  comfort      flat bonus for champions in the player's pool

Every observed effect is shrunk towards zero by games / (games + K): K is the
sampling variance of one game (2500 pp^2) divided by the variance of genuine
effects of that kind, estimated from patch 16.18 Emerald+ data by comparing the
observed spread of each delta family with pure sampling noise.

Roles are inferred by enumerating every way to put a team's champions in
distinct lanes, weighted by how often each champion plays each lane. Roles
known from the client or pinned by the user constrain the enumeration.
"""

import math
from itertools import combinations, permutations

import champion_data as cd

LANES = cd.LANES

K_META = 1000
K_MATCHUP_LANE = 750
K_MATCHUP_CROSS = 2000
K_SYNERGY = 5000
K_SYNERGY_DUO = 1700           # bottom + support

MIN_LANE_GAMES = 300           # a candidate needs this many games in the lane
NICHE_PICK_RATE = 1.0          # picked in fewer than this % of lane games: mostly specialists
ROLE_FLOOR = 0.5               # % added to every lane share so forced assignments stay possible
MIN_ROLE_PROBABILITY = 0.02    # lane assignments less likely than this are ignored

COUNTER_PICK_PROPENSITY = 0.4  # chance an unseen lane opponent deliberately counter-picks
COUNTER_MIN_PICK_RATE = 0.5    # counters picked in fewer than this % of lane games are ignored
COUNTERS_CONSIDERED = 3

DAMAGE_WEIGHT = 8.0
FRONTLINE_BONUS = 1.5
CC_BONUS = 1.0
COMP_CAP = 2.5

DEFAULT_COMFORT = 1.5
MAX_COMFORT = 5.0
REASON_THRESHOLD = 0.25        # effects smaller than this (pp) are not listed as reasons

OUTLOOK_MIN, OUTLOOK_MAX = 25.0, 75.0  # drafts alone never decide games more than this


def shrink(effect, games, k):
    return effect * games / (games + k) if games and games > 0 else 0.0


def _synergy_k(lane_a, lane_b):
    return K_SYNERGY_DUO if {lane_a, lane_b} == {"bottom", "support"} else K_SYNERGY


def meta_strength(champ, lane):
    s = cd.lane_stats(champ, lane)
    if not s:
        return 0.0
    return shrink(s["win_rate"] - cd.lane_avg_wr(lane), s["games"], K_META)


def matchup_effect(champ, lane, opp, opp_lane):
    """(shrunk delta, raw (win_rate, delta2, games) or None) for champ@lane vs opp@opp_lane."""
    raw = cd.matchup(champ, lane, opp, opp_lane)
    if not raw:
        return 0.0, None
    k = K_MATCHUP_LANE if lane == opp_lane else K_MATCHUP_CROSS
    return shrink(raw[1], raw[2], k), raw


def synergy_effect(champ, lane, ally, ally_lane):
    raw = cd.synergy(champ, lane, ally, ally_lane)
    if not raw:
        return 0.0, None
    return shrink(raw[1], raw[2], _synergy_k(lane, ally_lane)), raw


# ---------------------------------------------------------------------------
# Role inference
# ---------------------------------------------------------------------------

class Roles:
    """Lane assignment for one team: most likely assignment plus per-champion lane odds."""

    def __init__(self, champions, assignment, marginals, perms, pinned):
        self.champions = champions      # names, in input order
        self.assignment = assignment    # {name: lane} most likely assignment
        self.marginals = marginals      # {name: {lane: probability}}
        self.perms = perms              # [(lanes tuple aligned with champions, probability)]
        self.pinned = pinned            # {name: lane} constraints that were applied

    def probability(self, name, lane):
        return self.marginals.get(name, {}).get(lane, 0.0)

    def lane_filled(self, lane):
        """Probability that someone on this team plays `lane`."""
        return min(1.0, sum(d.get(lane, 0.0) for d in self.marginals.values()))


def infer_roles(champions, pinned=None, blocked=()):
    """
    champions: names on one team (at most five)
    pinned:    {name: lane} known lanes (client-assigned or set by the user)
    blocked:   lanes nobody here can play (e.g. the local player's lane for allies)
    """
    champs = list(dict.fromkeys(c for c in champions if c))
    lanes = [l for l in LANES if l not in blocked]
    if len(champs) > len(lanes):
        lanes = list(LANES)
    champs = champs[:len(lanes)]
    if not champs:
        return Roles([], {}, {}, [], {})

    fixed, used = {}, set()
    for c in champs:
        lane = (pinned or {}).get(c)
        if lane in lanes and lane not in used:
            fixed[c] = lane
            used.add(lane)

    dist = {c: cd.lane_distribution(c, floor=ROLE_FLOOR) for c in champs}
    weighted = []
    for perm in permutations(lanes, len(champs)):
        w = 1.0
        for c, lane in zip(champs, perm):
            f = fixed.get(c)
            w *= (1.0 if f == lane else 0.0) if f else dist[c][lane]
            if w == 0.0:
                break
        if w > 0.0:
            weighted.append((perm, w))

    total = sum(w for _, w in weighted)
    perms = [(perm, w / total) for perm, w in weighted]
    best = max(perms, key=lambda pw: pw[1])[0]
    marginals = {c: dict.fromkeys(LANES, 0.0) for c in champs}
    for perm, p in perms:
        for c, lane in zip(champs, perm):
            marginals[c][lane] += p
    return Roles(champs, dict(zip(champs, best)), marginals, perms, fixed)


# ---------------------------------------------------------------------------
# Draft state
# ---------------------------------------------------------------------------

def _lane_of(role_or_lane):
    if not role_or_lane:
        return None
    if role_or_lane in cd.ROLE_TO_LANE:
        return cd.ROLE_TO_LANE[role_or_lane]
    return role_or_lane if role_or_lane in LANES else None


class Draft:
    """A normalised champion select state plus the player's preferences."""

    def __init__(self, my_lane=None, my_pick="", allies=(), enemies=(), bans=(), pool=(),
                 pool_only=False, comfort=DEFAULT_COMFORT, available=None, include_niche=False):
        known = set(cd.champions)

        def clean(entries, limit):
            out, seen = [], set()
            for name, lane in entries:
                if name in known and name not in seen:
                    seen.add(name)
                    out.append((name, _lane_of(lane)))
            return out[:limit]

        self.my_lane = _lane_of(my_lane)
        self.my_pick = my_pick if my_pick in known else ""
        self.allies = [(n, l) for n, l in clean(allies, 5) if n != self.my_pick][:4]
        self.enemies = clean(enemies, 5)
        self.ally_names = [n for n, _ in self.allies]
        self.enemy_names = [n for n, _ in self.enemies]
        self.bans = {b for b in bans if b in known}
        self.pool = {p for p in pool if p in known}
        self.pool_only = bool(pool_only) and bool(self.pool)
        try:
            self.comfort = max(0.0, min(MAX_COMFORT, float(comfort)))
        except (TypeError, ValueError):
            self.comfort = DEFAULT_COMFORT
        self.available = {a for a in available if a in known} if available else None
        self.include_niche = bool(include_niche)
        self.taken = set(self.ally_names) | set(self.enemy_names) | self.bans
        self.enemy_roles = infer_roles(self.enemy_names, {n: l for n, l in self.enemies if l})
        self._ally_roles = {}

    @classmethod
    def from_payload(cls, data):
        """Build a Draft from the /suggest JSON body (also accepts the pre-2.x field names)."""
        def strings(value):
            return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []

        def text(value):
            return value if isinstance(value, str) else ""

        def entries(items, legacy):
            items = items if isinstance(items, list) else data.get(legacy)
            out = []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict):
                    out.append((text(item.get("champion")), text(item.get("role") or item.get("lane"))))
                elif isinstance(item, str):
                    out.append((item, None))
            return out

        available = data.get("available")
        return cls(
            my_lane=text(data.get("my_role") or data.get("role") or data.get("assigned_role")),
            my_pick=text(data.get("my_pick")),
            allies=entries(data.get("allies"), "ally_picks"),
            enemies=entries(data.get("enemies"), "enemy_picks"),
            bans=strings(data.get("bans")),
            pool=strings(data.get("pool")),
            pool_only=data.get("pool_only") is True,
            comfort=data.get("comfort", DEFAULT_COMFORT),
            available=strings(available) if isinstance(available, list) else None,
            include_niche=data.get("include_niche") is True,
        )

    def ally_roles(self, my_lane=None):
        """Ally lane inference with the local player's lane blocked."""
        if my_lane not in self._ally_roles:
            self._ally_roles[my_lane] = infer_roles(
                self.ally_names, {n: l for n, l in self.allies if l},
                blocked=(my_lane,) if my_lane else ())
        return self._ally_roles[my_lane]

    def open_lanes(self):
        """Lanes the local player could still take (no ally likely there)."""
        roles = self.ally_roles(None)
        lanes = [l for l in LANES if roles.lane_filled(l) < 0.5]
        return lanes or list(LANES)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _magic_share(profiles):
    magic = sum(p["magic"] for p in profiles)
    physical = sum(p["physical"] for p in profiles)
    return magic / (magic + physical) if magic + physical > 0 else 0.5


def _damage_imbalance(magic_share):
    return max(0.0, 0.25 - magic_share) + max(0.0, magic_share - 0.75)


def composition(draft, champ, lane, ally_roles):
    """(points, notes) for how well `champ` fills the allied team's gaps."""
    allies = [(a, ally_roles.assignment.get(a)) for a in draft.ally_names]
    k = len(allies)
    if k < 2:
        return 0.0, []
    urgency = k / 4.0
    points, notes = 0.0, []

    profiles = [cd.damage_profile(a, l) for a, l in allies]
    before = _magic_share(profiles)
    after = _magic_share(profiles + [cd.damage_profile(champ, lane)])
    improvement = _damage_imbalance(before) - _damage_imbalance(after)
    if abs(improvement) >= 0.01:
        pts = DAMAGE_WEIGHT * improvement * urgency
        points += pts
        if pts > 0:
            kind = "magic" if before < 0.5 else "physical"
            other = "physical" if kind == "magic" else "magic"
            notes.append({"impact": pts, "kind": "composition",
                          "text": f"Adds {kind} damage to a mostly {other} team"})
        else:
            kind = "physical" if before < 0.5 else "magic"
            notes.append({"impact": pts, "kind": "composition",
                          "text": f"Team is already mostly {kind} damage"})

    if not any(cd.is_frontline(a) for a, _ in allies):
        attrs = cd.attributes(champ)
        if cd.is_frontline(champ):
            pts = FRONTLINE_BONUS * urgency
            notes.append({"impact": pts, "kind": "composition", "text": "Adds the frontline your team lacks"})
            points += pts
        elif attrs["durability"] >= 2 and attrs["attack_type"] == "melee":
            pts = 0.5 * FRONTLINE_BONUS * urgency
            notes.append({"impact": pts, "kind": "composition", "text": "Adds some frontline"})
            points += pts

    cc_avg = sum(cd.attributes(a)["crowd_control"] for a, _ in allies) / k
    if cc_avg < 1.75 and cd.attributes(champ)["crowd_control"] >= 3:
        pts = CC_BONUS * urgency
        notes.append({"impact": pts, "kind": "composition", "text": "Brings crowd control your team lacks"})
        points += pts

    points = max(-COMP_CAP, min(COMP_CAP, points))
    return points, notes


def _lane_counters(draft, champ, lane):
    """Most dangerous available same-lane counters: [(shrunk delta, name, wr, d2, games)]."""
    threats = []
    for opp, row in cd.lane_opponents(champ, lane).items():
        if opp in draft.taken or opp == draft.my_pick:
            continue
        wr, d2, games = row
        eff = shrink(d2, games, K_MATCHUP_LANE)
        if eff >= -0.1:
            continue
        s = cd.lane_stats(opp, lane)
        if not s or s.get("pick_rate", 0.0) < COUNTER_MIN_PICK_RATE:
            continue
        threats.append((eff, opp, wr, d2, games))
    threats.sort()
    return threats[:COUNTERS_CONSIDERED]


def _confidence(games):
    return "high" if games >= 20000 else "medium" if games >= 5000 else "low"


def _r(x, nd=2):
    return round(x, nd) + 0.0  # + 0.0 turns -0.0 into 0.0


def score(draft, champ, lane, min_games=MIN_LANE_GAMES):
    """Full evaluation of `champ` in `lane` for this draft, or None without enough data."""
    s = cd.lane_stats(champ, lane)
    if not s or s.get("games", 0) < min_games:
        return None
    role = cd.LANE_TO_ROLE[lane]
    avg = cd.lane_avg_wr(lane)
    meta = shrink(s["win_rate"] - avg, s["games"], K_META)

    matchups, matchup_total = [], 0.0
    for enemy, dist in draft.enemy_roles.marginals.items():
        impact, shown = 0.0, None
        for el in LANES:
            p = dist.get(el, 0.0)
            if p < MIN_ROLE_PROBABILITY:
                continue
            eff, raw = matchup_effect(champ, lane, enemy, el)
            if raw is None:
                continue
            impact += p * eff
            if shown is None or p > shown[0]:
                shown = (p, el, raw)
        matchup_total += impact
        if shown:
            p, el, (wr, d2, games) = shown
            matchups.append({
                "champion": enemy, "lane": el, "role": cd.LANE_TO_ROLE[el],
                "probability": _r(p), "same_lane": el == lane,
                "win_rate": wr, "delta": d2, "games": games, "impact": _r(impact),
            })
    matchups.sort(key=lambda m: -abs(m["impact"]))

    ally_roles = draft.ally_roles(lane)
    synergies, synergy_total = [], 0.0
    for ally, dist in ally_roles.marginals.items():
        impact, shown = 0.0, None
        for al in LANES:
            p = dist.get(al, 0.0)
            if p < MIN_ROLE_PROBABILITY or al == lane:
                continue
            eff, raw = synergy_effect(champ, lane, ally, al)
            if raw is None:
                continue
            impact += p * eff
            if shown is None or p > shown[0]:
                shown = (p, al, raw)
        synergy_total += impact
        if shown:
            p, al, (wr, d2, games) = shown
            synergies.append({
                "champion": ally, "lane": al, "role": cd.LANE_TO_ROLE[al], "probability": _r(p),
                "win_rate": wr, "delta": d2, "games": games, "impact": _r(impact),
            })
    synergies.sort(key=lambda m: -abs(m["impact"]))

    comp, comp_notes = composition(draft, champ, lane, ally_roles)

    p_open = max(0.0, 1.0 - draft.enemy_roles.lane_filled(lane))
    threats = _lane_counters(draft, champ, lane)
    blind = 0.0
    if p_open > 0.05 and threats:
        blind = p_open * COUNTER_PICK_PROPENSITY * sum(t[0] for t in threats) / COUNTERS_CONSIDERED
    counters = [{"champion": opp, "win_rate": wr, "delta": d2, "games": games}
                for _, opp, wr, d2, games in threats]

    in_pool = champ in draft.pool
    comfort = draft.comfort if in_pool else 0.0
    total = meta + matchup_total + synergy_total + comp + blind + comfort

    reasons = []
    if abs(meta) >= REASON_THRESHOLD:
        tier = s.get("tier_letter") or ""
        label = f"{tier} tier, " if tier else ""
        reasons.append({"impact": meta, "kind": "meta",
                        "text": f"{label}{s['win_rate']:.1f}% win rate in {role}"})
    for m in matchups:
        if abs(m["impact"]) >= REASON_THRESHOLD:
            where = "" if m["same_lane"] else f" ({m['role']})"
            verb = "Strong vs" if m["impact"] > 0 else "Weak vs"
            reasons.append({"impact": m["impact"], "kind": "matchup", "text": f"{verb} {m['champion']}{where}"})
    for sy in synergies:
        if abs(sy["impact"]) >= REASON_THRESHOLD:
            verb = "Pairs well with" if sy["impact"] > 0 else "Awkward with"
            reasons.append({"impact": sy["impact"], "kind": "synergy", "text": f"{verb} {sy['champion']}"})
    reasons.extend(comp_notes)
    if blind <= -REASON_THRESHOLD:
        names = ", ".join(c["champion"] for c in counters[:2])
        reasons.append({"impact": blind, "kind": "blind", "text": f"Counter-pick risk: {names}"})
    elif p_open > 0.5:
        reasons.append({"impact": 0.0, "kind": "info", "text": "Safe blind pick: few popular counters"})
    if comfort:
        reasons.append({"impact": comfort, "kind": "comfort", "text": "In your champion pool"})
    reasons.sort(key=lambda r: -abs(r["impact"]))
    for r in reasons:
        r["impact"] = _r(r["impact"])

    main = cd.main_lane(champ)
    return {
        "champion": champ,
        "lane": lane,
        "role": role,
        "main_role": cd.LANE_TO_ROLE.get(main, role),
        "off_role": main is not None and main != lane,
        "niche": s.get("pick_rate", 0.0) < NICHE_PICK_RATE,
        "estimate": _r(50.0 + total, 1),
        "breakdown": {
            "meta": _r(meta), "matchups": _r(matchup_total), "synergy": _r(synergy_total),
            "composition": _r(comp), "blind_risk": _r(blind), "comfort": _r(comfort),
        },
        "stats": {
            "win_rate": s.get("win_rate"), "lane_avg_wr": _r(avg), "pick_rate": s.get("pick_rate"),
            "ban_rate": s.get("ban_rate"), "games": s.get("games"), "tier": s.get("tier_letter") or "",
            "rank": s.get("rank") or None,
        },
        "matchups": matchups[:6],
        "synergies": synergies[:5],
        "counters": counters,
        "reasons": reasons[:6],
        "in_pool": in_pool,
        "lane_opponent_known": p_open < 0.5,
        "confidence": _confidence(s.get("games", 0)),
    }


def rank_candidates(draft):
    """Every eligible champion for the local player, best first (each in its best open lane)."""
    open_lanes = [draft.my_lane] if draft.my_lane else draft.open_lanes()
    results = []
    for champ in cd.champions:
        if champ in draft.taken:
            continue
        if draft.available is not None and champ not in draft.available:
            continue
        if draft.pool_only and champ not in draft.pool:
            continue
        best = None
        for lane in cd.playable_lanes(champ):
            if lane not in open_lanes:
                continue
            r = score(draft, champ, lane)
            if not r or (r["niche"] and not draft.include_niche and not r["in_pool"]):
                continue
            if best is None or r["estimate"] > best["estimate"]:
                best = r
        if best:
            results.append(best)
    results.sort(key=lambda r: -r["estimate"])
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results


def suggest(draft, count=10):
    return rank_candidates(draft)[:count]


def evaluate_pick(draft, champ, ranked=()):
    """Score a specific champion in the player's lane, even an off-meta one."""
    if not champ or champ not in cd.champions:
        return None
    lanes = [draft.my_lane] if draft.my_lane else (cd.playable_lanes(champ) or [cd.main_lane(champ)])
    best = None
    for lane in lanes:
        if not lane:
            continue
        r = score(draft, champ, lane, min_games=1)
        if r and (best is None or r["estimate"] > best["estimate"]):
            best = r
    if best:
        best["rank"] = 1 + sum(1 for x in ranked if x["estimate"] > best["estimate"])
    return best


# ---------------------------------------------------------------------------
# Bans
# ---------------------------------------------------------------------------

def _enemy_open_lanes(draft):
    return {l: max(0.0, 1.0 - draft.enemy_roles.lane_filled(l)) for l in LANES}


def ban_lanes(draft):
    """The player's lane while the enemy laner is unknown, otherwise every lane the enemy hasn't filled."""
    open_for_enemy = _enemy_open_lanes(draft)
    if draft.my_lane and open_for_enemy[draft.my_lane] > 0.3:
        return [draft.my_lane]
    return [l for l in LANES if open_for_enemy[l] > 0.05]


def suggest_bans(draft, count=8):
    """
    Champions worth banning, ranked by expected win-rate swing per game:
    (chance the enemy still picks them into a lane) x (their strength + how hard
    they beat the player's pool), over the lanes from ban_lanes().
    """
    open_for_enemy = _enemy_open_lanes(draft)
    lanes = ban_lanes(draft)
    pool_by_lane = {l: [p for p in draft.pool if l in cd.playable_lanes(p)] for l in lanes}
    results = []
    for champ in cd.champions:
        if champ in draft.taken or champ in draft.pool or champ == draft.my_pick:
            continue
        value, best = 0.0, None
        for lane in lanes:
            s = cd.lane_stats(champ, lane)
            if not s or s["games"] < MIN_LANE_GAMES:
                continue
            strength = shrink(s["win_rate"] - cd.lane_avg_wr(lane), s["games"], K_META)
            beats = []
            for mine in pool_by_lane[lane]:
                eff, raw = matchup_effect(mine, lane, champ, lane)
                if raw:
                    beats.append((-eff, mine))
            pool_threat = sum(v for v, _ in beats) / len(beats) if beats else 0.0
            lane_value = open_for_enemy[lane] * s["pick_rate"] / 100.0 * (strength + pool_threat)
            if lane_value <= 0:
                continue
            value += lane_value
            if best is None or lane_value > best["value"]:
                beats.sort(reverse=True)
                best = {"lane": lane, "value": lane_value, "stats": s, "strength": strength,
                        "beats": [{"champion": m, "impact": _r(v)} for v, m in beats if v >= 0.3][:3]}
        if best:
            s = best["stats"]
            reasons = []
            tier = s.get("tier_letter") or ""
            reasons.append(f"{tier + ' tier, ' if tier else ''}{s['win_rate']:.1f}% win rate, "
                           f"picked in {s['pick_rate']:.1f}% of {cd.LANE_TO_ROLE[best['lane']]} games")
            if best["beats"]:
                reasons.append("Beats your " + ", ".join(b["champion"] for b in best["beats"]))
            results.append({
                "champion": champ, "lane": best["lane"], "role": cd.LANE_TO_ROLE[best["lane"]],
                "value": _r(value, 3), "tier": tier, "win_rate": s.get("win_rate"),
                "pick_rate": s.get("pick_rate"), "ban_rate": s.get("ban_rate"),
                "beats_pool": best["beats"], "reasons": reasons,
            })
    results.sort(key=lambda r: -r["value"])
    return results[:count]


# ---------------------------------------------------------------------------
# Team analysis & draft outlook
# ---------------------------------------------------------------------------

def ally_team_roles(draft):
    """Lane inference for the whole allied team, including the player's own pick."""
    if draft.my_pick:
        team = draft.allies + [(draft.my_pick, draft.my_lane)]
        return infer_roles([n for n, _ in team], {n: l for n, l in team if l})
    return draft.ally_roles(draft.my_lane)


def team_summary(roles, side, me=""):
    """Composition summary for one team. side is 'ally' or 'enemy' (changes the advice)."""
    names = roles.champions
    picks = [{
        "champion": n, "lane": roles.assignment[n], "role": cd.LANE_TO_ROLE[roles.assignment[n]],
        "probability": _r(roles.probability(n, roles.assignment[n])), "pinned": n in roles.pinned,
        "is_me": n == me,
    } for n in names]
    if not names:
        return {"picks": [], "damage": None, "frontline": 0, "crowd_control": None, "notes": []}

    profiles = [cd.damage_profile(n, roles.assignment[n]) for n in names]
    total = sum(sum(p.values()) for p in profiles) or 1.0
    damage = {k: _r(sum(p[k] for p in profiles) / total) for k in ("physical", "magic", "true")}
    magic_share = _magic_share(profiles)
    frontline = sum(1 for n in names if cd.is_frontline(n))
    cc = sum(cd.attributes(n)["crowd_control"] for n in names) / len(names)
    melee = sum(1 for n in names if cd.attributes(n)["attack_type"] == "melee")

    notes = []
    if len(names) >= 3:
        if magic_share < 0.25:
            notes.append("Mostly physical damage - armor stacking hurts" if side == "ally"
                         else "Mostly physical damage - armor is valuable")
        elif magic_share > 0.75:
            notes.append("Mostly magic damage - magic resist stacking hurts" if side == "ally"
                         else "Mostly magic damage - magic resist is valuable")
        if frontline == 0:
            notes.append("No frontline" if side == "ally" else "No frontline - they are vulnerable to dive")
        if cc < 1.6:
            notes.append("Little crowd control" if side == "ally" else "Little crowd control - easy to kite")
        elif cc >= 2.4 and side == "enemy":
            notes.append("Heavy crowd control - consider cleanse / tenacity")
    return {
        "picks": picks,
        "damage": damage,
        "frontline": frontline,
        "crowd_control": _r(cc, 1),
        "melee": melee,
        "ranged": len(names) - melee,
        "notes": notes,
    }


def _team_synergy(roles):
    """Expected sum of pairwise synergy inside one team, over its lane assignments."""
    names = roles.champions
    if len(names) < 2:
        return 0.0
    cache = {}
    total = 0.0
    for perm, p in roles.perms:
        s = 0.0
        for (i, a), (j, b) in combinations(enumerate(names), 2):
            key = (a, perm[i], b, perm[j])
            if key not in cache:
                cache[key] = synergy_effect(a, perm[i], b, perm[j])[0]
            s += cache[key]
        total += p * s
    return total


def draft_outlook(draft, ally_roles=None):
    """Win chance implied by the picks on both sides (needs at least one pick per team)."""
    ally_roles = ally_roles or ally_team_roles(draft)
    if not ally_roles.champions or not draft.enemy_names:
        return None
    enemy_roles = draft.enemy_roles

    def strength(roles):
        return sum(p * meta_strength(n, l)
                   for n, dist in roles.marginals.items() for l, p in dist.items() if p >= MIN_ROLE_PROBABILITY)

    ally_strength, enemy_strength = strength(ally_roles), strength(enemy_roles)
    matchups = 0.0
    for a, adist in ally_roles.marginals.items():
        for e, edist in enemy_roles.marginals.items():
            for al, pa in adist.items():
                if pa < MIN_ROLE_PROBABILITY:
                    continue
                for el, pe in edist.items():
                    if pe < MIN_ROLE_PROBABILITY:
                        continue
                    matchups += pa * pe * matchup_effect(a, al, e, el)[0]
    synergy = _team_synergy(ally_roles) - _team_synergy(enemy_roles)
    total = ally_strength - enemy_strength + matchups + synergy
    return {
        "win_chance": _r(max(OUTLOOK_MIN, min(OUTLOOK_MAX, 50.0 + total)), 1),
        "strength": _r(ally_strength - enemy_strength),
        "matchups": _r(matchups),
        "synergy": _r(synergy),
        "ally_picks": len(ally_roles.champions),
        "enemy_picks": len(draft.enemy_names),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def analyze(draft, count=10, ban_count=8):
    """Everything the UI shows for one draft state."""
    ranked = rank_candidates(draft)
    my_pick = None
    if draft.my_pick:
        my_pick = (next((r for r in ranked if r["champion"] == draft.my_pick), None)
                   or evaluate_pick(draft, draft.my_pick, ranked))
    ally_roles = ally_team_roles(draft)
    return {
        "lane": draft.my_lane,
        "role": cd.LANE_TO_ROLE.get(draft.my_lane) if draft.my_lane else None,
        "open_roles": [cd.LANE_TO_ROLE[l] for l in draft.open_lanes()],
        "suggestions": ranked[:count],
        "eligible": len(ranked),
        "my_pick": my_pick,
        "bans": suggest_bans(draft, ban_count),
        "ban_roles": [cd.LANE_TO_ROLE[l] for l in ban_lanes(draft)],
        "teams": {
            "ally": team_summary(ally_roles, "ally", me=draft.my_pick),
            "enemy": team_summary(draft.enemy_roles, "enemy"),
        },
        "outlook": draft_outlook(draft, ally_roles),
        "has_matchups": cd.has_matchup_data(),
    }
