"""All PSN access (via psnawp) lives here: fetching the game library and,
for a given set of titles, their full trophy list with earn dates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from psnawp_api import PSNAWP
from psnawp_api.core.psnawp_exceptions import PSNAWPError
from psnawp_api.models.title_stats import PlatformCategory
from psnawp_api.models.trophies import PlatformType

PLATFORM_LABEL = {PlatformCategory.PS4: "PS4", PlatformCategory.PS5: "PS5"}

# psnawp self-rate-limits to 300 req / 15 min; keep trophy batches small.
TROPHY_BATCH_SIZE = 5


@dataclass
class GameRow:
    title_id: str
    np_communication_id: str | None
    title: str
    system: str
    playtime_hours: float
    play_count: int
    last_played: datetime | None


@dataclass
class TrophyDefRow:
    np_communication_id: str
    trophy_id: int
    trophy_name: str | None
    trophy_type: str | None
    trophy_detail: str | None


@dataclass
class TrophyProgressRow:
    title_id: str
    trophy_id: int
    np_communication_id: str
    earned: bool
    earned_at: datetime | None
    rarity: str | None


def authenticate(npsso: str):
    """Return (psnawp, client). Raises on bad/expired NPSSO."""
    psnawp = PSNAWP(npsso)
    client = psnawp.me()
    return psnawp, client


def fetch_games(client) -> list[GameRow]:
    """Full PS4/PS5 library with cumulative playtime. np_communication_id is
    filled in later, from the trophy summary call.
    """
    games: list[GameRow] = []
    for stat in client.title_stats(page_size=100):
        duration = getattr(stat, "play_duration", None)
        playtime_hours = round(duration.total_seconds() / 3600.0, 2) if duration else 0.0
        system = PLATFORM_LABEL.get(getattr(stat, "category", None), "OTHER")
        games.append(
            GameRow(
                title_id=getattr(stat, "title_id", "") or "",
                np_communication_id=None,
                title=stat.name or "Unknown",
                system=system,
                playtime_hours=playtime_hours,
                play_count=getattr(stat, "play_count", 0) or 0,
                last_played=getattr(stat, "last_played_date_time", None),
            )
        )
    return games


def fetch_trophies_for_titles(
    client,
    title_ids: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[list[TrophyDefRow], list[TrophyProgressRow], dict[str, str]]:
    """Full trophy list + earn status for the given titles.

    Returns (definitions, progress, {title_id: np_communication_id}). Only call
    this for titles whose playtime/play_count actually changed since the last
    sync, to keep request volume low. ``on_progress(done, total)`` is called
    after each batch so long runs aren't silent.
    """
    definitions: list[TrophyDefRow] = []
    progress: list[TrophyProgressRow] = []
    comm_ids: dict[str, str] = {}
    total_batches = (len(title_ids) + TROPHY_BATCH_SIZE - 1) // TROPHY_BATCH_SIZE

    for i in range(0, len(title_ids), TROPHY_BATCH_SIZE):
        batch = title_ids[i : i + TROPHY_BATCH_SIZE]
        try:
            summaries = list(client.trophy_titles_for_title(batch))
        except PSNAWPError:
            if on_progress is not None:
                on_progress(i // TROPHY_BATCH_SIZE + 1, total_batches)
            continue  # whole batch unavailable (rate limit, private set); skip and move on

        for summary in summaries:
            title_id = summary.np_title_id
            if not title_id:
                continue
            comm_ids[title_id] = summary.np_communication_id
            # title_platform often comes back UNKNOWN; np_service_name reliably
            # tells PS4/PS3/Vita ("trophy") from PS5 ("trophy2").
            platform = (
                PlatformType.PS5
                if summary.np_service_name == "trophy2"
                else PlatformType.PS4
            )
            try:
                trophies = list(
                    client.trophies(summary.np_communication_id, platform, include_progress=True)
                )
            except PSNAWPError:
                # e.g. no "default" trophy group for this title; best-effort, skip it
                continue

            for trophy in trophies:
                definitions.append(
                    TrophyDefRow(
                        np_communication_id=summary.np_communication_id,
                        trophy_id=trophy.trophy_id,
                        trophy_name=trophy.trophy_name,
                        trophy_type=trophy.trophy_type.value if trophy.trophy_type else None,
                        trophy_detail=trophy.trophy_detail,
                    )
                )
                progress.append(
                    TrophyProgressRow(
                        title_id=title_id,
                        trophy_id=trophy.trophy_id,
                        np_communication_id=summary.np_communication_id,
                        earned=bool(trophy.earned),
                        earned_at=trophy.earned_date_time,
                        rarity=trophy.trophy_rarity.value if trophy.trophy_rarity else None,
                    )
                )
        if on_progress is not None:
            on_progress(i // TROPHY_BATCH_SIZE + 1, total_batches)
    return definitions, progress, comm_ids
