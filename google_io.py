from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Dict, Any, Optional
from pathlib import Path
import streamlit as st
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials


# ---------------------------------------------------------
# Konfiguration & client
# ---------------------------------------------------------
@lru_cache(maxsize=1)
def load_config() -> Dict[str, Any]:
    """
    Cloud: bruger st.secrets
    Lokalt: bruger config.json hvis den findes
    """
    # 1) Streamlit Cloud (secrets findes)
    if hasattr(st, "secrets") and "app" in st.secrets:
        return dict(st.secrets["app"])

    # 2) Lokalt fallback
    cfg_path = Path("config.json")
    if cfg_path.exists():
        return json.loads(cfg_path.read_text(encoding="utf-8"))

    raise FileNotFoundError(
        "Mangler config. Opret config.json lokalt eller sæt [app] i Streamlit Secrets."
    )

@lru_cache(maxsize=1)
def get_gsheet_client() -> gspread.client.Client:
    cfg = load_config()

    # Cloud: brug secrets
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )
        return gspread.authorize(creds)

    # Lokalt: brug filsti fra config.json
    creds = Credentials.from_service_account_file(
        cfg["service_account_file"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds)


# ---------------------------------------------------------
# Spillere fra "truppen"
# ---------------------------------------------------------
def load_players() -> List[Dict[str, Any]]:
    cfg = load_config()
    client = get_gsheet_client()

    sheet = client.open_by_key(cfg["truppen_sheet_id"]).worksheet("truppen")
    rows = sheet.get_all_values()

    # række 5 = header (index 4), data starter i række 6 (index 5)
    data_rows = rows[5:]

    players: List[Dict[str, Any]] = []
    for r in data_rows:
        if len(r) < 5:
            continue
        if not r[1]:
            continue

        players.append(
            {
                "name": r[1],
                "pos_primary": r[2] if len(r) > 2 else "",
                "pos_secondary": r[3] if len(r) > 3 else "",
                "team_primary": r[4] if len(r) > 4 else "",
                "team_secondary": r[5] if len(r) > 5 else "",
            }
        )

    return players


# ---------------------------------------------------------
# Statistik-ark (eksisterende Google Sheet)
# Struktur (ny):
# Timestamp | MatchID | Half | Player | Event | Position | Team | Delta | MetaValue
# ---------------------------------------------------------
@lru_cache(maxsize=1)
def _get_stats_spreadsheet() -> gspread.Spreadsheet:
    cfg = load_config()
    client = get_gsheet_client()
    return client.open_by_key(cfg["stats_sheet_id"])


def get_stats_worksheet() -> gspread.Worksheet:
    ss = _get_stats_spreadsheet()
    ws = ss.sheet1

    # Sørg for header
    header = ws.row_values(1)
    expected = [
        "Timestamp",
        "MatchID",
        "Half",
        "Player",
        "Event",
        "Position",
        "Team",
        "Delta",
        "MetaValue",
    ]

    # Hvis arket er tomt eller har "gammel" header, så skriver vi ny header i A1:I1.
    # (Dette overskriver kun header-rækken, ikke data)
    if not header or header[:2] != ["Timestamp", "MatchID"] or len(header) < 7:
        ws.update("A1:I1", [expected])

    # Hvis header er gammel (fx uden Half/MetaValue), så udvid den forsigtigt
    # uden at være alt for smart: vi sikrer minimum expected længde.
    if header and header[:2] == ["Timestamp", "MatchID"] and len(header) < len(expected):
        ws.update("A1:I1", [expected])

    return ws


def _event_to_row(event: Dict[str, Any]) -> List[Any]:
    # robust defaults
    ts = event.get("timestamp", "")
    match_id = event.get("match_id", "")
    half = event.get("half", "")
    player = event.get("player", "")
    ev_name = event.get("event", "")
    pos = event.get("pos_primary", "")
    team = event.get("team_primary", "")
    delta = int(event.get("delta", 1))
    meta = event.get("meta_value", "")

    return [ts, match_id, half, player, ev_name, pos, team, delta, meta]


def write_stats_row(event: Dict[str, Any]) -> None:
    ws = get_stats_worksheet()
    ws.append_row(_event_to_row(event), value_input_option="USER_ENTERED")


def write_stats_rows(events: List[Dict[str, Any]]) -> None:
    """Batch append (hurtigere og færre API calls)."""
    if not events:
        return
    ws = get_stats_worksheet()
    rows = [_event_to_row(e) for e in events]
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# ---------------------------------------------------------
# Matches-ark (fane 'Matches' i samme fil)
# Struktur: MatchID | Date | Team | Opponent
# ---------------------------------------------------------
def get_matches_worksheet() -> gspread.Worksheet:
    ss = _get_stats_spreadsheet()
    try:
        ws = ss.worksheet("Matches")
    except WorksheetNotFound:
        ws = ss.add_worksheet(title="Matches", rows=200, cols=10)
        ws.update("A1:D1", [["MatchID", "Date", "Team", "Opponent"]])
    return ws


def append_match_record(match: Dict[str, Any]) -> None:
    ws = get_matches_worksheet()
    ws.append_row(
        [
            match.get("match_id", ""),
            match.get("date", ""),
            str(match.get("team_number", "")),
            match.get("opponent", ""),
        ],
        value_input_option="USER_ENTERED",
    )


def get_all_matches() -> List[Dict[str, Any]]:
    ws = get_matches_worksheet()
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    data_rows = rows[1:]
    matches: List[Dict[str, Any]] = []
    for r in data_rows:
        if not r or not r[0]:
            continue
        matches.append(
            {
                "match_id": r[0],
                "date": r[1] if len(r) > 1 else "",
                "team_number": r[2] if len(r) > 2 else "",
                "opponent": r[3] if len(r) > 3 else "",
            }
        )
    return matches


def get_stats_for_match(match_id: str) -> List[Dict[str, Any]]:
    ws = get_stats_worksheet()
    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    data_rows = rows[1:]
    events: List[Dict[str, Any]] = []

    for r in data_rows:
        if len(r) < 2:
            continue
        if r[1] != match_id:
            continue

        # ny struktur:
        # 0 ts, 1 match, 2 half, 3 player, 4 event, 5 pos, 6 team, 7 delta, 8 meta
        half = r[2] if len(r) > 2 else ""
        player = r[3] if len(r) > 3 else ""
        ev_name = r[4] if len(r) > 4 else ""
        pos = r[5] if len(r) > 5 else ""
        team = r[6] if len(r) > 6 else ""

        delta = 1
        if len(r) > 7 and str(r[7]).strip() != "":
            try:
                delta = int(float(r[7]))
            except ValueError:
                delta = 1

        meta = r[8] if len(r) > 8 else ""

        events.append(
            {
                "timestamp": r[0] if len(r) > 0 else "",
                "match_id": match_id,
                "half": half,
                "player": player,
                "event": ev_name,
                "pos_primary": pos,
                "team_primary": team,
                "delta": delta,
                "meta_value": meta,
            }
        )

    return events
