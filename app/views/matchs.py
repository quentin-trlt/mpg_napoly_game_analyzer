from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import fixture_grid, hero, how, section
from mpg.analysis import Analysis


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
        return "".join(f'<span class="chip">{escape(b.strip())}</span>' for b in r["bonus_poses"].split(","))

    return (
        f'<div class="fixture result{" me" if me else ""}">'
        f'<div class="row top"><div style="flex:1;min-width:0"><div class="team">{escape(row["team_name"])}</div>'
        f'<div class="meta">{escape(str(row["formation"]))}, note {row["note_moy"]:.2f}</div></div>'
        f'<div class="score">{int(row["bp"])} – {int(away["bp"])}</div>'
        f'<div class="right" style="flex:1;min-width:0"><div class="team">{escape(away["team_name"])}</div>'
        f'<div class="meta">note {away["note_moy"]:.2f}, {escape(str(away["formation"]))}</div></div></div>'
        f'<div class="scorers"><div class="meta">{scorers(row["team_id"])}</div>'
        f'<div class="meta right">{scorers(away["team_id"])}</div></div>'
        f'<div class="foot bonus"><div>{bonus(row)}</div><div class="right">{bonus(away)}</div></div></div>'
    )


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    tm = a.team_match
    hero(
        "Matchs et calendrier",
        "Résultats, journée par journée",
        "Buteurs, buts MPG, bonus posés et difficulté du calendrier à venir.",
    )

    gws = sorted(tm["gw"].unique().tolist())
    gw = st.segmented_control(
        "Journée", options=gws, default=gws[-1], required=True, format_func=lambda g: f"J{g}", key="match_gw"
    )
    day = tm[tm["gw"] == gw]
    home = day[day["domicile"]].sort_values("team_id")
    goals = a.league.goals
    cards = []
    for _, h in home.iterrows():
        aw = day[(day["match_id"] == h["match_id"]) & ~day["domicile"]].iloc[0]
        cards.append(_match_card(h, aw, goals[goals["match_id"] == h["match_id"]], team_id))
    fixture_grid(cards, 2)

    section(
        f"{a.league.team_names[team_id]}, match par match",
        "Couleur de la barre : vert victoire, jaune nul, rouge défaite. Le résultat est aussi écrit sous chaque barre.",
    )
    charts.show(charts.gw_points(tm, team_id))

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
        st.dataframe(
            todo[["gw", "date", "lieu", "adversaire", "rang_adv", "force_adv"]],
            hide_index=True,
            height=470,
            column_config={
                "gw": st.column_config.NumberColumn("J", format="J%d"),
                "date": st.column_config.DateColumn("Date", format="DD/MM"),
                "lieu": "Lieu",
                "adversaire": "Adversaire",
                "rang_adv": st.column_config.NumberColumn("Rang actuel"),
                "force_adv": st.column_config.NumberColumn("Force a priori", format="%+.2f"),
            },
        )
