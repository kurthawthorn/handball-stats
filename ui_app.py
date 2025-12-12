from __future__ import annotations

from datetime import date
from typing import List, Dict, Any
from collections import defaultdict

import pandas as pd
import streamlit as st

from google_io import load_players, append_match_record, write_stats_rows
from stats_engine import create_match, build_event


st.set_page_config(page_title="Håndbold Stats", layout="wide")


# --------------------------------------------------
# Konfiguration
# --------------------------------------------------
EVENT_TYPES = [
    ("Mål", "M"),
    ("Assist", "A"),
    ("Frikast", "F"),
    ("Redning", "R"),
    ("Gult kort", "G"),
    ("2 min", "2"),
    ("Rødt kort", "X"),
]


@st.cache_data(ttl=600)
def get_cached_players() -> List[Dict[str, Any]]:
    return load_players()


# --------------------------------------------------
# Session state
# --------------------------------------------------
defaults = {
    "wizard_step": 1,
    "current_match": None,
    "match_players": [],
    "events": [],
    "selected_event": None,
    "selected_player": None,
    "current_half": 1,
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def find_player(players: List[Dict[str, Any]], name: str) -> Dict[str, Any] | None:
    if not name:
        return None
    return next((p for p in players if p["name"] == name), None)


def make_meta_event(match_id: str, event: str, value: str) -> Dict[str, Any]:
    return {
        "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match_id": match_id,
        "half": st.session_state["current_half"],
        "player": "",
        "event": event,
        "pos_primary": "",
        "team_primary": "",
        "delta": 0,
        "meta_value": value,
    }


# --------------------------------------------------
# Dialogs
# --------------------------------------------------
@st.dialog("Halvlegsresultat")
def half_dialog(match_id: str):
    c1, c2 = st.columns(2)
    with c1:
        ours = st.number_input("Vores mål", min_value=0, step=1)
    with c2:
        opp = st.number_input("Modstander mål", min_value=0, step=1)

    if st.button("Gem", type="primary", use_container_width=True):
        st.session_state["events"].append(
            make_meta_event(match_id, "HALVLEG_RESULTAT", f"{ours}-{opp}")
        )
        st.rerun()


@st.dialog("Afslut kamp")
def end_dialog(match_id: str, players: List[Dict[str, Any]]):
    c1, c2 = st.columns(2)
    with c1:
        ours = st.number_input("Vores mål (slut)", min_value=0, step=1)
    with c2:
        opp = st.number_input("Modstander mål (slut)", min_value=0, step=1)

    mvp = st.selectbox("Kampens spiller", [p["name"] for p in players])
    comment = st.text_area("Kommentar", height=120)

    if st.button("Gem og afslut kamp", type="primary", use_container_width=True):
        st.session_state["events"].extend([
            make_meta_event(match_id, "SLUT_RESULTAT", f"{ours}-{opp}"),
            make_meta_event(match_id, "KAMPENS_SPILLER", mvp),
            make_meta_event(match_id, "KOMMENTAR", comment.strip()),
        ])

        # 🔥 BATCH WRITE – ÉN GANG
        write_stats_rows(st.session_state["events"])

        # videre til opsummering
        st.session_state["wizard_step"] = 4
        st.rerun()


# --------------------------------------------------
# Step 1 – Opret kamp
# --------------------------------------------------
def step_create_match():
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        team = st.selectbox("Hold", ["1", "2", "3"])
    with c2:
        d = st.date_input("Dato", value=date.today())
    with c3:
        opp = st.text_input("Modstander")

    if st.button("Opret kamp", type="primary", use_container_width=True):
        match = create_match(d, team, opp)
        append_match_record(match)
        st.session_state.update({
            "current_match": match,
            "wizard_step": 2,
            "events": [],
            "selected_event": None,
            "selected_player": None,
            "current_half": 1,
        })
        st.rerun()


# --------------------------------------------------
# Step 2 – Vælg spillere
# --------------------------------------------------
def step_select_players(players):
    st.subheader("Vælg spillere til kampen")

    col1, col2 = st.columns(2)

    with col1:
        team_filter = st.selectbox(
            "Hold",
            ["Alle", "1", "2", "3", "X"],
            index=0,
        )

    with col2:
        positions = sorted({p["pos_primary"] for p in players if p["pos_primary"]})
        pos_filter = st.selectbox(
            "Primær position",
            ["Alle"] + positions,
            index=0,
        )

    filtered = players
    if team_filter != "Alle":
        filtered = [p for p in filtered if str(p["team_primary"]) == team_filter]

    if pos_filter != "Alle":
        filtered = [p for p in filtered if p["pos_primary"] == pos_filter]

    selected = st.multiselect(
        "Spillere i kampen",
        options=[p["name"] for p in filtered],
        default=[p["name"] for p in filtered],  # auto-vælg filtreret hold
    )

    if st.button("Start kamp", type="primary", use_container_width=True):
        if not selected:
            st.warning("Vælg mindst én spiller.")
            return

        st.session_state["match_players"] = [
            p for p in players if p["name"] in selected
        ]
        st.session_state["wizard_step"] = 3
        st.rerun()



# --------------------------------------------------
# Step 3 – Registrering
# --------------------------------------------------
def step_record():
    match = st.session_state["current_match"]
    players = st.session_state["match_players"]

    # CSS til aktiv halvleg
    st.markdown("""
    <style>
    /* Default look for half buttons */
    button[data-testid="baseButton-secondary"][aria-label="half_1_btn"],
    button[data-testid="baseButton-secondary"][aria-label="half_2_btn"]{
        border-radius: 10px !important;
        height: 3rem !important;
        font-weight: 700 !important;
    }

    /* Selected half – we toggle via inline style hooks below */
    </style>
    """, unsafe_allow_html=True)


    # tællere
    counts = defaultdict(int)
    for e in st.session_state["events"]:
        if e.get("player"):
            counts[(e["player"], e["event"])] += 1

    # topbar (1, 2, Halvleg, Registrer, Afslut)
    t = st.columns([1, 1, 1, 1, 1])

    # Half 1
    with t[0]:
        is_sel = st.session_state["current_half"] == 1
        st.button(
            f"{'✅ ' if is_sel else ''}1",
            key="btn_half_1",
            use_container_width=True,
            on_click=lambda: st.session_state.update({"current_half": 1}),
        )

    # Half 2
    with t[1]:
        is_sel = st.session_state["current_half"] == 2
        st.button(
            f"{'✅ ' if is_sel else ''}2",
            key="btn_half_2",
            use_container_width=True,
            on_click=lambda: st.session_state.update({"current_half": 2}),
        )

    # Halvleg-popup
    with t[2]:
        st.button(
            "Halvleg",
            key="btn_half_dialog",
            use_container_width=True,
            on_click=lambda: half_dialog(match["match_id"]),
        )

    # Registrer (instant + rerun)
    with t[3]:
        can = bool(st.session_state.get("selected_event")) and bool(st.session_state.get("selected_player"))
        if st.button(
            "Registrer",
            key="btn_register",
            type="primary",
            disabled=not can,
            use_container_width=True,
        ):
            p = find_player(players, st.session_state["selected_player"])
            if not p:
                st.warning("Vælg spiller igen.")
                st.session_state["selected_player"] = None
                st.rerun()

            ev = build_event(p, st.session_state["selected_event"], match["match_id"])
            ev["half"] = st.session_state["current_half"]
            st.session_state["events"].append(ev)

            # reset UI INSTANT
            st.session_state["selected_event"] = None
            st.session_state["selected_player"] = None
            st.rerun()

    # Afslut popup
    with t[4]:
        st.button(
            "Afslut",
            key="btn_end_dialog",
            use_container_width=True,
            on_click=lambda: end_dialog(match["match_id"], players),
        )

    st.divider()

    left, right = st.columns([1, 2])

    # Event types (vælg type)
    with left:
        for label, code in EVENT_TYPES:
            is_sel = st.session_state.get("selected_event") == label
            st.button(
                f"{'✅ ' if is_sel else ''}{label}",
                key=f"type_{code}",
                use_container_width=True,
                on_click=lambda l=label: st.session_state.update({"selected_event": l}),
            )

    # Players (vælg spiller)
    with right:
        for p in players:
            name = p["name"]
            badge = " ".join(
                f"{code}:{counts[(name, label)]}"
                for label, code in EVENT_TYPES
                if counts[(name, label)] > 0
            )

            c1, c2 = st.columns([3, 1])
            with c1:
                is_sel = st.session_state.get("selected_player") == name
                st.button(
                    f"{'✅ ' if is_sel else ''}{name}",
                    key=f"player_{name}",
                    use_container_width=True,
                    on_click=lambda n=name: st.session_state.update({"selected_player": n}),
                )
            with c2:
                st.write(badge)

# --------------------------------------------------
# Step 4 – Opsummering
# --------------------------------------------------
def step_summary():
    st.subheader("Kamp afsluttet")
    st.write("Klar til næste kamp.")

    if st.button("Start ny kamp", type="primary", use_container_width=True):
        for k in defaults:
            st.session_state[k] = defaults[k]
        st.rerun()


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    players = get_cached_players()
    step = st.session_state["wizard_step"]

    if step == 1:
        step_create_match()
    elif step == 2:
        step_select_players(players)
    elif step == 3:
        step_record()
    else:
        step_summary()


if __name__ == "__main__":
    main()
