# LoL Champion Suggester

A tool that reads your League of Legends champion select and suggests the best pick based on counter data and team composition.

## Features
- **Counter-based suggestions** — Uses win rate and delta data from Lolalytics to find champions that counter the enemy team
- **Team composition awareness** — Fills missing roles (Top/Jungle/Mid/ADC/Support)
- **LCU Client integration** — Reads picks directly from the League Client API during champion select
- **Data-driven** — All champion data (roles, counters) stored as JSON, easily refreshable

## Getting Started

1. Clone the repository:
   ```bash
   git clone https://github.com/YusufShahz/lol-champion-suggester.git
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Populate data (first time or to refresh):
   ```bash
   python data/update_data.py --champions --roles
   python scrape_lolalytics.py
   ```

4. Run the app:
   ```bash
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

## Project Structure
```
├── app.py                    # Flask web server
├── champion_data.py          # Data loading module (JSON-backed)
├── ddragon.py                # Riot Data Dragon API client
├── lcu_api.py                # League Client API integration
├── scrape_lolalytics.py      # Lolalytics counter data scraper
├── data/
│   ├── champions.json        # Champion list
│   ├── roles.json            # Champion → role mapping
│   ├── counters.json         # Counter/matchup data with win rates
│   └── update_data.py        # CLI to refresh all data files
├── templates/
│   └── index.html            # Web UI
├── static/
│   └── style.css             # Styles
└── requirements.txt
```

## Refreshing Data
```bash
# Update champions and roles from Data Dragon
python data/update_data.py --champions --roles

# Update counter data from Lolalytics (~6 min)
python scrape_lolalytics.py

# Or update everything at once
python data/update_data.py
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
MIT
