# LoL Champion Suggester

A ranked draft assistant for League of Legends. It follows your champion select
live from the League client and ranks every champion you could pick by an
**estimated win rate for this exact draft**, using current-patch Lolalytics data:
lane strength, matchups against every enemy, synergy with your allies, team
composition and the risk of being counter-picked. It also suggests bans and
shows how the two drafts compare.

The app only *reads* champion select. It never picks, bans or clicks anything
for you.

## Features

- **Live client sync:** locked picks, hovers, bans for both teams, everyone's
  assigned role, whose turn it is and the phase timer, all read from the
  League client. Everything also works by hand without the client.
- **Estimated win rate per pick** with the reasons behind it ("Strong vs
  Yasuo +1.2", "Pairs well with Thresh +0.8", "Counter-pick risk: Malphite") and
  a full breakdown when you expand a card.
- **Matchups across all lanes:** every enemy counts, weighted by how likely they
  are to play each lane. Your lane opponent matters most, but the enemy
  jungler and bot lane count too.
- **Role inference** for both teams, including flex picks. Roles the client
  assigns, or that you set on the board, are respected.
- **Blind-pick awareness:** while your lane opponent is unknown, picks with
  popular hard counters are penalised.
- **Ban suggestions** aimed at your lane (or at the lanes the enemy still has to
  fill), prioritising champions that beat your pool.
- **Draft outlook:** the win chance implied by both teams' picks.
- **Champion pool** with an adjustable comfort bonus. You can import your
  top-mastery champions from the client, and filter to your pool or to champions
  you can actually pick.
- **Team composition panels:** damage split, frontline, crowd control and
  warnings such as "Mostly physical damage" or "No frontline".

## Getting started

Requires Python 3.10 or newer. On Windows, use `py`; elsewhere, use `python3`.

```bash
pip install -r requirements.txt
py data/update_data.py        # first-time data download, a few minutes
py app.py --open              # starts the server and opens http://127.0.0.1:5000
```

Keep the page open while you queue. When champion select starts, the board fills
in by itself. Click the client status pill in the header to pause or resume
syncing.

Options: `--port 5000`, `--host 127.0.0.1`, `--open`, `--debug` (auto-reload
while developing). `PORT`, `HOST` and `FLASK_DEBUG=1` can also be set in `.env`.

## How a pick is scored

Every candidate gets an estimated win rate, normalised so that an average
champion in an average draft sits at 50%:

```
estimate = 50 + meta + matchups + synergy + composition + blind_risk + comfort
```

| Part          | What it measures                                                               |
|---------------|--------------------------------------------------------------------------------|
| `meta`        | The champion's win rate in the lane minus the bracket average                  |
| `matchups`    | Lolalytics delta2 against each enemy, weighted by the chance they play each lane |
| `synergy`     | delta2 with each ally, weighted the same way                                   |
| `composition` | Fixing damage-type imbalance, a missing frontline or a lack of crowd control   |
| `blind_risk`  | Expected loss to a counter-pick while your lane opponent is still unknown      |
| `comfort`     | The bonus from settings for champions in your pool                             |

Small samples are noisy, so every observed effect is shrunk towards zero by
`games / (games + K)`. K is estimated per kind of effect (lane matchup,
cross-lane matchup, synergy, duo synergy) from how much the observed effects
spread compared with pure sampling noise. A matchup seen in 300 games therefore
counts for much less than one seen in 30,000.

Champions picked in under 1% of a role's games are hidden by default. Their win
rates mostly come from one-trick specialists. Turn on **Niche picks** to see
them anyway.

## Refreshing data

```bash
py data/update_data.py               # everything
py data/update_data.py --stats       # tier list only (a few seconds)
py data/update_data.py --matchups    # matchups and synergy (slow, resumes where it stopped)
py data/update_data.py --champions   # champion list and League client metadata
py data/update_data.py --matchups --force --tier platinum_plus   # extra options go to the scraper
```

The running app notices new data files and reloads them without a restart. The
header shows the patch and rank bracket of the data in use.

## Tests

```bash
py -m unittest
```

Engine tests run on a small synthetic dataset. The real-data sanity checks are
skipped until `data/update_data.py` has been run.

## Project structure

```
├── app.py                  Flask server: UI, /suggest API, live client state over Server-Sent Events
├── suggester.py            Suggestion engine: role inference, scoring, bans, draft outlook
├── champion_data.py        Data layer: tier list, matchups, synergy, champion attributes
├── lcu_api.py              League client API: champion select session, mastery, owned champions
├── ddragon.py              Data Dragon / Community Dragon: ids, icons, damage types, playstyle ratings
├── scrape_lolalytics.py    Lolalytics scraper (tier list, matchups, synergy)
├── data/
│   ├── update_data.py      Refreshes everything below
│   ├── stats.json          Tier list per lane
│   ├── matchups.json       Matchups and synergy per champion and lane
│   ├── cdragon_champions.json, ddragon_champions.json   Champion metadata caches
│   └── champions.json, roles.json                      Fallbacks when stats are missing
├── templates/index.html    Page shell
├── static/app.js           Front end: draft board, picker, suggestion cards, live sync
├── static/style.css        Styles
└── tests/                  Unit tests
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to
discuss what you would like to change.

## License

MIT

LoL Champion Suggester isn't endorsed by Riot Games and doesn't reflect the views
or opinions of Riot Games or anyone officially involved in producing or managing
Riot Games properties. Riot Games and all associated properties are trademarks or
registered trademarks of Riot Games, Inc.
