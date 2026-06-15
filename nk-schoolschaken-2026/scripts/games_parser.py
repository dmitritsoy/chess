"""Parse individual games from KNSB Netstand pairings and Sevilla team pages."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

NETSTAND_BASE = "https://knsb.netstand.nl"
PLACEHOLDER_PLAYER_NAME = "NO"


@dataclass
class Game:
    round: int | None
    board: int
    color: str
    opponent: str
    opponent_team: str
    team_match: str
    result: str
    points: float


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def is_placeholder_player(name: str) -> bool:
    return clean_name(name).upper() == PLACEHOLDER_PLAYER_NAME


def parse_result_score(result: str) -> tuple[float, float]:
    normalized = (
        result.replace("\xa0", " ")
        .replace("−", "-")
        .replace("–", "-")
        .replace(",", ".")
        .replace("Â½", ".5")
        .replace("½", ".5")
        .replace("1/2", ".5")
    )

    if "-" not in normalized:
        return 0.0, 0.0
    left, right = normalized.split("-", 1)

    def to_score(value: str) -> float:
        value = value.strip()
        if value in {"", "-"}:
            return 0.0
        match = re.match(r"^([0-9]+(?:\.5)?)", value)
        if match:
            return float(match.group(1))
        return 0.0

    return to_score(left), to_score(right)


def player_result(home_score: float, away_score: float, is_home: bool) -> tuple[str, float]:
    score = home_score if is_home else away_score
    opp = away_score if is_home else home_score
    if score > opp:
        return "1-0", 1.0
    if score < opp:
        return "0-1", 0.0
    return "½-½", 0.5


def knsb_team_pairing_urls(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for link in soup.find_all("a", href=re.compile(r"/pairings/view/\d+")):
        href = link["href"]
        if href not in urls:
            urls.append(href)
    return urls


def parse_round_number(value: str) -> int | None:
    text = clean_name(value)
    if text.isdigit():
        return int(text)
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else None


def knsb_parse_pairing(html: str, team_name: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    header = table.find("thead")
    if not header:
        return []

    header_cells = header.find_all("th")
    home_link = header_cells[1].find("a") if len(header_cells) > 1 else None
    away_link = header_cells[4].find("a") if len(header_cells) > 4 else None
    round_link = header_cells[6].find("a") if len(header_cells) > 6 else None

    home_team = clean_name(home_link.get_text()) if home_link else ""
    away_team = clean_name(away_link.get_text()) if away_link else ""
    round_no = parse_round_number(round_link.get_text()) if round_link else None
    team_match = f"{home_team} - {away_team}"

    if team_name.casefold() not in {home_team.casefold(), away_team.casefold()}:
        return []

    is_home_team = team_name.casefold() == home_team.casefold()
    games: list[dict[str, Any]] = []

    body = table.find("tbody")
    if not body:
        return games

    for board, row in enumerate(body.find_all("tr"), start=1):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        home_player_link = cells[1].find("a")
        away_player_link = cells[4].find("a")
        home_player = clean_name(home_player_link.get_text()) if home_player_link else ""
        away_player = clean_name(away_player_link.get_text()) if away_player_link else ""

        home_score, away_score = parse_result_score(cells[6].get_text())
        if is_home_team:
            player_name = home_player
            opponent_name = away_player
            opponent_team = away_team
            color = "white" if "fas" in cells[0].get("class", []) else "black"
            result, points = player_result(home_score, away_score, True)
        else:
            player_name = away_player
            opponent_name = home_player
            opponent_team = home_team
            color = "white" if "fas" in cells[3].get("class", []) else "black"
            result, points = player_result(home_score, away_score, False)

        games.append(
            {
                "player_name": player_name,
                "player_id": (
                    home_player_link["href"].rstrip("/").split("/")[-1]
                    if is_home_team and home_player_link
                    else away_player_link["href"].rstrip("/").split("/")[-1]
                    if away_player_link
                    else None
                ),
                "game": asdict(
                    Game(
                        round=round_no,
                        board=board,
                        color=color,
                        opponent=opponent_name,
                        opponent_team=opponent_team,
                        team_match=team_match,
                        result=result,
                        points=points,
                    )
                ),
            }
        )

    return games


def sevilla_parse_team_games(html: str, team_name: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = None
    for candidate in soup.find_all("table"):
        if candidate.find("td", class_="GM_White"):
            table = candidate
            break
    if not table:
        return []

    games: list[dict[str, Any]] = []
    round_no: int | None = None
    white_team = ""
    black_team = ""
    board = 0

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        texts = [clean_name(cell.get_text()) for cell in cells]
        if texts[0] == "Nr.":
            continue

        if texts[0].isdigit():
            round_no = int(texts[0])
            white_team = texts[1] if len(texts) > 1 else ""
            black_team = texts[2] if len(texts) > 2 else ""
            board = 0
            continue

        if len(texts) < 3 or not texts[1] or not texts[2]:
            continue

        board += 1
        white_player = texts[1]
        black_player = texts[2]
        raw_result = texts[3] if len(texts) > 3 else ""
        home_score, away_score = parse_result_score(raw_result)
        team_match = f"{white_team} - {black_team}"

        if team_name.casefold() == white_team.casefold():
            result, points = player_result(home_score, away_score, True)
            games.append(
                {
                    "player_name": white_player,
                    "game": asdict(
                        Game(
                            round=round_no,
                            board=board,
                            color="white",
                            opponent=black_player,
                            opponent_team=black_team,
                            team_match=team_match,
                            result=result,
                            points=points,
                        )
                    ),
                }
            )
        elif team_name.casefold() == black_team.casefold():
            result, points = player_result(home_score, away_score, False)
            games.append(
                {
                    "player_name": black_player,
                    "game": asdict(
                        Game(
                            round=round_no,
                            board=board,
                            color="black",
                            opponent=white_player,
                            opponent_team=white_team,
                            team_match=team_match,
                            result=result,
                            points=points,
                        )
                    ),
                }
            )

    return games


def ensure_placeholder_player(
    team: dict[str, Any],
    players_by_name: dict[str, dict[str, Any]],
    name: str,
    player_id: str | None = None,
) -> dict[str, Any]:
    key = clean_name(name).casefold()
    player = players_by_name.get(key)
    if player:
        return player

    player = {
        "name": clean_name(name),
        "rating": None,
        "games": [],
        "points": None,
        "tpr": None,
        "player_id": player_id,
    }
    team["players"].append(player)
    players_by_name[key] = player
    return player


def attach_games_to_players(team: dict[str, Any], raw_games: list[dict[str, Any]]) -> None:
    players_by_name = {clean_name(player["name"]).casefold(): player for player in team["players"]}
    for player in team["players"]:
        player["games"] = []

    for entry in raw_games:
        player_name = clean_name(entry["player_name"])
        player = players_by_name.get(player_name.casefold())
        if not player:
            if not is_placeholder_player(player_name):
                continue
            player = ensure_placeholder_player(
                team,
                players_by_name,
                player_name,
                entry.get("player_id"),
            )
        player["games"].append(entry["game"])

    for player in team["players"]:
        player["games"].sort(
            key=lambda game: (game.get("round") or 0, game.get("board") or 0)
        )


def pairing_url(path: str) -> str:
    return urljoin(NETSTAND_BASE, path)
