# LoL Champion Suggester

A tool for suggesting League of Legends champions based on various data sources, including U.GG, Lolalytics, and more.

## Features
- Suggests champions for your next game based on meta data
- Integrates with League Client API
- Uses computer vision for champion select
- Supports data from U.GG and Lolalytics

## Getting Started
1. Clone the repository:
   ```bash
   git clone https://github.com/YusufShahz/lol-champion-suggester.git
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the app:
   ```bash
   python app.py
   ```

## Project Structure
- `app.py`: Main application file
- `champ_select_cv.py`: Computer vision for champion select
- `ddragon.py`, `lcu_api.py`: Data and API utilities
- `populate_champion_data_ugg.py`: U.GG data integration
- `static/`, `templates/`: Frontend assets

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License
MIT
