"""Shared helpers for tournament.json and ratings.json."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOURNAMENT_PATH = ROOT / "data" / "tournament.json"
RATINGS_PATH = ROOT / "data" / "ratings.json"

PLAYER_RATING_FIELDS = (
    "knsb_relatienummer",
    "knsb_classic",
    "knsb_rapid",
    "ratingviewer_url",
    "resolved_name",
)

TEAM_RATING_FIELDS = (
    "avg_knsb_classic",
    "avg_knsb_rapid",
    "top_knsb_classic",
    "top_knsb_rapid",
)

KNSB_SUMMARY_FIELDS = (
    "knsb_classic_count",
    "avg_knsb_classic",
    "avg_knsb_rapid",
)

# Netstand placeholders mapped to known KNSB members.
PLAYER_OVERRIDES: dict[str, dict[str, Any]] = {
    "-1": {
        "resolved_name": "Bram ten Dam",
        "relatienummer": 8975340,
    },
}


def player_storage_key(player: dict[str, Any]) -> str:
    player_id = player.get("player_id")
    if player_id is not None and str(player_id) != "":
        return str(player_id)
    return f"name:{player['name']}"


def extract_player_ratings(player: dict[str, Any]) -> dict[str, Any] | None:
    payload = {"name": player["name"]}
    has_rating = False
    for field in PLAYER_RATING_FIELDS:
        if field in player and player[field] is not None:
            payload[field] = player[field]
            has_rating = True
    return payload if has_rating else None


def strip_player_ratings(player: dict[str, Any]) -> None:
    for field in PLAYER_RATING_FIELDS:
        player.pop(field, None)


def strip_team_ratings(team: dict[str, Any]) -> None:
    for field in TEAM_RATING_FIELDS:
        team.pop(field, None)
    for player in team.get("players", []):
        strip_player_ratings(player)


def strip_summary_knsb(summary: dict[str, Any]) -> None:
    for field in KNSB_SUMMARY_FIELDS:
        summary.pop(field, None)


def extract_ratings(tournament: dict[str, Any]) -> dict[str, Any]:
    players: dict[str, Any] = {}
    team_stats: dict[str, Any] = {}
    semifinal_summaries: dict[str, Any] = {}

    for semifinal in tournament.get("semifinals", []):
        semi_summary = semifinal.get("summary", {})
        semi_payload = {
            field: semi_summary[field]
            for field in KNSB_SUMMARY_FIELDS
            if field in semi_summary
        }
        if semi_payload:
            semifinal_summaries[semifinal["id"]] = semi_payload

        for team in semifinal.get("teams", []):
            team_payload = {
                field: team[field]
                for field in TEAM_RATING_FIELDS
                if field in team
            }
            if team_payload:
                team_stats[team["id"]] = team_payload
            for player in team.get("players", []):
                rating = extract_player_ratings(player)
                if rating:
                    players[player_storage_key(player)] = rating

    for team in tournament.get("finalists", []):
        team_payload = {
            field: team[field]
            for field in TEAM_RATING_FIELDS
            if field in team
        }
        if team_payload:
            team_stats[team["id"]] = team_payload
        for player in team.get("players", []):
            rating = extract_player_ratings(player)
            if rating:
                players[player_storage_key(player)] = rating

    summary = {
        field: tournament["summary"][field]
        for field in KNSB_SUMMARY_FIELDS
        if field in tournament.get("summary", {})
    }

    return {
        "fetched_at": tournament.get("ratings_fetched_at"),
        "summary": summary,
        "semifinal_summaries": semifinal_summaries,
        "team_stats": team_stats,
        "players": players,
        "overrides": deepcopy(PLAYER_OVERRIDES),
    }


def strip_tournament_ratings(tournament: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(tournament)
    strip_summary_knsb(payload.get("summary", {}))
    payload.pop("ratings_fetched_at", None)

    for semifinal in payload.get("semifinals", []):
        strip_summary_knsb(semifinal.get("summary", {}))
        for team in semifinal.get("teams", []):
            strip_team_ratings(team)

    for team in payload.get("finalists", []):
        strip_team_ratings(team)

    return payload


def apply_player_ratings(player: dict[str, Any], ratings: dict[str, Any] | None) -> None:
    if not ratings:
        return
    for field in PLAYER_RATING_FIELDS:
        if field in ratings:
            player[field] = ratings[field]


def apply_ratings_to_tournament(tournament: dict[str, Any], ratings: dict[str, Any]) -> None:
    player_ratings = ratings.get("players", {})
    team_stats = ratings.get("team_stats", {})

    if ratings.get("summary"):
        tournament["summary"] = {
            **tournament.get("summary", {}),
            **ratings["summary"],
        }

    for semifinal in tournament.get("semifinals", []):
        semi_summary = ratings.get("semifinal_summaries", {}).get(semifinal["id"])
        if semi_summary:
            semifinal["summary"] = {**semifinal.get("summary", {}), **semi_summary}
        for team in semifinal.get("teams", []):
            apply_player_ratings_to_team(team, player_ratings, team_stats)

    for team in tournament.get("finalists", []):
        apply_player_ratings_to_team(team, player_ratings, team_stats)

    if ratings.get("fetched_at"):
        tournament["ratings_fetched_at"] = ratings["fetched_at"]


def apply_player_ratings_to_team(
    team: dict[str, Any],
    player_ratings: dict[str, Any],
    team_stats: dict[str, Any],
) -> None:
    stats = team_stats.get(team["id"])
    if stats:
        team.update(stats)
    for player in team.get("players", []):
        apply_player_ratings(player, player_ratings.get(player_storage_key(player)))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
