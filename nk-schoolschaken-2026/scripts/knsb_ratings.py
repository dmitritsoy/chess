"""Fetch official KNSB classic and rapid ratings from ratingviewer.nl."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from ratings_data import (
    PLAYER_OVERRIDES,
    player_storage_key,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data" / "rating_cache.json"
RATINGVIEWER_BASE = "https://ratingviewer.nl"
NETSTAND_BASE = "https://knsb.netstand.nl"
REQUEST_DELAY = 0.12

RELATIENUMMER_RE = re.compile(
    r"ratingviewer\.nl/list/latest(?:-[A-Z])?/players/(\d+)/statistics"
)


@dataclass
class KnsbRatings:
    relatienummer: int | None
    classic: int | None
    rapid: int | None
    ratingviewer_url: str | None


class KnsbRatingService:
    def __init__(self, session: requests.Session) -> None:
        self.session = session
        self.cache = self._load_cache()
        self.classic_list_id: int | None = None
        self.rapid_list_id: int | None = None
        self._metrics_cache: dict[int, list[dict[str, Any]]] = {}

    def _load_cache(self) -> dict[str, Any]:
        if not CACHE_PATH.exists():
            return {"players": {}, "metrics": {}, "list_ids": {}}
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    def save_cache(self) -> None:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(self.cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _get_json(self, url: str) -> Any:
        time.sleep(REQUEST_DELAY)
        response = self.session.get(
            url,
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        response.raise_for_status()
        return response.json()

    def ensure_list_ids(self) -> None:
        cached = self.cache.get("list_ids", {})
        if cached.get("classic") and cached.get("rapid"):
            self.classic_list_id = cached["classic"]
            self.rapid_list_id = cached["rapid"]
            return

        data = self._get_json(f"{RATINGVIEWER_BASE}/rating-lists/index.json")
        classic = next(item for item in data["items"] if item["category"] == "C")
        rapid = next(item for item in data["items"] if item["category"] == "R")
        self.classic_list_id = classic["list_id"]
        self.rapid_list_id = rapid["list_id"]
        self.cache["list_ids"] = {
            "classic": self.classic_list_id,
            "rapid": self.rapid_list_id,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def ratingviewer_url(self, relatienummer: int) -> str:
        list_id = self.classic_list_id or 181
        return f"{RATINGVIEWER_BASE}/lists/{list_id}/players/{relatienummer}"

    def _search_query(self, name: str) -> str:
        paren_match = re.search(r"\(([^)]+)\)", name)
        if "," in name and paren_match:
            achternaam = name.split("(")[0].split(",")[0].strip()
            voornaam = paren_match.group(1).strip()
            return f"{voornaam} {achternaam}"
        return re.sub(r"\s+", " ", name).strip()

    def _pick_search_result(self, name: str, results: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not results:
            return None
        if len(results) == 1:
            return results[0]

        query = self._search_query(name).casefold()
        tokens = [token for token in re.split(r"[\s,()]+", query) if token]

        def score(result: dict[str, Any]) -> int:
            candidate = " ".join(
                part
                for part in [
                    result.get("voornaam", ""),
                    result.get("tussenvoegsels") or "",
                    result.get("achternaam", ""),
                ]
                if part
            ).casefold()
            return sum(1 for token in tokens if token in candidate)

        ranked = sorted(results, key=score, reverse=True)
        if ranked and score(ranked[0]) > 0:
            return ranked[0]
        return None

    def resolve_relatienummer(self, name: str, player_id: str | None = None) -> int | None:
        if player_id and str(player_id) in PLAYER_OVERRIDES:
            override = PLAYER_OVERRIDES[str(player_id)]
            relatienummer = override["relatienummer"]
            cache_key = f"netstand:{player_id}"
            self.cache["players"][cache_key] = {
                "name": name,
                "player_id": player_id,
                "relatienummer": relatienummer,
                "resolved_name": override.get("resolved_name"),
            }
            return relatienummer

        cache_key = f"netstand:{player_id}" if player_id else f"name:{name}"
        cached = self.cache["players"].get(cache_key)
        if cached and "relatienummer" in cached:
            return cached["relatienummer"]

        relatienummer: int | None = None
        if player_id and str(player_id) != "-1":
            time.sleep(REQUEST_DELAY)
            response = self.session.get(
                f"{NETSTAND_BASE}/players/view/{player_id}",
                timeout=30,
                headers={"User-Agent": "NK-Schoolschaak-Stats/1.0"},
            )
            response.raise_for_status()
            match = RELATIENUMMER_RE.search(response.text)
            if match:
                relatienummer = int(match.group(1))

        if relatienummer is None:
            query = quote(self._search_query(name))
            results = self._get_json(f"{RATINGVIEWER_BASE}/players/find.json?query={query}")
            picked = self._pick_search_result(name, results)
            if picked:
                relatienummer = picked["relatienummer"]

        self.cache["players"][cache_key] = {
            "name": name,
            "player_id": player_id,
            "relatienummer": relatienummer,
        }
        return relatienummer

    def _metrics_for(self, relatienummer: int) -> list[dict[str, Any]]:
        if relatienummer in self._metrics_cache:
            return self._metrics_cache[relatienummer]

        cache_key = str(relatienummer)
        if cache_key in self.cache["metrics"]:
            metrics = self.cache["metrics"][cache_key]
        else:
            metrics = self._get_json(
                f"{RATINGVIEWER_BASE}/metrics/forRelatienr/{relatienummer}.json"
            )
            self.cache["metrics"][cache_key] = metrics

        self._metrics_cache[relatienummer] = metrics
        return metrics

    def _rating_on_list(self, relatienummer: int, list_id: int | None) -> int | None:
        if list_id is None:
            return None
        entries = [entry for entry in self._metrics_for(relatienummer) if entry["list_id"] == list_id]
        if not entries:
            return None
        latest = max(entries, key=lambda entry: entry["moment"])
        rating = latest.get("rating")
        return int(rating) if rating is not None else None

    def get_ratings(self, name: str, player_id: str | None = None) -> KnsbRatings:
        self.ensure_list_ids()
        relatienummer = self.resolve_relatienummer(name, player_id)
        if relatienummer is None:
            return KnsbRatings(None, None, None, None)

        return KnsbRatings(
            relatienummer=relatienummer,
            classic=self._rating_on_list(relatienummer, self.classic_list_id),
            rapid=self._rating_on_list(relatienummer, self.rapid_list_id),
            ratingviewer_url=self.ratingviewer_url(relatienummer),
        )


def player_key(player: dict[str, Any]) -> tuple[str, str | None]:
    return (player["name"], player.get("player_id"))


def ratings_to_player_entry(
    player: dict[str, Any],
    ratings: KnsbRatings,
) -> dict[str, Any]:
    entry = {"name": player["name"]}
    if ratings.relatienummer is not None:
        entry["knsb_relatienummer"] = ratings.relatienummer
    if ratings.classic is not None:
        entry["knsb_classic"] = ratings.classic
    if ratings.rapid is not None:
        entry["knsb_rapid"] = ratings.rapid
    if ratings.ratingviewer_url is not None:
        entry["ratingviewer_url"] = ratings.ratingviewer_url

    player_id = player.get("player_id")
    if player_id and str(player_id) in PLAYER_OVERRIDES:
        entry["resolved_name"] = PLAYER_OVERRIDES[str(player_id)].get("resolved_name")

    return entry


def update_team_knsb_stats(
    team: dict[str, Any],
    player_ratings: dict[str, Any],
) -> dict[str, Any]:
    players = team["players"]
    knsb_classic = [
        player_ratings[player_storage_key(player)]["knsb_classic"]
        for player in players
        if player_ratings.get(player_storage_key(player), {}).get("knsb_classic") is not None
    ]
    knsb_rapid = [
        player_ratings[player_storage_key(player)]["knsb_rapid"]
        for player in players
        if player_ratings.get(player_storage_key(player), {}).get("knsb_rapid") is not None
    ]
    return {
        "avg_knsb_classic": (
            round(sum(knsb_classic) / len(knsb_classic), 1) if knsb_classic else None
        ),
        "avg_knsb_rapid": (
            round(sum(knsb_rapid) / len(knsb_rapid), 1) if knsb_rapid else None
        ),
        "top_knsb_classic": max(knsb_classic) if knsb_classic else None,
        "top_knsb_rapid": max(knsb_rapid) if knsb_rapid else None,
    }


def summarize_knsb_players(
    teams: list[dict[str, Any]],
    player_ratings: dict[str, Any],
) -> dict[str, Any]:
    knsb_classic = [
        player_ratings[player_storage_key(player)]["knsb_classic"]
        for team in teams
        for player in team["players"]
        if player_ratings.get(player_storage_key(player), {}).get("knsb_classic") is not None
    ]
    knsb_rapid = [
        player_ratings[player_storage_key(player)]["knsb_rapid"]
        for team in teams
        for player in team["players"]
        if player_ratings.get(player_storage_key(player), {}).get("knsb_rapid") is not None
    ]
    return {
        "knsb_classic_count": len(knsb_classic),
        "avg_knsb_classic": (
            round(sum(knsb_classic) / len(knsb_classic), 1) if knsb_classic else None
        ),
        "avg_knsb_rapid": (
            round(sum(knsb_rapid) / len(knsb_rapid), 1) if knsb_rapid else None
        ),
    }


def build_ratings(tournament: dict[str, Any], service: KnsbRatingService) -> dict[str, Any]:
    service.ensure_list_ids()
    ratings_by_key: dict[tuple[str, str | None], KnsbRatings] = {}
    player_entries: dict[str, Any] = {}
    team_stats: dict[str, Any] = {}
    unique_players = 0

    def store_player(player: dict[str, Any]) -> None:
        nonlocal unique_players
        lookup_key = player_key(player)
        if lookup_key not in ratings_by_key:
            ratings_by_key[lookup_key] = service.get_ratings(
                player["name"],
                player.get("player_id"),
            )
            unique_players += 1
            if unique_players % 25 == 0:
                print(f"  resolved {unique_players} players")
        entry = ratings_to_player_entry(player, ratings_by_key[lookup_key])
        player_entries[player_storage_key(player)] = entry

    for semifinal in tournament["semifinals"]:
        for team in semifinal["teams"]:
            for player in team["players"]:
                store_player(player)
            team_stats[team["id"]] = update_team_knsb_stats(team, player_entries)

    for team in tournament["finalists"]:
        for player in team["players"]:
            store_player(player)
        team_stats[team["id"]] = update_team_knsb_stats(team, player_entries)

    semifinal_summaries = {
        semifinal["id"]: summarize_knsb_players(semifinal["teams"], player_entries)
        for semifinal in tournament["semifinals"]
    }

    return {
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary": summarize_knsb_players(tournament["finalists"], player_entries),
        "semifinal_summaries": semifinal_summaries,
        "team_stats": team_stats,
        "players": player_entries,
        "overrides": dict(PLAYER_OVERRIDES),
    }


def enrich_tournament(tournament: dict[str, Any], service: KnsbRatingService) -> int:
    """Backward-compatible helper that merges ratings into a tournament payload."""
    from ratings_data import apply_ratings_to_tournament

    ratings = build_ratings(tournament, service)
    apply_ratings_to_tournament(tournament, ratings)
    return len(
        {
            entry["knsb_relatienummer"]
            for entry in ratings["players"].values()
            if entry.get("knsb_relatienummer")
        }
    )
