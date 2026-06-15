#!/usr/bin/env python3
"""Enrich tournament.json with KNSB classic and rapid ratings from ratingviewer.nl."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

from knsb_ratings import KnsbRatingService, enrich_tournament

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "tournament.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch KNSB ratings for players in tournament.json")
    parser.add_argument(
        "--input",
        type=Path,
        default=DATA_PATH,
        help="Tournament JSON to enrich (default: data/tournament.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: overwrite --input)",
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
    resolved = enrich_tournament(tournament, service)
    service.save_cache()

    output = args.output or args.input
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tournament, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Resolved KNSB ratings for {resolved} unique players")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
