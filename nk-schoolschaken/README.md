# NK Schoolschaak 2026 — Halve Finales

Tool om teamcompositie te ondersteunen met data uit de drie halve finales.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Data ophalen

Tournament data (standen, spelers, toernooiresultaten):

```bash
python scripts/fetch_data.py
```

KNSB ratings (klassiek/rapid via [ratingviewer.nl](https://ratingviewer.nl)):

```bash
python scripts/fetch_ratings.py
```

`fetch_ratings.py` leest `data/tournament.json` en schrijft de ratings terug naar hetzelfde bestand. Ratings worden gecached in `data/rating_cache.json` voor snellere herhaalde runs.

Partijen per speler (tegenstander + team):

```bash
python scripts/fetch_games.py
```

## Website bekijken

```bash
python3 -m http.server 8080
```

Open daarna [http://localhost:8080/web/](http://localhost:8080/web/).

## Bronnen

- [Halve finale Arnhem](https://knsb.netstand.nl/divisions/view/647)
- [Halve finale Kruiningen](https://knsb.netstand.nl/divisions/view/645)
- [Halve finale Almere](https://uitslagen.schakenalmere.nl/schoolschaak-halve-finale-nk-2026/Grp1-Layout1.html)

De top 8 teams per halve finale zijn gemarkeerd als finalisten (24 teams totaal).
