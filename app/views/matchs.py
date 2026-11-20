from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import chip, empty_state, fixture_grid, how, section, volet_title
from app.state import get_frozen
from mpg.analysis import Analysis

ENSEMBLE = "Ensemble"


def _match_card(row: pd.Series, away: pd.Series, goals: pd.DataFrame, team_id: int) -> str:
    me = team_id in (row["team_id"], away["team_id"])

    def scorers(tid: int) -> str:
        g = goals[goals["team_id"] == tid]
        if g.empty:
            return "—"
        labels = {"reel": "", "mpg": " (MPG)", "csc": " (CSC)", "rotaldo_csc": " (CSC Rotaldo)", "bloque": " (bloqué)"}
        return "<br>".join(
            escape(f"{r.buteur_affiche.removeprefix('(Bloqué) ')}{labels.get(r.type_but, '')}") for r in g.itertuples()
        )

    def bonus(r: pd.Series) -> str:
        if not r["bonus_poses"]:
            return ""
        return "".join(chip(b.strip()) for b in r["bonus_poses"].split(","))

    return (
        f'<div class="fixture result{" me" if me else ""}">'
        f'<div class="row top"><div class="grow"><div class="team">{escape(row["team_name"])}</div>'
        f'<div class="meta">{escape(str(row["formation"]))}, note {row["note_moy"]:.2f}</div></div>'
        f'<div class="score">{int(row["bp"])} – {int(away["bp"])}</div>'
        f'<div class="right grow"><div class="team">{escape(away["team_name"])}</div>'
        f'<div class="meta">note {away["note_moy"]:.2f}, {escape(str(away["formation"]))}</div></div></div>'
        f'<div class="scorers"><div class="meta">{scorers(row["team_id"])}</div>'
        f'<div class="meta right">{scorers(away["team_id"])}</div></div>'
        f'<div class="foot bonus"><div>{bonus(row)}</div><div class="right">{bonus(away)}</div></div></div>'
    )


def _rang(r: int) -> str:
    return "1er" if r == 1 else f"{r}e"


def recap_text(a: Analysis, gw: int, frozen: pd.DataFrame | None) -> str:
    """Récap de journée en texte brut, assemblé par gabarit pour être collé dans une discussion."""
    day = a.team_match[a.team_match["gw"] == gw]
    lines = [f"J{gw} en bref"]
    matches = []
    for _, h in day[day["domicile"]].sort_values("team_id").iterrows():
        aw = day[(day["match_id"] == h["match_id"]) & ~day["domicile"]]
        if aw.empty:
            continue
        matches.append((h["match_id"], h["team_name"], aw.iloc[0]["team_name"]))
        lines.append(f"{h['team_name']} {int(h['bp'])}-{int(aw.iloc[0]['bp'])} {aw.iloc[0]['team_name']}")

    if frozen is not None and not frozen.empty:
        played = frozen[(frozen["gw"] == gw) & frozen["joue"] & (frozen["modele"] == ENSEMBLE)]
        if not played.empty:
            m = played.loc[played["p_issue_reelle"].idxmin()]
            issue = (
                "au nul"
                if m["issue"] == 1
                else f"pour la victoire de {m['home_team' if m['issue'] == 0 else 'away_team']}"
            )
            lines.append(
                f"Surprise : {m['home_team']} {int(m['home_goals'])}-{int(m['away_goals'])} {m['away_team']} "
                f"({round(m['p_issue_reelle'] * 100)}\u202f% {issue})"
            )

    best = a.league.best_players
    best = best[best["gw"] == gw].dropna(subset=["note"])
    if not best.empty:
        top = best.loc[best["note"].idxmax()]
        names = next(((h, w) for mid, h, w in matches if mid == top["match_id"]), None)
        where = f"match {names[0]} - {names[1]}" if names else f"J{gw}"
        note = f"{top['note']:.1f}".replace(".", ",")
        lines.append(f"Homme de la journée : {top['joueur']} ({where}), note {note}")

    st_gw = a.standings_by_gw
    now = st_gw[st_gw["gw"] == gw]
    if not now.empty:
        leader = now.loc[now["rang"].idxmin()]
        prev = st_gw[st_gw["gw"] == gw - 1]
        if prev.empty:
            verb = "est en tête"
        else:
            verb = (
                "garde la tête" if prev.loc[prev["rang"].idxmin(), "team_id"] == leader["team_id"] else "prend la tête"
            )
        lines.append(f"{leader['team_name']} {verb} ({int(leader['pts'])} pts)")
        if not prev.empty:
            moves = now.merge(prev[["team_id", "rang"]], on="team_id", suffixes=("", "_avant"))
            moves = moves.assign(gain=moves["rang_avant"] - moves["rang"])
            if not moves.empty and moves["gain"].max() >= 2:
                up = moves.loc[moves["gain"].idxmax()]
                lines.append(f"{up['team_name']} gagne {int(up['gain'])} places ({_rang(int(up['rang']))})")
    return "\n".join(lines)


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    tm = a.team_match
    finished = meta["capacites"].terminee
    volet_title(
        "Résultats, journée par journée",
        "Buteurs, buts MPG et bonus posés, match par match."
        if finished
        else "Buteurs, buts MPG, bonus posés et difficulté du calendrier à venir.",
    )

    gws = sorted(tm["gw"].unique().tolist())
    gw = st.segmented_control(
        "Journée",
        options=gws,
        default=gws[-1],
        required=True,
        format_func=lambda g: f"J{g}",
        key=f"match_gw_{meta['saison']}",
    )
    fm = get_frozen()["frozen_matches"] if meta["saison_en_cours"] else None
    section("La journée en bref", "À copier pour le groupe.")
    st.code(recap_text(a, gw, fm), language=None, wrap_lines=True)
    day = tm[tm["gw"] == gw]
    home = day[day["domicile"]].sort_values("team_id")
    goals = a.league.goals
    cards = []
    for _, h in home.iterrows():
        aw = day[(day["match_id"] == h["match_id"]) & ~day["domicile"]].iloc[0]
        cards.append(_match_card(h, aw, goals[goals["match_id"] == h["match_id"]], team_id))
    fixture_grid(cards, 2)

    if finished:
        empty_state(
            "La saison est finie",
            "Il n'y a plus de match à jouer, donc plus de calendrier à comparer. Les résultats sont dans les "
            "journées ci-dessus.",
        )
        return

    section(
        "Calendrier restant",
        f"Difficulté pour chaque équipe, puis les prochains matchs de {a.league.team_names[team_id]}.",
    )
    rem = a.remaining.merge(a.standings[["team_id", "team_name"]], on="team_id")
    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        fig = charts.ranked_bars(
            rem,
            "force_adv_restante",
            "team_name",
            team_id,
            "Difficulté du calendrier restant",
            fmt="+.2f",
            ascending=True,
            x_title="Indice de force moyen des adversaires restants",
        )
        charts.show(fig, height=470)
        how("indice_force", meta)
    with right:
        fx = a.league.fixtures
        todo = fx[(fx["statut"] != "joue") & ((fx["home_team_id"] == team_id) | (fx["away_team_id"] == team_id))]
        rank = a.standings.set_index("team_id")["rang"]
        force = a.favourites.set_index("team_id")["indice_force"]
        todo = todo.assign(
            adversaire=lambda d: d.apply(
                lambda r: r["away_team"] if r["home_team_id"] == team_id else r["home_team"], axis=1
            ),
            opp_id=lambda d: d.apply(
                lambda r: r["away_team_id"] if r["home_team_id"] == team_id else r["home_team_id"], axis=1
            ),
            lieu=lambda d: (d["home_team_id"] == team_id).map({True: "Domicile", False: "Extérieur"}),
        )
        todo["rang_adv"] = todo["opp_id"].map(rank)
        todo["force_adv"] = todo["opp_id"].map(force)
        todo["journee"] = "J" + todo["gw"].astype(str) + todo["date"].dt.strftime(", %d/%m").fillna("")
        st.dataframe(
            todo[["journee", "lieu", "adversaire", "rang_adv", "force_adv"]],
            hide_index=True,
            height=470,
            alt="Calendrier restant",
            column_config={
                "journee": "Journée",
                "lieu": "Lieu",
                "adversaire": "Adversaire",
                "rang_adv": st.column_config.NumberColumn("Rang actuel"),
                "force_adv": st.column_config.NumberColumn("Force sur le papier", format="%+.2f"),
            },
        )
