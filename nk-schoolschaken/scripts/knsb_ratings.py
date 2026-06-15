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
        cache_key = f"netstand:{player_id}" if player_id else f"name:{name}"
        cached = self.cache["players"].get(cache_key)
        if cached and "relatienummer" in cached:
            return cached["relatienummer"]

        relatienummer: int | None = None
        if player_id:
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


def apply_ratings_to_player(player: dict[str, Any], ratings: KnsbRatings) -> None:
    player["knsb_relatienummer"] = ratings.relatienummer
    player["knsb_classic"] = ratings.classic
    player["knsb_rapid"] = ratings.rapid
    player["ratingviewer_url"] = ratings.ratingviewer_url


def player_key(player: dict[str, Any]) -> tuple[str, str | None]:
    return (player["name"], player.get("player_id"))


def update_team_knsb_stats(team: dict[str, Any]) -> None:
    players = team["players"]
    knsb_classic = [player["knsb_classic"] for player in players if player.get("knsb_classic")]
    knsb_rapid = [player["knsb_rapid"] for player in players if player.get("knsb_rapid")]
    team["avg_knsb_classic"] = (
        round(sum(knsb_classic) / len(knsb_classic), 1) if knsb_classic else None
    )
    team["avg_knsb_rapid"] = (
        round(sum(knsb_rapid) / len(knsb_rapid), 1) if knsb_rapid else None
    )
    team["top_knsb_classic"] = max(knsb_classic) if knsb_classic else None
    team["top_knsb_rapid"] = max(knsb_rapid) if knsb_rapid else None


def summarize_knsb_players(teams: list[dict[str, Any]]) -> dict[str, Any]:
    knsb_classic = [
        player["knsb_classic"]
        for team in teams
        for player in team["players"]
        if player.get("knsb_classic")
    ]
    knsb_rapid = [
        player["knsb_rapid"]
        for team in teams
        for player in team["players"]
        if player.get("knsb_rapid")
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


def enrich_tournament(tournament: dict[str, Any], service: KnsbRatingService) -> int:
    service.ensure_list_ids()
    ratings_by_key: dict[tuple[str, str | None], KnsbRatings] = {}
    unique_players = 0

    for semifinal in tournament["semifinals"]:
        for team in semifinal["teams"]:
            for index, player in enumerate(team["players"], start=1):
                key = player_key(player)
                if key not in ratings_by_key:
                    ratings_by_key[key] = service.get_ratings(player["name"], player.get("player_id"))
                    unique_players += 1
                    if unique_players % 25 == 0:
                        print(f"  resolved {unique_players} players")
                apply_ratings_to_player(player, ratings_by_key[key])
            update_team_knsb_stats(team)

    for team in tournament["finalists"]:
        for player in team["players"]:
            apply_ratings_to_player(player, ratings_by_key[player_key(player)])
        update_team_knsb_stats(team)

    for semifinal in tournament["semifinals"]:
        semifinal["summary"] = {
            **semifinal["summary"],
            **summarize_knsb_players(semifinal["teams"]),
        }

    tournament["summary"] = {
        **tournament["summary"],
        **summarize_knsb_players(tournament["finalists"]),
    }
    tournament["ratings_fetched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return len({ratings.relatienummer for ratings in ratings_by_key.values() if ratings.relatienummer})
