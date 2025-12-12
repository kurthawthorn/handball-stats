from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, List


STAT_TYPES: List[str] = [
    "Mål",
    "Assist",
    "Frikast",
    "Redning",
    "Gult kort",
    "2 min",
    "Rødt kort",
    ]


def create_match_id(match_date: date, team_number: str, opponent: str) -> str:
    opp_clean = opponent.strip().replace(" ", "_")
    return f"{match_date.strftime('%Y-%m-%d')}_H{team_number}_{opp_clean}"


def create_match(match_date: date, team_number: str, opponent: str) -> Dict[str, Any]:
    match_id = create_match_id(match_date, team_number, opponent)
    return {
        "match_id": match_id,
        "date": match_date.strftime("%Y-%m-%d"),
        "team_number": team_number,
        "opponent": opponent.strip(),
    }


def build_event(
    player: Dict[str, Any], event_type: str, match_id: str
) -> Dict[str, Any]:
    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match_id": match_id,
        "player": player["name"],
        "event": event_type,
        "pos_primary": player["pos_primary"],
        "team_primary": player["team_primary"],
    }
