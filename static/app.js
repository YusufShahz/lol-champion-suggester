// Champion Suggester front end: draft board, champion picker, suggestions and live client sync.

const BOOT = JSON.parse(document.getElementById('bootstrap').textContent);

const LANES = ['top', 'jungle', 'middle', 'bottom', 'support'];
const ROLES = ['Top', 'Jungle', 'Mid', 'ADC', 'Support'];
const LANE_OF = { Top: 'top', Jungle: 'jungle', Mid: 'middle', ADC: 'bottom', Support: 'support' };
const ROLE_OF = { top: 'Top', jungle: 'Jungle', middle: 'Mid', bottom: 'ADC', support: 'Support' };
const STORAGE_KEY = 'champion-suggester:v2';
const DRAFT_TTL_MS = 3 * 60 * 60 * 1000;
const PIN_MIN_SHARE = 5;        // % of games in a lane before a row click pins a champion there
const STALE_DATA_DAYS = 10;
const DD_VERSION = BOOT.data.ddragon_version || '16.18.1';

const BRACKETS = {
    all: 'All ranks', emerald_plus: 'Emerald+', platinum_plus: 'Platinum+', diamond_plus: 'Diamond+',
    d2_plus: 'Diamond 2+', master_plus: 'Master+', gold_plus: 'Gold+', silver: 'Silver', gold: 'Gold',
    platinum: 'Platinum', emerald: 'Emerald', diamond: 'Diamond', master: 'Master',
};
const GAMEFLOW = {
    None: 'Home', Lobby: 'In lobby', Matchmaking: 'In queue', ReadyCheck: 'Match found',
    ChampSelect: 'Champion select', GameStart: 'Game starting', InProgress: 'In game',
    Reconnect: 'Reconnect', WaitingForStats: 'Post-game', PreEndOfGame: 'Post-game', EndOfGame: 'Post-game',
};
const ALIASES = {
    asol: 'Aurelion Sol', j4: 'Jarvan IV', ww: 'Warwick', gp: 'Gangplank', lb: 'LeBlanc',
    mundo: 'Dr. Mundo', kass: 'Kassadin', morde: 'Mordekaiser', noc: 'Nocturne', cait: 'Caitlyn',
};

const ROLE_ICONS = {
    Auto: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 6.8l1.5 3.7 3.7 1.5-3.7 1.5-1.5 3.7-1.5-3.7-3.7-1.5 3.7-1.5z" fill="currentColor"/></svg>',
    Top: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 3h14.5l-3.8 3.8H6.8v6.9L3 17.5z" fill="currentColor"/><path d="M21 6.5V21H6.5l3.8-3.8h6.9v-6.9z" fill="currentColor" opacity=".32"/><path d="M9.6 9.6h4.8v4.8H9.6z" fill="currentColor" opacity=".32"/></svg>',
    Jungle: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12.4 2.2c2.3 3.1 3.3 6.4 3 9.8-.3 3.3-1.8 6.3-4.4 9.8.5-3.2.4-6.1-.4-8.8-.7-2.5-.6-5.4 1.8-10.8z" fill="currentColor"/><path d="M6.1 5.2c1.9 2.3 2.8 4.8 2.8 7.4 0 2.3-.7 4.6-2.2 6.9-.1-2.2-.5-4.1-1.3-5.9-.9-1.9-.8-4.5.7-8.4zM18.4 6.4c1.2 2.1 1.6 4.2 1.4 6.4-.2 2-1 3.9-2.4 5.8.1-1.9 0-3.6-.4-5.1-.4-1.7-.1-4 1.4-7.1z" fill="currentColor" opacity=".55"/></svg>',
    Mid: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16.5 3H21v4.5L7.5 21H3v-4.5z" fill="currentColor"/><path d="M3 3h10l-3.5 3.5H6.5v3L3 13zM21 11v10H11l3.5-3.5h3v-3z" fill="currentColor" opacity=".32"/></svg>',
    ADC: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 21H6.5l3.8-3.8h6.9v-6.9L21 6.5z" fill="currentColor"/><path d="M3 17.5V3h14.5l-3.8 3.8H6.8v6.9z" fill="currentColor" opacity=".32"/><path d="M9.6 9.6h4.8v4.8H9.6z" fill="currentColor" opacity=".32"/></svg>',
    Support: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9.3 3.4h5.4l-1.2 3.4h-3z" fill="currentColor"/><path d="M12 8.2l3.2 3L12 20.6l-3.2-9.4z" fill="currentColor"/><path d="M1.8 7.6h6.7l1.7 2.6-2.9 3.3-3.5-1.4zM22.2 7.6h-6.7l-1.7 2.6 2.9 3.3 3.5-1.4z" fill="currentColor" opacity=".6"/></svg>',
};
const ICON = {
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
    chevron: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    ban: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="7.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M6.8 6.8l10.4 10.4" stroke="currentColor" stroke-width="2"/></svg>',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function norm(s) {
    return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function words(s) {
    return String(s).split(/[\s'.&]+/).map(norm).filter(Boolean);
}

function initials(s) {
    return words(s).map(w => w[0]).join('');
}

function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function signed(x, digits = 1) {
    const v = Number(x) || 0;
    const s = Math.abs(v).toFixed(digits);
    if (Number(s) === 0) return (0).toFixed(digits);
    return (v > 0 ? '+' : '−') + s;
}

const pct = (x, d = 1) => (x == null ? '–' : `${Number(x).toFixed(d)}%`);
const int = x => (x == null ? '–' : Math.round(x).toLocaleString());
const compact = x => (x == null ? '–' : x >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : x >= 1e4 ? `${Math.round(x / 1e3)}k` : int(x));
const tierClass = t => (t ? `t-${t[0].toLowerCase()}` : '');
const signClass = (v, eps = 0.005) => (v > eps ? 'pos' : v < -eps ? 'neg' : 'zero');

function estClass(e) {
    return e >= 54 ? 'great' : e >= 52 ? 'good' : e >= 49.5 ? 'ok' : e >= 47.5 ? 'meh' : 'bad';
}

function fmtDate(iso) {
    if (!iso) return 'unknown';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? 'unknown' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function lolalyticsSlug(name) {
    const s = name.toLowerCase();
    if (s.startsWith('nunu')) return 'nunu';
    if (s.startsWith('renata')) return 'renata';
    return s.replace(/['.& ]/g, '');
}

const CHAMPS = BOOT.champions.map(c => ({ ...c, key: norm(c.name), initials: initials(c.name), words: words(c.name) }));
const BY_NAME = new Map(CHAMPS.map(c => [c.name, c]));

function iconUrl(name) {
    const c = BY_NAME.get(name);
    return c && c.icon ? `https://ddragon.leagueoflegends.com/cdn/${DD_VERSION}/img/champion/${c.icon}.png` : '';
}

function splashUrl(name) {
    const c = BY_NAME.get(name);
    return c && c.icon ? `https://ddragon.leagueoflegends.com/cdn/img/champion/centered/${c.icon}_0.jpg` : '';
}

/** Image in a wrapper that shows the champion's initials if the image can't load. */
function imgBox(name, cls = '') {
    const url = iconUrl(name);
    const letters = esc(initials(name).toUpperCase().slice(0, 2));
    return `<span class="${cls} img-wrap${url ? '' : ' broken'}" data-initials="${letters}">${url ? `<img src="${url}" alt="" loading="lazy" decoding="async">` : ''}</span>`;
}

function mainLane(name) {
    const c = BY_NAME.get(name);
    if (!c) return null;
    const lanes = Object.entries(c.lanes || {});
    if (lanes.length) return lanes.sort((a, b) => b[1] - a[1])[0][0];
    return c.roles && c.roles.length ? LANE_OF[c.roles[0]] : null;
}

function laneShare(name, lane) {
    return (BY_NAME.get(name)?.lanes || {})[lane] || 0;
}

const htmlCache = new WeakMap();
function setHtml(target, html) {
    const el = typeof target === 'string' ? $(target) : target;
    if (!el || htmlCache.get(el) === html) return false;
    htmlCache.set(el, html);
    el.innerHTML = html;
    return true;
}

function toast(message, kind = '') {
    const el = document.createElement('div');
    el.className = `toast ${kind}`;
    el.textContent = message;
    $('#toasts').appendChild(el);
    setTimeout(() => {
        el.classList.add('leaving');
        el.addEventListener('animationend', () => el.remove(), { once: true });
    }, 3200);
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

function loadSaved() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        return {};
    }
}

function cleanNames(list, max) {
    const out = [];
    for (const n of Array.isArray(list) ? list : []) {
        if (BY_NAME.has(n) && !out.includes(n)) out.push(n);
    }
    return out.slice(0, max);
}

function cleanMembers(list, max) {
    const out = [];
    for (const m of Array.isArray(list) ? list : []) {
        if (m && BY_NAME.has(m.champion) && !out.some(o => o.champion === m.champion)) {
            out.push({ champion: m.champion, role: ROLES.includes(m.role) ? m.role : '', state: '', source: m.role ? 'user' : '' });
        }
    }
    return out.slice(0, max);
}

const saved = loadSaved();
const savedDraft = saved.draft && Date.now() - (saved.draft.at || 0) < DRAFT_TTL_MS ? saved.draft : {};
const num = (v, lo, hi, dflt) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Math.min(hi, Math.max(lo, Number(v))) : dflt);

const state = {
    myRole: ROLES.includes(savedDraft.myRole) ? savedDraft.myRole : '',
    myPick: BY_NAME.has(savedDraft.myPick) ? savedDraft.myPick : '',
    myPickState: '',
    allies: cleanMembers(savedDraft.allies, 4),
    enemies: cleanMembers(savedDraft.enemies, 5),
    bans: { ally: cleanNames(savedDraft.bans?.ally, 5), enemy: cleanNames(savedDraft.bans?.enemy, 5) },
    pins: { ally: {}, enemy: {} },
    view: 'picks',
    count: BOOT.defaults.count,
    prefs: {
        pool: cleanNames(saved.prefs?.pool, 80),
        poolOnly: saved.prefs?.poolOnly === true,
        ownedOnly: saved.prefs?.ownedOnly !== false,
        includeNiche: saved.prefs?.includeNiche === true,
        comfort: num(saved.prefs?.comfort, 0, BOOT.defaults.max_comfort, BOOT.defaults.comfort),
        live: saved.prefs?.live !== false,
    },
    client: { type: 'offline' },
    owned: null,
    pickable: null,
    analysis: null,
    loading: false,
    error: '',
    expanded: new Set(),
};

const sync = { gameId: null, clientRole: null, clientPick: null, actionKey: '' };

function save() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
            prefs: state.prefs,
            draft: {
                at: Date.now(),
                myRole: state.myRole,
                myPick: state.myPick,
                allies: state.allies.filter(m => m.champion).map(({ champion, role }) => ({ champion, role })),
                enemies: state.enemies.filter(m => m.champion).map(({ champion, role }) => ({ champion, role })),
                bans: state.bans,
            },
        }));
    } catch {
        /* storage full or disabled: the app still works, it just won't remember */
    }
}

const members = side => (side === 'ally' ? state.allies : state.enemies);
const available = () => state.pickable || state.owned;
const connected = () => state.client.type === 'connected' || state.client.type === 'champ_select';

function isBanned(name) {
    return state.bans.ally.includes(name) || state.bans.enemy.includes(name);
}

function takenReason(name) {
    if (isBanned(name)) return 'Banned';
    if (state.myPick === name) return 'You';
    if (state.allies.some(m => m.champion === name)) return 'Ally';
    if (state.enemies.some(m => m.champion === name)) return 'Enemy';
    return '';
}

/** A champion can only be in one place in a draft. */
function removeEverywhere(name) {
    state.allies = state.allies.filter(m => m.champion !== name);
    state.enemies = state.enemies.filter(m => m.champion !== name);
    state.bans.ally = state.bans.ally.filter(n => n !== name);
    state.bans.enemy = state.bans.enemy.filter(n => n !== name);
    if (state.myPick === name) {
        state.myPick = '';
        state.myPickState = '';
    }
}

function commit({ analyze = true } = {}) {
    save();
    render();
    if (analyze) scheduleAnalysis();
}

// ---------------------------------------------------------------------------
// Analysis requests
// ---------------------------------------------------------------------------

let analyzeTimer = 0;
let inflight = null;
let freshUntil = 0;

function payload() {
    const list = side => members(side).filter(m => m.champion).map(m => ({ champion: m.champion, role: m.role || '' }));
    const body = {
        my_role: state.myRole,
        my_pick: state.myPick,
        allies: list('ally'),
        enemies: list('enemy'),
        bans: [...state.bans.ally, ...state.bans.enemy],
        pool: state.prefs.pool,
        pool_only: state.prefs.poolOnly && state.prefs.pool.length > 0,
        comfort: state.prefs.comfort,
        include_niche: state.prefs.includeNiche,
        count: state.count,
        ban_count: 10,
    };
    if (state.prefs.ownedOnly && available()?.length) body.available = available();
    return body;
}

function scheduleAnalysis(delay = 70) {
    clearTimeout(analyzeTimer);
    analyzeTimer = setTimeout(analyze, delay);
}

async function analyze() {
    if (inflight) inflight.abort();
    const ctrl = new AbortController();
    inflight = ctrl;
    setLoading(true);
    try {
        const res = await fetch('/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload()),
            signal: ctrl.signal,
        });
        if (!res.ok) throw new Error(`The suggestion server answered with an error (${res.status}).`);
        state.analysis = await res.json();
        state.error = '';
        freshUntil = Date.now() + 450;
    } catch (err) {
        if (err.name === 'AbortError') return;
        state.error = err instanceof TypeError
            ? 'Could not reach the app server. Is app.py still running?'
            : err.message;
    } finally {
        if (inflight === ctrl) {
            inflight = null;
            setLoading(false);
            render();
        }
    }
}

function setLoading(on) {
    state.loading = on;
    $('#progress').hidden = !on;
    $('#results').classList.toggle('stale', on && !!state.analysis);
}

// ---------------------------------------------------------------------------
// Draft edits
// ---------------------------------------------------------------------------

function addMember(side, name, lane) {
    removeEverywhere(name);
    const list = members(side);
    const placeholder = lane && list.find(m => !m.champion && m.role === ROLE_OF[lane]);
    if (placeholder) {
        placeholder.champion = name;
    } else {
        const max = side === 'ally' ? 4 : 5;
        if (list.filter(m => m.champion).length >= max) {
            toast(side === 'ally' ? 'Your team already has four allies.' : 'The enemy team is full.', 'bad');
            return;
        }
        const pin = lane && laneShare(name, lane) >= PIN_MIN_SHARE ? ROLE_OF[lane] : '';
        list.push({ champion: name, role: pin, state: '', source: pin ? 'user' : '' });
        if (pin) state.pins[side][name] = pin;
    }
    commit();
}

function replaceMember(side, oldName, name, lane) {
    if (oldName === name) return;
    const role = members(side).find(m => m.champion === oldName)?.role || '';
    removeEverywhere(name);
    const member = members(side).find(m => m.champion === oldName);
    if (member) {
        member.champion = name;
        member.state = '';
        member.role = role || (lane && laneShare(name, lane) >= PIN_MIN_SHARE ? ROLE_OF[lane] : '');
    } else {
        addMember(side, name, lane);
        return;
    }
    commit();
}

function removeMember(side, name) {
    if (side === 'ally') state.allies = state.allies.filter(m => m.champion !== name);
    else state.enemies = state.enemies.filter(m => m.champion !== name);
    delete state.pins[side][name];
    commit();
}

function setMyPick(name) {
    if (name) removeEverywhere(name);
    state.myPick = name;
    state.myPickState = '';
    commit();
}

function setMyRole(role) {
    const old = state.myRole;
    if (role === old) return;
    if (role) {
        for (const m of state.allies) {
            if (m.role === role) {
                m.role = old || '';
                if (m.role) state.pins.ally[m.champion] = m.role;
                else delete state.pins.ally[m.champion];
            }
        }
    }
    state.myRole = role;
    state.expanded.clear();
    commit();
}

function setMemberRole(side, name, role) {
    const list = members(side);
    const member = list.find(m => m.champion === name);
    if (!member) return;
    const rows = teamRows(side);
    const fromLane = LANES.find(l => rows[l] && !rows[l].me && rows[l].champion === name) || null;
    if (role) {
        const target = rows[LANE_OF[role]];
        if (target && target.me) {
            state.myRole = fromLane ? ROLE_OF[fromLane] : '';
        } else if (target && target.champion && target.champion !== name) {
            const other = list.find(m => m.champion === target.champion);
            if (other) {
                other.role = fromLane ? ROLE_OF[fromLane] : '';
                other.source = other.role ? 'user' : '';
                if (other.role) state.pins[side][other.champion] = other.role;
                else delete state.pins[side][other.champion];
            }
        }
    }
    member.role = role;
    member.source = role ? 'user' : '';
    if (role) state.pins[side][name] = role;
    else delete state.pins[side][name];
    commit();
}

function addBan(side, name) {
    removeEverywhere(name);
    const other = side === 'ally' ? 'enemy' : 'ally';
    if (state.bans[side].length < 5) state.bans[side].push(name);
    else if (state.bans[other].length < 5) state.bans[other].push(name);
    else {
        toast('All ten ban slots are full.', 'bad');
        return;
    }
    commit();
}

function removeBan(side, name) {
    state.bans[side] = state.bans[side].filter(n => n !== name);
    commit();
}

function togglePool(name) {
    const pool = state.prefs.pool;
    const i = pool.indexOf(name);
    if (i >= 0) pool.splice(i, 1);
    else pool.push(name);
}

function resetDraft() {
    state.allies = [];
    state.enemies = [];
    state.bans = { ally: [], enemy: [] };
    state.pins = { ally: {}, enemy: {} };
    state.myPick = '';
    state.myPickState = '';
    state.expanded.clear();
    state.count = BOOT.defaults.count;
    commit();
}

// ---------------------------------------------------------------------------
// Team board
// ---------------------------------------------------------------------------

/**
 * Which champion goes in which lane row: client-assigned and pinned roles
 * first, then the server's role inference, then the champion's main lane.
 */
function teamRows(side) {
    const rows = Object.fromEntries(LANES.map(l => [l, null]));
    const inferred = new Map((state.analysis?.teams?.[side]?.picks || []).map(p => [p.champion, p]));
    const queue = [];
    if (side === 'ally' && (state.myPick || state.myRole)) {
        queue.push({ champion: state.myPick, role: state.myRole, state: state.myPickState, me: true });
    }
    queue.push(...members(side));

    const second = [];
    for (const m of queue) {
        const lane = LANE_OF[m.role];
        if (lane && !rows[lane]) rows[lane] = { ...m, lane, pinned: true };
        else second.push(m);
    }
    const third = [];
    for (const m of second) {
        const p = m.champion ? inferred.get(m.champion) : null;
        if (p && !rows[p.lane]) rows[p.lane] = { ...m, lane: p.lane, probability: p.probability };
        else third.push(m);
    }
    for (const m of third) {
        if (!m.champion) continue;
        const lane = [mainLane(m.champion), ...LANES].find(l => l && !rows[l]);
        if (lane) rows[lane] = { ...m, lane };
    }
    return rows;
}

function slotSub(m, role) {
    const bits = [role];
    if (m.me) bits.push(m.pinned ? (state.client.type === 'champ_select' && sync.clientRole === state.myRole ? 'assigned' : 'your role') : 'auto');
    else if (m.pinned) bits.push(m.source === 'client' ? 'assigned' : 'pinned');
    else if (m.probability != null) bits.push(`${Math.round(m.probability * 100)}% likely`);
    return bits.join(' · ');
}

function stateTag(m) {
    return m.state === 'hovering' || m.state === 'intent' ? '<span class="hover-tag" title="Hovering, not locked in">hover</span>' : '';
}

function slotHtml(side, lane, m) {
    const role = ROLE_OF[lane];
    const myTurn = state.client.type === 'champ_select' && state.client.action?.is_mine && state.client.action.type === 'pick';
    const opponent = side === 'enemy' && state.myRole && LANE_OF[state.myRole] === lane;

    if (m && m.me) {
        const roleBtn = `<button type="button" class="slot-role" data-action="role-menu" data-side="ally" data-me="1" title="Your role: ${role}. Click to change">${ROLE_ICONS[role]}</button>`;
        if (!m.champion) {
            return `<li class="slot me empty${myTurn ? ' active-turn' : ''}">${roleBtn}
                <button type="button" class="slot-body" data-action="pick-me">
                    <span class="portrait empty">+</span>
                    <span class="slot-text"><span class="slot-name">Your pick</span><span class="slot-sub">${role} · click to choose</span></span>
                </button></li>`;
        }
        const hovering = m.state === 'hovering' || m.state === 'intent';
        return `<li class="slot me filled pinned${hovering ? ' hovering' : ''}${myTurn ? ' active-turn' : ''}">${roleBtn}
            <button type="button" class="slot-body" data-action="pick-me" title="Change your champion">
                ${imgBox(m.champion, 'portrait')}
                <span class="slot-text"><span class="slot-name"><span class="name-text">${esc(m.champion)}</span><span class="you-tag">You</span>${stateTag(m)}</span><span class="slot-sub">${slotSub(m, role)}</span></span>
            </button>
            <button type="button" class="slot-clear" data-action="clear-me" aria-label="Clear your pick">${ICON.close}</button></li>`;
    }

    if (!m || !m.champion) {
        const waiting = m && !m.champion;
        const label = waiting ? 'Picking…' : side === 'ally' ? 'Add ally' : 'Add enemy';
        return `<li class="slot empty${opponent ? ' opponent' : ''}">
            <span class="slot-role" title="${role}">${ROLE_ICONS[role]}</span>
            <button type="button" class="slot-body" data-action="add" data-side="${side}" data-lane="${lane}">
                <span class="portrait empty">+</span>
                <span class="slot-text"><span class="slot-name">${label}</span><span class="slot-sub">${role}${opponent ? ' · your lane opponent' : ''}</span></span>
            </button></li>`;
    }

    const hovering = m.state === 'hovering' || m.state === 'intent';
    const name = esc(m.champion);
    return `<li class="slot filled${m.pinned ? ' pinned' : ''}${hovering ? ' hovering' : ''}${opponent ? ' opponent' : ''}">
        <button type="button" class="slot-role" data-action="role-menu" data-side="${side}" data-name="${name}" title="${role}${m.pinned ? '' : ' (guessed)'}. Click to set the role">${ROLE_ICONS[role]}</button>
        <button type="button" class="slot-body" data-action="replace" data-side="${side}" data-name="${name}" data-lane="${lane}" title="Replace ${name}">
            ${imgBox(m.champion, 'portrait')}
            <span class="slot-text"><span class="slot-name"><span class="name-text">${name}</span>${opponent ? '<span class="opp-tag" title="Your lane opponent">vs you</span>' : ''}${stateTag(m)}</span><span class="slot-sub">${slotSub(m, role)}</span></span>
        </button>
        <button type="button" class="slot-clear" data-action="remove" data-side="${side}" data-name="${name}" aria-label="Remove ${name}">${ICON.close}</button></li>`;
}

function compHtml(summary) {
    if (!summary || !summary.picks || !summary.picks.length || !summary.damage) return '';
    const d = summary.damage;
    const w = x => `${(x * 100).toFixed(1)}%`;
    const p = x => `${Math.round(x * 100)}%`;
    const notes = summary.notes.length ? `<ul class="comp-notes">${summary.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>` : '';
    return `<div class="comp-title"><span>Composition</span><span>${summary.picks.length}/5</span></div>
        <div class="dmg-bar" title="Damage split"><span class="physical" style="width:${w(d.physical)}"></span><span class="magic" style="width:${w(d.magic)}"></span><span class="true" style="width:${w(d.true)}"></span></div>
        <div class="dmg-legend"><span><i style="background:var(--physical)"></i>Physical ${p(d.physical)}</span><span><i style="background:var(--magic)"></i>Magic ${p(d.magic)}</span><span><i style="background:var(--true)"></i>True ${p(d.true)}</span></div>
        <div class="comp-stats">
            <div class="comp-stat" title="Tanks and other durable champions"><b>${summary.frontline}</b><span>Frontline</span></div>
            <div class="comp-stat" title="Average crowd control rating (1-3) from the League client"><b>${Number(summary.crowd_control).toFixed(1)}</b><span>CC rating</span></div>
            <div class="comp-stat" title="${summary.melee} melee, ${summary.ranged} ranged"><b>${summary.ranged} / ${summary.picks.length}</b><span>Ranged</span></div>
        </div>${notes}`;
}

function renderTeams() {
    for (const side of ['ally', 'enemy']) {
        const rows = teamRows(side);
        setHtml(`#${side}Slots`, LANES.map(l => slotHtml(side, l, rows[l])).join(''));
        const filled = LANES.filter(l => rows[l] && rows[l].champion).length;
        $(`#${side}Meta`).textContent = `${filled}/5 picked`;
        setHtml(`#${side}Comp`, compHtml(state.analysis?.teams?.[side]));
    }
}

function renderBans() {
    for (const side of ['ally', 'enemy']) {
        const list = state.bans[side];
        const html = Array.from({ length: 5 }, (_, i) => {
            const name = list[i];
            if (!name) return `<button type="button" class="ban-slot" data-action="add-ban" data-side="${side}" title="Add a ban" aria-label="Add a ban">${ICON.ban}</button>`;
            const url = iconUrl(name);
            return `<button type="button" class="ban-slot filled img-wrap${url ? '' : ' broken'}" data-action="unban" data-side="${side}" data-name="${esc(name)}" data-initials="${esc(initials(name).toUpperCase().slice(0, 2))}" title="${esc(name)} banned. Click to remove">${url ? `<img src="${url}" alt="${esc(name)}" loading="lazy">` : ''}<span class="ban-x">×</span></button>`;
        }).join('');
        setHtml(`#${side}Bans`, html);
    }
}

// ---------------------------------------------------------------------------
// Center column
// ---------------------------------------------------------------------------

function renderRoleSelect() {
    const fromClient = state.client.type === 'champ_select' && sync.clientRole && sync.clientRole === state.myRole;
    const opts = [['', 'Auto'], ...ROLES.map(r => [r, r])];
    setHtml('#roleSelect', opts.map(([value, label]) => {
        const checked = state.myRole === value;
        const title = value ? `Suggest ${label} champions` : 'Suggest champions for any role your team still needs';
        return `<button type="button" role="radio" aria-checked="${checked}" data-role="${value}" title="${title}">${ROLE_ICONS[value || 'Auto']}<span>${label}</span>${checked && fromClient ? '<i class="from-client" title="Assigned by the League client"></i>' : ''}</button>`;
    }).join(''));
}

function renderViewSelect() {
    for (const b of $$('#viewSelect button')) b.setAttribute('aria-selected', String(b.dataset.view === state.view));
}

function renderFilters() {
    $('#poolOnly').checked = state.prefs.poolOnly;
    $('#includeNiche').checked = state.prefs.includeNiche;
    $('#ownedOnly').checked = state.prefs.ownedOnly;
    $('#ownedToggle').hidden = !available();
    const a = state.analysis;
    let info = '';
    if (a && state.view === 'picks') info = `${a.eligible} champion${a.eligible === 1 ? '' : 's'} considered`;
    $('#filtersInfo').textContent = info;
    $('#filters').hidden = state.view !== 'picks';
}

function reasonHtml(r) {
    const cls = r.impact > 0.05 ? 'up' : r.impact < -0.05 ? 'down' : '';
    const val = Math.abs(r.impact) >= 0.05 ? `<b>${signed(r.impact, 1)}</b>` : '';
    return `<li class="reason ${cls}" title="${esc(r.text)}"><span>${esc(r.text)}</span>${val}</li>`;
}

const PARTS = [
    ['meta', 'Champion strength'],
    ['matchups', 'Matchups'],
    ['synergy', 'Synergy'],
    ['composition', 'Team comp'],
    ['blind_risk', 'Counter-pick risk'],
    ['comfort', 'Comfort'],
];

function relRows(rows, withProbability = true) {
    return `<ul class="rel-list">${rows.map(r => {
        const where = withProbability ? `<small>${esc(r.role)}${r.probability < 0.95 ? ` · ${Math.round(r.probability * 100)}%` : ''}</small>` : '';
        const value = r.impact != null ? r.impact : r.delta;
        return `<li class="rel">${imgBox(r.champion, 'rel-img')}
            <span class="rel-name">${esc(r.champion)}${where}</span>
            <span class="rel-wr" title="${esc(int(r.games))} games">${pct(r.win_rate)}</span>
            <span class="rel-imp ${signClass(value)}">${signed(value, r.impact != null ? 2 : 1)}</span></li>`;
    }).join('')}</ul>`;
}

function detailsHtml(s) {
    const b = s.breakdown;
    const shown = PARTS.filter(([k]) => k !== 'comfort' || b.comfort);
    const max = Math.max(2, ...shown.map(([k]) => Math.abs(b[k] || 0)));
    const bars = shown.map(([k, label]) => {
        const v = b[k] || 0;
        const width = Math.min(50, (Math.abs(v) / max) * 50).toFixed(1);
        const fill = Math.abs(v) >= 0.005 ? `<span class="bd-fill ${v > 0 ? 'pos' : 'neg'}" style="width:${width}%"></span>` : '';
        return `<div class="bd-row"><span class="bd-label">${label}</span><span class="bd-bar">${fill}</span><span class="bd-val ${signClass(v)}">${signed(v, 2)}</span></div>`;
    }).join('');
    const st = s.stats;
    const sections = [`<div class="detail"><h4>Why ${s.estimate.toFixed(1)}%</h4>${bars}
        <p style="margin-top:8px">Win-rate points compared with an average pick. The average ${esc(s.role)} win rate in this bracket is ${pct(st.lane_avg_wr)}.</p></div>`];

    const hasEnemies = state.enemies.some(m => m.champion);
    sections.push(`<div class="detail"><h4>Matchups <small class="zero">win rate · impact</small></h4>${s.matchups.length ? relRows(s.matchups)
        : `<p>${hasEnemies ? 'Not enough games against these enemies yet.' : 'Add enemy picks to see matchups.'}</p>`}</div>`);
    if (state.allies.some(m => m.champion)) {
        sections.push(`<div class="detail"><h4>Synergy <small class="zero">win rate · impact</small></h4>${s.synergies.length ? relRows(s.synergies)
            : '<p>Not enough games together with your allies.</p>'}</div>`);
    }
    if (s.counters.length && !s.lane_opponent_known) {
        sections.push(`<div class="detail"><h4>Counter-picks to watch</h4>${relRows(s.counters, false)}
            <p style="margin-top:6px">Your lane opponent isn't known yet. These popular picks beat ${esc(s.champion)}.</p></div>`);
    }
    sections.push(`<div class="detail wide"><h4>This patch as ${esc(s.role)}</h4><div class="stat-grid">
        <div class="stat"><b>${pct(st.win_rate)}</b><span>Win rate</span></div>
        <div class="stat"><b>${pct(st.pick_rate)}</b><span>Pick rate</span></div>
        <div class="stat"><b>${pct(st.ban_rate)}</b><span>Ban rate</span></div>
        <div class="stat"><b>${compact(st.games)}</b><span>Games</span></div>
        <div class="stat"><b>${esc(st.tier || '–')}</b><span>Tier</span></div>
        <div class="stat"><b>${st.rank ? '#' + st.rank : '–'}</b><span>Role rank</span></div></div></div>`);

    const mine = s.champion === state.myPick;
    const inPool = state.prefs.pool.includes(s.champion);
    const name = esc(s.champion);
    sections.push(`<div class="detail-actions">
        <button type="button" class="btn small${mine ? ' active' : ''}" data-action="${mine ? 'clear-me' : 'preview'}" data-name="${name}">${mine ? 'Clear my pick' : 'Preview as my pick'}</button>
        <button type="button" class="btn small${inPool ? ' active' : ''}" data-action="toggle-pool" data-name="${name}">${inPool ? '★ In your pool' : '☆ Add to pool'}</button>
        <a class="btn small ghost" href="https://lolalytics.com/lol/${lolalyticsSlug(s.champion)}/build/?lane=${s.lane}" target="_blank" rel="noopener noreferrer">Build on Lolalytics ↗</a></div>`);
    return sections.join('');
}

function cardHtml(s, { featured = false, mine = false } = {}) {
    const key = (mine ? 'mine:' : '') + s.champion;
    const open = state.expanded.has(key);
    const tags = [];
    if (!mine && s.champion === state.myPick) tags.push('<span class="tag mine">Your pick</span>');
    if (s.in_pool) tags.push('<span class="tag pool">★ Pool</span>');
    if (s.off_role) tags.push(`<span class="tag flex" title="Mostly played as ${esc(s.main_role)}">Usually ${esc(s.main_role)}</span>`);
    if (s.niche) tags.push(`<span class="tag niche" title="Picked in only ${pct(s.stats.pick_rate)} of ${esc(s.role)} games, mostly by specialists">Niche</span>`);
    if (s.confidence === 'low') tags.push('<span class="tag low" title="Fewer than 5,000 games this patch">Few games</span>');
    const tier = s.stats.tier ? `<span class="tier ${tierClass(s.stats.tier)}" title="Lolalytics tier">${esc(s.stats.tier)}</span>` : '';
    const reasons = s.reasons.slice(0, featured ? 5 : 4).map(reasonHtml).join('');
    const splash = featured ? ` style="--splash:url('${esc(splashUrl(s.champion))}')"` : '';
    const eligible = state.analysis?.eligible;
    const label = mine ? (s.rank ? `#${s.rank}${eligible ? ` of ${eligible}` : ''}` : 'Your pick') : 'Est. win rate';
    return `<article class="card${featured ? ' featured' : ''}${mine ? ' mine' : ''}" data-key="${esc(key)}"${splash}>
        <div class="card-main clickable" data-action="expand">
            <span class="card-rank">${mine ? '' : s.rank}</span>
            ${imgBox(s.champion, 'card-icon')}
            <div class="card-info">
                <div class="card-title"><h3>${esc(s.champion)}</h3>${tier}<span class="role-tag">${ROLE_ICONS[s.role] || ''}${esc(s.role)}</span>${tags.join('')}</div>
                <ul class="reasons">${reasons}</ul>
            </div>
            <div class="card-score" title="Estimated win rate in this draft. 50% is an average pick in an average draft.">
                <span class="est ${estClass(s.estimate)}">${s.estimate.toFixed(1)}<small>%</small></span>
                <span class="est-label">${label}</span>
            </div>
            <button type="button" class="card-expand" aria-expanded="${open}" aria-label="Details for ${esc(s.champion)}">${ICON.chevron}</button>
        </div>
        <div class="card-details"${open ? '' : ' hidden'}>${detailsHtml(s)}</div>
    </article>`;
}

function banCardHtml(b, i, top) {
    const tier = b.tier ? `<span class="tier ${tierClass(b.tier)}">${esc(b.tier)}</span>` : '';
    const reasons = b.reasons.map(t => `<li class="reason"><span>${esc(t)}</span></li>`).join('');
    const priority = top > 0 ? Math.max(1, Math.round((100 * b.value) / top)) : 0;
    return `<article class="card ban-card">
        <div class="card-main">
            <span class="card-rank">${i + 1}</span>
            ${imgBox(b.champion, 'card-icon')}
            <div class="card-info">
                <div class="card-title"><h3>${esc(b.champion)}</h3>${tier}<span class="role-tag">${ROLE_ICONS[b.role] || ''}${esc(b.role)}</span></div>
                <ul class="reasons">${reasons}</ul>
            </div>
            <div class="card-score" title="Banning ${esc(b.champion)} is worth about ${b.value.toFixed(2)} win-rate points per game (how often they'd be picked into you times how much they win)">
                <span class="est ${priority >= 70 ? 'bad' : priority >= 40 ? 'meh' : 'ok'}">${priority}</span>
                <span class="est-label">Ban priority</span>
            </div>
            <button type="button" class="btn small" data-action="ban-suggested" data-name="${esc(b.champion)}">${ICON.ban}Ban</button>
        </div>
    </article>`;
}

function outlookHtml(o) {
    const ally = o.win_chance;
    return `<div class="outlook" title="Expected win chance from the picks so far: champion strength, cross-team matchups and synergy inside each team">
        <div class="outlook-head">
            <span class="outlook-title">Draft outlook · ${o.ally_picks} vs ${o.enemy_picks} picks</span>
            <span class="outlook-parts">Strength <b>${signed(o.strength)}</b> · Matchups <b>${signed(o.matchups)}</b> · Synergy <b>${signed(o.synergy)}</b></span>
        </div>
        <div class="outlook-bar"><div class="ally" style="width:${ally}%">${ally.toFixed(1)}%</div><div class="enemy">${(100 - ally).toFixed(1)}%</div></div>
    </div>`;
}

function emptyHtml(title, text) {
    return `<div class="empty-state"><strong>${title}</strong>${text}</div>`;
}

function picksHtml(a) {
    if (!a.suggestions.length) {
        if (state.prefs.poolOnly && state.prefs.pool.length) {
            return emptyHtml('None of your pool champions fit', `Nobody in your pool plays ${a.role ? esc(a.role) : 'an open role'} with enough games. Turn off <em>Pool only</em> to see everyone.`);
        }
        return emptyHtml('No suggestions', 'No champion has enough games in this role with the current filters.');
    }
    const title = a.role ? `Best ${esc(a.role)} picks for this draft` : `Best picks for your team's open roles (${a.open_roles.map(esc).join(', ')})`;
    return `<div class="section-label">${title}</div>` + a.suggestions.map((s, i) => cardHtml(s, { featured: i === 0 })).join('');
}

function bansHtml(a) {
    const bans = a.bans || [];
    if (!bans.length) return emptyHtml('No ban suggestions', 'The enemy has already filled every lane.');
    const roles = a.ban_roles || [];
    let where = 'across all roles';
    if (roles.length === 1 && roles[0] === a.role) where = `into ${esc(a.role)}`;
    else if (roles.length && roles.length < 5) where = `for the roles the enemy hasn't picked (${roles.map(esc).join(', ')})`;
    const top = bans[0].value;
    return `<div class="section-label">Champions worth banning ${where}</div>` + bans.map((b, i) => banCardHtml(b, i, top)).join('');
}

function renderCenter() {
    const a = state.analysis;
    const notices = [];
    if (!BOOT.data.has_stats) {
        notices.push(['error', 'No champion statistics found. Run <code>py data/update_data.py</code> to download them.']);
    } else if (!BOOT.data.has_matchups) {
        notices.push(['', 'Matchup data is missing, so suggestions only use tier-list strength. Run <code>py data/update_data.py</code> for the full analysis.']);
    }
    if (state.error) notices.push(['error', esc(state.error)]);
    if (state.prefs.poolOnly && !state.prefs.pool.length) {
        notices.push(['info', '<em>Pool only</em> needs champions in your pool. Add some in <a href="#" data-action="open-settings">Settings</a>.']);
    }
    setHtml('#notices', notices.map(([cls, html]) => `<div class="notice ${cls}">${html}</div>`).join(''));
    setHtml('#outlook', a?.outlook ? outlookHtml(a.outlook) : '');

    const results = $('#results');
    if (!a) {
        setHtml('#myPick', '');
        setHtml(results, state.error ? '' : '<div class="skeleton"></div>'.repeat(5));
        $('#moreBtn').hidden = true;
        return;
    }
    let changed;
    if (state.view === 'picks') {
        const mine = a.my_pick;
        const status = state.myPickState === 'locked' ? ' · locked in' : state.myPickState ? ' · hovering' : '';
        setHtml('#myPick', mine ? `<div class="section-label">Your pick${status}</div>${cardHtml(mine, { mine: true })}<div style="height:12px"></div>` : '');
        changed = setHtml(results, picksHtml(a));
        $('#moreBtn').hidden = !(a.eligible > a.suggestions.length && state.count < BOOT.defaults.max_count);
    } else {
        setHtml('#myPick', '');
        changed = setHtml(results, bansHtml(a));
        $('#moreBtn').hidden = true;
    }
    if (changed && Date.now() < freshUntil) {
        results.classList.add('fresh');
        clearTimeout(renderCenter.timer);
        renderCenter.timer = setTimeout(() => results.classList.remove('fresh'), 450);
    }
}

// ---------------------------------------------------------------------------
// Header: data freshness and League client status
// ---------------------------------------------------------------------------

function renderDataChip() {
    const d = BOOT.data;
    const bracket = BRACKETS[d.tier_bracket] || (d.tier_bracket || '').replace(/_/g, ' ');
    const updated = d.matchups_updated || d.stats_updated;
    const age = updated ? (Date.now() - Date.parse(updated)) / 86400000 : null;
    const stale = age != null && age > STALE_DATA_DAYS;
    const chip = $('#dataChip');
    chip.classList.toggle('stale', stale);
    setHtml(chip, `Patch <b>${esc(d.patch || '?')}</b>${bracket ? ` · ${esc(bracket)}` : ''}${stale ? ` · ${Math.floor(age)} days old` : ''}`);
    chip.title = `Lolalytics data from ${d.games_analysed ? int(d.games_analysed) + ' games' : 'this patch'}. Updated ${fmtDate(updated)}. Click for details.`;
    setHtml('#footer', `<span>Stats: <a href="https://lolalytics.com" target="_blank" rel="noopener noreferrer">lolalytics.com</a> (${esc(bracket || 'all ranks')}, patch ${esc(d.patch || '?')}, updated ${fmtDate(updated)}) · Art: Riot Data Dragon</span>
        <span>Not endorsed by Riot Games. League of Legends is a trademark of Riot Games, Inc.</span>`);
}

function turnInfo(c) {
    const a = c.action;
    if (c.phase === 'PLANNING') return { label: 'Champion select · declare your pick', mine: false };
    if (c.phase === 'FINALIZATION') return { label: 'Champion select · finalizing', mine: false };
    if (c.phase === 'GAME_STARTING') return { label: 'Game starting', mine: false };
    if (a) {
        if (a.is_mine) return { label: a.type === 'ban' ? 'Your turn to ban!' : 'Your turn to pick!', mine: true };
        return { label: `Champion select · ${a.is_ally ? 'ally' : 'enemy'} ${a.type === 'ban' ? 'banning' : 'picking'}`, mine: false };
    }
    return { label: 'Champion select', mine: false };
}

function renderClient() {
    const c = state.client;
    let st = 'offline';
    let label = 'League client offline';
    let mine = false;
    if (!state.prefs.live) {
        st = 'paused';
        label = 'Client sync paused';
    } else if (c.type === 'connecting') {
        label = 'Looking for the League client…';
    } else if (c.type === 'connected') {
        st = 'connected';
        label = `${c.summoner || 'Connected'} · ${GAMEFLOW[c.gameflow] || 'Connected'}`;
    } else if (c.type === 'champ_select') {
        const t = turnInfo(c);
        mine = t.mine;
        st = mine ? 'my_turn' : 'champ_select';
        label = t.label;
    } else if (c.type === 'error') {
        st = 'error';
        label = 'League client error';
    }
    const pill = $('#clientPill');
    pill.dataset.state = st;
    $('#clientText').textContent = label;
    document.title = `${mine ? '● ' + label + ' · ' : ''}Champion Suggester`;
    tickTimer();
}

function tickTimer() {
    const c = state.client;
    const el = $('#clientTimer');
    let text = '';
    if (state.prefs.live && c.type === 'champ_select' && c.timer && c.timer.left_ms > 0) {
        const left = c.timer.left_ms - (Date.now() - c.timer.at);
        if (left > 0) text = `${Math.ceil(left / 1000)}s`;
    }
    if (el.textContent !== text) el.textContent = text;
}

function render() {
    renderRoleSelect();
    renderViewSelect();
    renderFilters();
    renderBans();
    renderTeams();
    renderCenter();
    renderClient();
}

// ---------------------------------------------------------------------------
// Champion picker
// ---------------------------------------------------------------------------

const picker = { mode: null, lane: '', query: '' };

function pickerTitle(mode) {
    const role = mode.lane ? ROLE_OF[mode.lane] : '';
    switch (mode.kind) {
        case 'ally': return [role ? `Add your ${role}` : 'Add an ally', 'Pick the champion an ally locked in or is hovering.'];
        case 'enemy': return [role ? `Add the enemy ${role}` : 'Add an enemy', 'Roles are worked out automatically. Click a role icon on the board to set one.'];
        case 'me': return ['Your champion', 'Preview how a champion fares in this draft.'];
        case 'ban': return [mode.side === 'ally' ? 'Add a ban for your team' : 'Add an enemy ban', ''];
        case 'replace': return [`Replace ${mode.name}`, ''];
        case 'pool': return ['Champion pool', 'Click champions to add or remove them.'];
        default: return ['Choose a champion', ''];
    }
}

function openPicker(mode) {
    picker.mode = mode;
    picker.lane = mode.lane || '';
    picker.query = '';
    const [title, sub] = pickerTitle(mode);
    $('#pickerTitle').textContent = title;
    $('#pickerSub').textContent = sub;
    $('#pickerSearch').value = '';
    $('#pickerDone').hidden = mode.kind !== 'pool';
    renderPicker();
    const dialog = $('#picker');
    if (!dialog.open) dialog.showModal();
    $('#pickerSearch').focus();
    $('#pickerGrid').scrollTop = 0;
}

function matchScore(c, q) {
    if (c.key === q) return 100;
    if (c.key.startsWith(q)) return 80;
    if (ALIASES[q] === c.name) return 78;
    if (q.length >= 2 && c.initials.startsWith(q)) return 70;
    if (c.words.some(w => w.startsWith(q))) return 60;
    if (c.key.includes(q)) return 40;
    return 0;
}

function pickerList() {
    const q = norm(picker.query);
    const role = picker.lane ? ROLE_OF[picker.lane] : '';
    if (!q) {
        return role ? CHAMPS.filter(c => c.roles.includes(role)) : CHAMPS;
    }
    return CHAMPS.map(c => [c, matchScore(c, q)])
        .filter(([, score]) => score > 0)
        .map(([c, score]) => [c, score + (role && c.roles.includes(role) ? 5 : 0)])
        .sort((a, b) => b[1] - a[1] || a[0].name.localeCompare(b[0].name))
        .map(([c]) => c);
}

function renderPicker() {
    const opts = [['', 'All'], ...LANES.map(l => [l, ROLE_OF[l]])];
    setHtml('#pickerRoles', opts.map(([lane, label]) => `<button type="button" role="radio" aria-checked="${picker.lane === lane}" data-lane="${lane}">${lane ? ROLE_ICONS[label] : ''}<span>${label}</span></button>`).join(''));

    const mode = picker.mode;
    const list = pickerList();
    const pool = new Set(state.prefs.pool);
    const pickable = available() ? new Set(available()) : null;
    let firstMarked = false;
    const tiles = list.map(c => {
        let reason = '';
        if (mode.kind !== 'pool') {
            reason = c.name === mode.name ? 'Current' : takenReason(c.name);
            if (!reason && pickable && mode.kind === 'me' && !pickable.has(c.name)) reason = 'Not owned';
        }
        const disabled = !!reason && mode.kind !== 'pool';
        const first = !disabled && !firstMarked && picker.query;
        if (first) firstMarked = true;
        return `<button type="button" class="pick-tile${first ? ' first' : ''}${pool.has(c.name) ? ' in-pool' : ''}" data-name="${esc(c.name)}"${disabled ? ' disabled' : ''} title="${esc(c.name)}${c.roles.length ? ' · ' + c.roles.join(', ') : ''}${reason ? ' · ' + reason : ''}">
            ${imgBox(c.name, 'tile-img')}
            <span class="tile-name">${esc(c.name)}</span>${reason ? `<span class="tile-flag">${reason}</span>` : ''}</button>`;
    });
    setHtml('#pickerGrid', tiles.length ? tiles.join('') : `<div class="picker-empty">No champion matches “${esc(picker.query)}”.</div>`);
}

function choose(name) {
    const mode = picker.mode;
    if (!mode || !BY_NAME.has(name)) return;
    if (mode.kind === 'pool') {
        togglePool(name);
        renderPicker();
        renderSettings();
        commit();
        return;
    }
    $('#picker').close();
    if (mode.kind === 'ally' || mode.kind === 'enemy') addMember(mode.kind, name, mode.lane);
    else if (mode.kind === 'me') setMyPick(name);
    else if (mode.kind === 'ban') addBan(mode.side, name);
    else if (mode.kind === 'replace') replaceMember(mode.side, mode.name, name, mode.lane);
}

function gridColumns(grid) {
    const cols = getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length;
    return Math.max(1, cols);
}

function onPickerKey(e) {
    if (e.key === 'Escape') {
        e.preventDefault();
        $('#picker').close();
        return;
    }
    const grid = $('#pickerGrid');
    const tiles = $$('.pick-tile:not(:disabled)', grid);
    if (e.target.id === 'pickerSearch') {
        if (e.key === 'Enter') {
            e.preventDefault();
            if (tiles[0]) choose(tiles[0].dataset.name);
        } else if (e.key === 'ArrowDown' && tiles[0]) {
            e.preventDefault();
            tiles[0].focus();
        }
        return;
    }
    const tile = e.target.closest('.pick-tile');
    if (!tile) return;
    const all = $$('.pick-tile', grid);
    const i = all.indexOf(tile);
    const cols = gridColumns(grid);
    const step = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: cols, ArrowUp: -cols }[e.key];
    if (step) {
        e.preventDefault();
        const next = all[i + step];
        if (next) next.focus();
        else if (step < 0) $('#pickerSearch').focus();
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        $('#pickerSearch').focus();
    }
}

// ---------------------------------------------------------------------------
// Role menu
// ---------------------------------------------------------------------------

function openRoleMenu(anchor, side, name, isMe) {
    const menu = $('#roleMenu');
    const current = isMe ? state.myRole : members(side).find(m => m.champion === name)?.role || '';
    const title = isMe ? 'Your role' : `${esc(name)} plays`;
    menu.innerHTML = `<div class="menu-title">${title}</div>` +
        ROLES.map(r => `<button type="button" role="menuitemradio" aria-checked="${current === r}" data-role="${r}">${ROLE_ICONS[r]}${r}</button>`).join('') +
        `<hr><button type="button" role="menuitemradio" aria-checked="${!current}" data-role="">${ROLE_ICONS.Auto}${isMe ? 'Any role' : 'Work it out'}</button>`;
    menu.hidden = false;
    const r = anchor.getBoundingClientRect();
    const mw = menu.offsetWidth;
    const mh = menu.offsetHeight;
    let left = side === 'enemy' ? r.right - mw : r.left;
    let top = r.bottom + 6;
    if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    left = Math.min(Math.max(8, left), window.innerWidth - mw - 8);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.onclick = e => {
        const b = e.target.closest('button[data-role]');
        if (!b) return;
        closeRoleMenu();
        if (isMe) setMyRole(b.dataset.role);
        else setMemberRole(side, name, b.dataset.role);
    };
    (menu.querySelector('[aria-checked="true"]') || menu.querySelector('button')).focus();
}

function closeRoleMenu() {
    $('#roleMenu').hidden = true;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

function renderSettings() {
    const pool = state.prefs.pool.slice().sort((a, b) => a.localeCompare(b));
    $('#poolCount').textContent = pool.length ? `${pool.length}` : '';
    setHtml('#poolList', pool.length
        ? pool.map(n => `<span class="pool-chip">${imgBox(n, 'pool-img')}${esc(n)}<button type="button" data-action="pool-remove" data-name="${esc(n)}" aria-label="Remove ${esc(n)} from your pool">${ICON.close}</button></span>`).join('')
        : '<span class="pool-empty">Your pool is empty.</span>');
    $('#poolClear').disabled = !pool.length;
    $('#comfort').value = state.prefs.comfort;
    $('#comfortOut').textContent = `+${state.prefs.comfort.toFixed(1)}%`;
    $('#liveSync').checked = state.prefs.live;
    $('#poolImport').disabled = !connected();
    $('#poolImport').title = connected() ? 'Add your ten highest-mastery champions' : 'Needs the League client running';
    const d = BOOT.data;
    $('#dataInfo').innerHTML = `Lolalytics, patch <b>${esc(d.patch || '?')}</b>, ${esc(BRACKETS[d.tier_bracket] || d.tier_bracket || 'all ranks')}` +
        `${d.games_analysed ? `, ${esc(int(d.games_analysed))} games` : ''}. Tier list updated ${fmtDate(d.stats_updated)}, matchups ${fmtDate(d.matchups_updated)}.`;
}

function openSettings() {
    renderSettings();
    const dialog = $('#settings');
    if (!dialog.open) dialog.showModal();
}

async function importMastery() {
    const btn = $('#poolImport');
    btn.disabled = true;
    try {
        const res = await fetch('/lcu/mastery?limit=10');
        const data = await res.json();
        if (!data.available) {
            toast('Could not read your mastery from the League client.', 'bad');
            return;
        }
        const added = data.champions.map(c => c.champion).filter(n => BY_NAME.has(n) && !state.prefs.pool.includes(n));
        state.prefs.pool.push(...added);
        toast(added.length ? `Added ${added.length} champion${added.length === 1 ? '' : 's'} from your mastery.` : 'Your top mastery champions are already in your pool.', 'good');
        renderSettings();
        commit();
    } catch {
        toast('Could not reach the app server.', 'bad');
    } finally {
        btn.disabled = !connected();
    }
}

// ---------------------------------------------------------------------------
// Live League client sync
// ---------------------------------------------------------------------------

let source = null;
let reconnectTimer = 0;

function startLive() {
    if (source) return;
    state.client = { type: 'connecting' };
    renderClient();
    source = new EventSource('/lcu/stream');
    source.onmessage = e => {
        try {
            onLive(JSON.parse(e.data));
        } catch (err) {
            console.error('Bad live update', err);
        }
    };
    source.onerror = () => {
        if (source && source.readyState === EventSource.CLOSED) {
            source = null;
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => state.prefs.live && startLive(), 4000);
        }
        state.client = { type: 'connecting' };
        renderClient();
    };
}

function stopLive() {
    clearTimeout(reconnectTimer);
    if (source) source.close();
    source = null;
    state.client = { type: 'offline' };
    state.pickable = null;
    render();
}

async function fetchOwned() {
    try {
        const res = await fetch('/lcu/owned');
        const data = await res.json();
        state.owned = data.available && data.champions.length ? data.champions : null;
        render();
        if (state.prefs.ownedOnly && state.owned) scheduleAnalysis();
    } catch {
        /* the toggle simply stays hidden */
    }
}

function onLive(s) {
    const prev = state.client;
    state.client = s;
    if (s.type === 'champ_select') {
        applySession(s);
        return;
    }
    const wasInSelect = prev.type === 'champ_select';
    if (wasInSelect) toast('Champion select ended. The last draft stays on screen.');
    if (state.pickable) {
        state.pickable = null;
        if (state.prefs.ownedOnly) scheduleAnalysis();
    }
    if (s.type === 'connected' && !state.owned) fetchOwned();
    if (s.type === 'offline') state.owned = null;
    render();
}

function applySession(s) {
    const newGame = s.game_id !== sync.gameId;
    if (newGame) {
        sync.gameId = s.game_id;
        sync.clientRole = null;
        sync.clientPick = null;
        sync.actionKey = '';
        state.pins = { ally: {}, enemy: {} };
        state.expanded.clear();
        state.count = BOOT.defaults.count;
        toast('Champion select found. Syncing picks and bans from the client.', 'good');
    }
    const role = s.my_role || '';
    if (role !== sync.clientRole) {
        sync.clientRole = role;
        state.myRole = role;
    }
    const pick = s.me.champion || '';
    if (pick !== sync.clientPick || (s.me.state === 'locked' && state.myPick !== pick)) {
        sync.clientPick = pick;
        state.myPick = pick;
    }
    state.myPickState = state.myPick && state.myPick === pick ? s.me.state : '';
    state.allies = s.allies
        .filter(a => a.champion || a.role)
        .map(a => ({ champion: a.champion, role: state.pins.ally[a.champion] || a.role || '', state: a.state, source: state.pins.ally[a.champion] ? 'user' : a.role ? 'client' : '' }));
    state.enemies = s.enemies
        .filter(e => e.champion)
        .map(e => ({ champion: e.champion, role: state.pins.enemy[e.champion] || '', state: e.state, source: state.pins.enemy[e.champion] ? 'user' : '' }));
    state.bans = { ally: s.bans.ally.slice(0, 5), enemy: s.bans.enemy.slice(0, 5) };
    const takenElsewhere = n => isBanned(n) || state.allies.some(m => m.champion === n) || state.enemies.some(m => m.champion === n);
    if (state.myPick && state.myPick !== pick && takenElsewhere(state.myPick)) state.myPick = pick;
    state.pickable = s.pickable && s.pickable.length ? s.pickable : null;

    const key = s.action ? `${s.action.type}:${s.action.is_mine}` : '';
    if (key !== sync.actionKey) {
        sync.actionKey = key;
        if (s.action && s.action.is_mine) state.view = s.action.type === 'ban' ? 'bans' : 'picks';
    }
    commit();
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function toggleExpand(main) {
    const card = main.closest('.card');
    const details = card && card.querySelector('.card-details');
    if (!details) return;
    const open = details.hidden;
    details.hidden = !open;
    main.querySelector('.card-expand')?.setAttribute('aria-expanded', String(open));
    if (open) state.expanded.add(card.dataset.key);
    else state.expanded.delete(card.dataset.key);
    const container = card.parentElement;
    htmlCache.delete(container);
}

document.addEventListener('click', e => {
    const menu = $('#roleMenu');
    if (!menu.hidden && !menu.contains(e.target) && !e.target.closest('[data-action="role-menu"]')) closeRoleMenu();

    const el = e.target.closest('[data-action]');
    if (!el) return;
    const { action, side, lane, name } = el.dataset;
    switch (action) {
        case 'add': openPicker({ kind: side, lane }); break;
        case 'pick-me': openPicker({ kind: 'me', lane: LANE_OF[state.myRole] || '' }); break;
        case 'replace': openPicker({ kind: 'replace', side, name, lane }); break;
        case 'remove': removeMember(side, name); break;
        case 'clear-me': setMyPick(''); break;
        case 'role-menu':
            if (!menu.hidden) closeRoleMenu();
            else openRoleMenu(el, side, name, el.dataset.me === '1');
            break;
        case 'add-ban': openPicker({ kind: 'ban', side }); break;
        case 'unban': removeBan(side, name); break;
        case 'expand':
            if (!e.target.closest('a, .detail-actions')) toggleExpand(el);
            break;
        case 'preview': setMyPick(name); break;
        case 'toggle-pool':
            togglePool(name);
            commit();
            break;
        case 'ban-suggested': addBan('ally', name); break;
        case 'open-settings':
            e.preventDefault();
            openSettings();
            break;
        case 'close-dialog': el.closest('dialog').close(); break;
        case 'pool-remove':
            togglePool(name);
            renderSettings();
            commit();
            break;
        default: break;
    }
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !$('#roleMenu').hidden) {
        closeRoleMenu();
        e.stopPropagation();
    }
});

window.addEventListener('resize', closeRoleMenu);
window.addEventListener('scroll', closeRoleMenu, { passive: true });

document.addEventListener('error', e => {
    const img = e.target;
    if (img instanceof HTMLImageElement) img.closest('.img-wrap')?.classList.add('broken');
}, true);

for (const dialog of $$('dialog')) {
    dialog.addEventListener('click', e => {
        if (e.target === dialog) dialog.close();
    });
}

$('#picker').addEventListener('keydown', onPickerKey);
$('#pickerSearch').addEventListener('input', e => {
    picker.query = e.target.value;
    renderPicker();
    $('#pickerGrid').scrollTop = 0;
});
$('#pickerRoles').addEventListener('click', e => {
    const b = e.target.closest('button[data-lane]');
    if (!b) return;
    picker.lane = b.dataset.lane;
    renderPicker();
    $('#pickerSearch').focus();
});
$('#pickerGrid').addEventListener('click', e => {
    const tile = e.target.closest('.pick-tile');
    if (tile && !tile.disabled) choose(tile.dataset.name);
});

$('#roleSelect').addEventListener('click', e => {
    const b = e.target.closest('button[data-role]');
    if (b) setMyRole(b.dataset.role);
});
$('#viewSelect').addEventListener('click', e => {
    const b = e.target.closest('button[data-view]');
    if (!b || b.dataset.view === state.view) return;
    state.view = b.dataset.view;
    render();
});

$('#poolOnly').addEventListener('change', e => {
    state.prefs.poolOnly = e.target.checked;
    commit();
});
$('#includeNiche').addEventListener('change', e => {
    state.prefs.includeNiche = e.target.checked;
    commit();
});
$('#ownedOnly').addEventListener('change', e => {
    state.prefs.ownedOnly = e.target.checked;
    commit();
});
$('#moreBtn').addEventListener('click', () => {
    state.count = Math.min(BOOT.defaults.max_count, state.count + 10);
    scheduleAnalysis(0);
});
$('#resetBtn').addEventListener('click', () => {
    resetDraft();
    toast('Draft cleared.');
});

$('#clientPill').addEventListener('click', () => {
    state.prefs.live = !state.prefs.live;
    save();
    if (state.prefs.live) startLive();
    else stopLive();
    toast(state.prefs.live ? 'Syncing with the League client.' : 'Client sync paused. Edit the draft by hand.');
});
$('#liveSync').addEventListener('change', e => {
    state.prefs.live = e.target.checked;
    save();
    if (state.prefs.live) startLive();
    else stopLive();
});
$('#comfort').addEventListener('input', e => {
    state.prefs.comfort = Number(e.target.value);
    $('#comfortOut').textContent = `+${state.prefs.comfort.toFixed(1)}%`;
    save();
    if (state.prefs.pool.length) scheduleAnalysis(150);
});
$('#poolAdd').addEventListener('click', () => {
    $('#settings').close();
    openPicker({ kind: 'pool', fromSettings: true });
});
$('#picker').addEventListener('close', () => {
    if (picker.mode && picker.mode.fromSettings) {
        picker.mode = null;
        openSettings();
    }
});
$('#poolImport').addEventListener('click', importMastery);
$('#poolClear').addEventListener('click', () => {
    if (!state.prefs.pool.length) return;
    state.prefs.pool = [];
    state.prefs.poolOnly = false;
    renderSettings();
    commit();
});

setInterval(tickTimer, 250);

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

renderDataChip();
render();
analyze();
if (state.prefs.live) startLive();
