#!/usr/bin/env python3
"""Fetch and parse NK Schoolschaak 2026 semifinal data from KNSB Netstand and Sevilla."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "tournament.json"

QUALIFIERS_PER_SEMIFINAL = 8
REQUEST_DELAY = 0.15

SOURCES = {
    "arnhem": {
        "name": "Halve Finale Arnhem",
        "system": "swiss_team",
        "url": "https://knsb.netstand.nl/divisions/view/647",
        "parser": "knsb",
    },
    "kruiningen": {
        "name": "Halve Finale Kruiningen",
        "system": "swiss_team",
        "url": "https://knsb.netstand.nl/divisions/view/645",
        "parser": "knsb",
    },
    "almere": {
        "name": "Halve Finale Almere",
        "system": "swiss",
        "url": "https://uitslagen.schakenalmere.nl/schoolschaak-halve-finale-nk-2026/Grp1-Layout1.html",
        "base_url": "https://uitslagen.schakenalmere.nl/schoolschaak-halve-finale-nk-2026/",
        "parser": "sevilla",
    },
}


@dataclass
class Player:
    name: str
    rating: int | None
    games: int
    points: float
    tpr: int | None
    player_id: str | None = None
    boards: list[int] | None = None


@dataclass
class Team:
    id: str
    name: str
    rank: int
    match_points: float | None
    board_points: float | None
    score: float | None
    buchholz: float | None
    team_rating: int | None
    qualified: bool
    source_url: str
    players: list[Player]


@dataclass
class Semifinal:
    id: str
    name: str
    system: str
    url: str
    teams: list[Team]


def fetch_html(session: requests.Session, url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    }
    response = session.get(url, timeout=30, headers=headers)
    response.raise_for_status()
    return response.text


def clean_text(value: str) -> str:
    text = unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def parse_number(value: str) -> float | None:
    value = value.strip().replace(",", ".")
    if not value or value in {"-", "—"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_int(value: str) -> int | None:
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def knsb_parse_division(html: str, source_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    teams_heading = soup.find("h2", string=re.compile(r"^Teams$"))
    if not teams_heading:
        raise ValueError("Could not find Teams section on KNSB division page")

    table = teams_heading.find_next("table")
    if not table:
        raise ValueError("Could not find teams table on KNSB division page")

    teams: list[dict[str, Any]] = []
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        link = cells[0].find("a", href=True)
        if not link:
            continue
        team_id = link["href"].rstrip("/").split("/")[-1]
        teams.append(
            {
                "id": team_id,
                "name": clean_text(link.get_text()),
                "rank": len(teams) + 1,
                "match_points": parse_number(cells[1].get_text()),
                "board_points": parse_number(cells[2].get_text()),
                "score": None,
                "buchholz": None,
                "team_rating": None,
                "source_url": urljoin(source_url, link["href"]),
            }
        )
    return teams


def knsb_parse_team(html: str) -> list[Player]:
    soup = BeautifulSoup(html, "html.parser")
    players_heading = soup.find("h2", string=re.compile(r"^Spelers$"))
    players: list[Player] = []

    if players_heading:
        table = players_heading.find_next("table")
        if table and (table.find("tbody") or table):
            body = table.find("tbody") or table
            for row in body.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) < 4:
                    continue
                link = cells[0].find("a", href=True)
                name = clean_text(link.get_text() if link else cells[0].get_text())
                player_id = None
                if link and "/players/view/" in link["href"]:
                    player_id = link["href"].rstrip("/").split("/")[-1]
                rating = parse_int(cells[1].get_text())
                games = parse_int(cells[2].get_text()) or 0
                points = parse_number(cells[3].get_text()) or 0.0
                tpr = parse_int(cells[4].get_text()) if len(cells) > 4 else None
                players.append(
                    Player(
                        name=name,
                        rating=rating if rating and rating > 0 else None,
                        games=games,
                        points=points,
                        tpr=tpr if tpr and tpr > 0 else None,
                        player_id=player_id,
                    )
                )

    boards_by_player = knsb_parse_board_usage(soup)
    for player in players:
        key = player.name.casefold()
        if key in boards_by_player:
            player.boards = boards_by_player[key]

    return players


def knsb_parse_board_usage(soup: BeautifulSoup) -> dict[str, list[int]]:
    heading = soup.find("h2", string=re.compile(r"Persoonlijke Resultaten"))
    if not heading:
        return {}

    table = heading.find_next("table")
    if not table:
        return {}

    header_cells = table.find("thead").find_all("th")
    board_numbers: list[int] = []
    for cell in header_cells:
        text = clean_text(cell.get_text())
        if text.isdigit():
            board_numbers.append(int(text))

    usage: dict[str, list[int]] = {}
    for row in table.find("tbody").find_all("tr"):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        name = clean_text(cells[0].get_text())
        boards: list[int] = []
        for idx, board in enumerate(board_numbers):
            cell = cells[idx + 1] if idx + 1 < len(cells) else None
            if not cell:
                continue
            text = clean_text(cell.get_text())
            if text and text != "-":
                boards.append(board)
        if boards:
            usage[name.casefold()] = sorted(set(boards))
    return usage


def sevilla_parse_ranking(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    teams: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        header_index = None
        headers: list[str] = []

        for index, row in enumerate(rows):
            candidate = [
                clean_text(cell.get_text())
                for cell in row.find_all(["th", "td"])
            ]
            if len(candidate) >= 3 and candidate[0] == "Pos" and candidate[1] == "Name":
                header_index = index
                headers = candidate
                break

        if header_index is None:
            continue

        for row in rows[header_index + 1 :]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            rank = parse_int(cells[0].get_text())
            if rank is None:
                continue
            link = cells[1].find("a", href=True)
            name = clean_text(link.get_text() if link else cells[1].get_text())
            team_page = urljoin(base_url, link["href"]) if link else None
            teams.append(
                {
                    "id": link["href"] if link else f"team-{rank}",
                    "name": name,
                    "rank": rank,
                    "match_points": None,
                    "board_points": None,
                    "score": parse_number(cells[2].get_text()),
                    "buchholz": parse_number(cells[4].get_text()) if len(cells) > 4 else None,
                    "team_rating": None,
                    "source_url": team_page or base_url,
                }
            )
        if teams:
            break

    if not teams:
        raise ValueError("Could not find ranking table on Sevilla page")
    return teams


def sevilla_parse_team(html: str) -> tuple[int | None, list[Player]]:
    soup = BeautifulSoup(html, "html.parser")
    team_rating: int | None = None

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 2 and clean_text(cells[0].get_text()) == "Rating":
            team_rating = parse_int(cells[1].get_text())

    table = soup.find("table", id="IndividualDetailsTable")
    players: list[Player] = []
    if not table:
        return team_rating, players

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 12:
            continue
        name = clean_text(cells[0].get_text())
        if name.lower() == "name":
            continue
        score = parse_number(cells[8].get_text()) or 0.0
        games = parse_int(cells[9].get_text()) or 0
        rating = parse_int(cells[11].get_text())
        tpr = parse_int(cells[12].get_text()) if len(cells) > 12 else None
        players.append(
            Player(
                name=name,
                rating=rating if rating and rating > 0 else None,
                games=games,
                points=score,
                tpr=tpr if tpr and tpr > 0 else None,
            )
        )

    return team_rating, players


def build_semifinal(
    session: requests.Session,
    semifinal_id: str,
    config: dict[str, Any],
) -> Semifinal:
    print(f"Fetching {config['name']}...")
    html = fetch_html(session, config["url"])
    parser = config["parser"]

    if parser == "knsb":
        raw_teams = knsb_parse_division(html, config["url"])
        for index, raw in enumerate(raw_teams):
            time.sleep(REQUEST_DELAY)
            team_html = fetch_html(session, raw["source_url"])
            players = knsb_parse_team(team_html)
            raw["players"] = players
            if (index + 1) % 6 == 0:
                print(f"  loaded {index + 1}/{len(raw_teams)} teams")
    elif parser == "sevilla":
        raw_teams = sevilla_parse_ranking(html, config["base_url"])
        for index, raw in enumerate(raw_teams):
            if not raw["source_url"]:
                raw["players"] = []
                continue
            time.sleep(REQUEST_DELAY)
            team_html = fetch_html(session, raw["source_url"])
            team_rating, players = sevilla_parse_team(team_html)
            raw["team_rating"] = team_rating
            raw["players"] = players
            if (index + 1) % 6 == 0:
                print(f"  loaded {index + 1}/{len(raw_teams)} teams")
    else:
        raise ValueError(f"Unknown parser: {parser}")

    teams: list[Team] = []
    for raw in raw_teams:
        qualified = raw["rank"] <= QUALIFIERS_PER_SEMIFINAL
        players = raw.get("players", [])
        teams.append(
            Team(
                id=f"{semifinal_id}-{raw['id']}",
                name=raw["name"],
                rank=raw["rank"],
                match_points=raw["match_points"],
                board_points=raw["board_points"],
                score=raw["score"],
                buchholz=raw["buchholz"],
                team_rating=raw.get("team_rating"),
                qualified=qualified,
                source_url=raw["source_url"],
                players=players,
            )
        )

    return Semifinal(
        id=semifinal_id,
        name=config["name"],
        system=config["system"],
        url=config["url"],
        teams=teams,
    )


def summarize_players(teams: list[Team]) -> dict[str, Any]:
    rated = [player.rating for team in teams for player in team.players if player.rating]
    return {
        "team_count": len(teams),
        "finalist_count": sum(1 for team in teams if team.qualified),
        "player_count": sum(len(team.players) for team in teams),
        "rated_player_count": len(rated),
        "avg_rating": round(sum(rated) / len(rated), 1) if rated else None,
        "max_rating": max(rated) if rated else None,
    }


def to_json(semifinals: list[Semifinal]) -> dict[str, Any]:
    all_teams = [team for semifinal in semifinals for team in semifinal.teams]
    finalists = [team for team in all_teams if team.qualified]

    def team_to_dict(team: Team) -> dict[str, Any]:
        players = sorted(
            team.players,
            key=lambda player: (player.rating or 0, player.points),
            reverse=True,
        )
        ratings = [player.rating for player in players if player.rating]
        return {
            **{k: v for k, v in asdict(team).items() if k != "players"},
            "players": [asdict(player) for player in players],
            "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
            "top_rating": max(ratings) if ratings else None,
            "player_count": len(players),
        }

    return {
        "competition": "NK Schoolschaak BO Algemeen 2026",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "qualifiers_per_semifinal": QUALIFIERS_PER_SEMIFINAL,
        "summary": {
            "semifinal_count": len(semifinals),
            "finalist_teams": len(finalists),
            **summarize_players(finalists),
        },
        "semifinals": [
            {
                "id": semifinal.id,
                "name": semifinal.name,
                "system": semifinal.system,
                "url": semifinal.url,
                "summary": summarize_players(
                    [team for team in semifinal.teams if team.qualified]
                ),
                "teams": [
                    team_to_dict(team)
                    for team in semifinal.teams
                    if team.qualified
                ],
            }
            for semifinal in semifinals
        ],
        "finalists": [
            team_to_dict(team)
            for semifinal in semifinals
            for team in semifinal.teams
            if team.qualified
        ],
    }


def main() -> int:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "NK-Schoolschaak-Stats/1.0 (+local team composition tool)",
        }
    )

    semifinals = [
        build_semifinal(session, semifinal_id, config)
        for semifinal_id, config in SOURCES.items()
    ]

    payload = to_json(semifinals)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {DATA_PATH}")
    print(
        f"Finalists: {payload['summary']['finalist_teams']} teams, "
        f"{payload['summary']['player_count']} players"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
