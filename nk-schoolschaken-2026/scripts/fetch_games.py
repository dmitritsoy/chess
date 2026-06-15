#!/usr/bin/env python3
"""Fetch per-player games with opponents and teams into tournament.json."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

from games_parser import (
    attach_games_to_players,
    clean_name,
    is_placeholder_player,
    knsb_parse_pairing,
    knsb_team_pairing_urls,
    pairing_url,
    sevilla_parse_team_games,
)
from ratings_data import TOURNAMENT_PATH

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = TOURNAMENT_PATH
REQUEST_DELAY = 0.12

PARSER_BY_SEMIFINAL = {
    "arnhem": "knsb",
    "kruiningen": "knsb",
    "almere": "sevilla",
}


def semifinal_teams_for_games(tournament: dict[str, Any], semifinal: dict[str, Any]) -> list[dict[str, Any]]:
    limit = tournament.get("qualifiers_per_semifinal", 8)
    teams = [team for team in semifinal.get("teams", []) if team.get("qualified")]
    teams.sort(key=lambda team: team.get("rank") or 999)
    return teams[:limit]


def fetch_html(session: requests.Session, url: str) -> str:
    time.sleep(REQUEST_DELAY)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
    }
    response = session.get(url, timeout=30, headers=headers)
    response.raise_for_status()
    return response.text


def fetch_knsb_team_games(session: requests.Session, team: dict[str, Any]) -> list[dict]:
    html = fetch_html(session, team["source_url"])
    team_name = team["name"]
    games: list[dict] = []
    for path in knsb_team_pairing_urls(html):
        pairing_html = fetch_html(session, pairing_url(path))
        games.extend(knsb_parse_pairing(pairing_html, team_name))
    return games


def fetch_sevilla_team_games(session: requests.Session, team: dict[str, Any]) -> list[dict]:
    html = fetch_html(session, team["source_url"])
    return sevilla_parse_team_games(html, team["name"])


def copy_games_by_name(source_team: dict, target_team: dict) -> None:
    source_by_name = {clean_name(player["name"]).casefold(): player for player in source_team["players"]}
    target_by_name = {clean_name(player["name"]).casefold(): player for player in target_team["players"]}
    for player in target_team["players"]:
        source = source_by_name.get(clean_name(player["name"]).casefold())
        player["games"] = list(source.get("games", [])) if source else []

    for source_player in source_team["players"]:
        if not is_placeholder_player(source_player["name"]):
            continue
        key = clean_name(source_player["name"]).casefold()
        if key in target_by_name:
            continue
        target_team["players"].append(
            {
                key: value
                for key, value in source_player.items()
                if key != "games"
            }
            | {"games": list(source_player.get("games", []))}
        )


def enrich_tournament(tournament: dict, session: requests.Session) -> int:
    team_count = 0
    qualifiers = tournament.get("qualifiers_per_semifinal", 8)

    for semifinal in tournament["semifinals"]:
        parser = PARSER_BY_SEMIFINAL.get(semifinal["id"], "knsb")
        teams = semifinal_teams_for_games(tournament, semifinal)
        for index, team in enumerate(teams, start=1):
            team_count += 1
            print(
                f"  [{semifinal['id']}] {team['name']} "
                f"({index}/{len(teams)} top-{qualifiers})"
            )
            if parser == "knsb":
                raw_games = fetch_knsb_team_games(session, team)
            else:
                raw_games = fetch_sevilla_team_games(session, team)
            attach_games_to_players(team, raw_games)

    for team in tournament["finalists"]:
        semifinal_id = team["id"].split("-")[0]
        source = next(
            (entry for entry in tournament["semifinals"] if entry["id"] == semifinal_id),
            None,
        )
        if not source:
            copy_games_by_name(team, team)
            continue
        source_team = next((entry for entry in source["teams"] if entry["id"] == team["id"]), None)
        if source_team:
            copy_games_by_name(source_team, team)
        else:
            for player in team["players"]:
                player["games"] = []

    return team_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch per-player games into tournament.json")
    parser.add_argument("--input", type=Path, default=DATA_PATH)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Missing {args.input}. Run scripts/fetch_data.py first.", file=sys.stderr)
        return 1

    tournament = json.loads(args.input.read_text(encoding="utf-8"))
    per_semifinal = tournament.get("qualifiers_per_semifinal", 8)
    semifinal_count = len(tournament.get("semifinals", []))
    teams_to_fetch = per_semifinal * semifinal_count
    print(
        f"Fetching games for top {per_semifinal} teams per semifinal "
        f"({teams_to_fetch} teams total)..."
    )

    session = requests.Session()
    team_count = enrich_tournament(tournament, session)
    tournament["games_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    output = args.output or args.input
    output.write_text(json.dumps(tournament, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Fetched games for {team_count} teams")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
