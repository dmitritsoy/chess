#!/usr/bin/env python3
"""Enrich ratings.json with KNSB classic and rapid ratings from ratingviewer.nl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from knsb_ratings import KnsbRatingService, build_ratings
from ratings_data import RATINGS_PATH, TOURNAMENT_PATH, write_json

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch KNSB ratings for players in tournament.json")
    parser.add_argument(
        "--input",
        type=Path,
        default=TOURNAMENT_PATH,
        help="Tournament JSON to read (default: data/tournament.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RATINGS_PATH,
        help="Ratings JSON to write (default: data/ratings.json)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Missing {args.input}. Run scripts/fetch_data.py first.", file=sys.stderr)
        return 1

    tournament = json.loads(args.input.read_text(encoding="utf-8"))
    player_count = sum(len(team["players"]) for semi in tournament["semifinals"] for team in semi["teams"])
    print(f"Fetching KNSB ratings for {player_count} player slots...")

    session = requests.Session()
    session.headers.update({"User-Agent": "NK-Schoolschaak-Stats/1.0 (+local team composition tool)"})

    service = KnsbRatingService(session)
    ratings = build_ratings(tournament, service)
    service.save_cache()

    write_json(args.output, ratings)

    resolved = len(
        {
            entry["knsb_relatienummer"]
            for entry in ratings["players"].values()
            if entry.get("knsb_relatienummer")
        }
    )
    print(f"Resolved KNSB ratings for {resolved} unique players")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
