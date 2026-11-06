from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import hero, how, section
from mpg.analysis import Analysis


def _match_card(row: pd.Series, away: pd.Series, goals: pd.DataFrame, team_id: int) -> str:
    me = team_id in (row["team_id"], away["team_id"])

    def scorers(tid: int) -> str:
        g = goals[goals["team_id"] == tid]
        if g.empty:
            return '<span class="muted">—</span>'
        labels = {"reel": "", "mpg": " (MPG)", "csc": " (CSC)", "rotaldo_csc": " (CSC Rotaldo)"}
        return "<br>".join(escape(f"{r.buteur_affiche}{labels.get(r.type_but, '')}") for r in g.itertuples())

    def bonus(r: pd.Series) -> str:
        if not r["bonus_poses"]:
            return ""
        return "".join(f'<span class="chip">{escape(b.strip())}</span>' for b in r["bonus_poses"].split(","))

    return f"""
    <div class="fixture{" me" if me else ""}">
      <div class="row">
        <div style="flex:1"><div class="team">{escape(row["team_name"])}</div>
          <div class="meta">{escape(str(row["formation"]))} · note {row["note_moy"]:.2f}</div></div>
        <div class="score">{int(row["bp"])} – {int(away["bp"])}</div>
        <div style="flex:1;text-align:right"><div class="team">{escape(away["team_name"])}</div>
          <div class="meta">note {away["note_moy"]:.2f} · {escape(str(away["formation"]))}</div></div>
      </div>
      <div class="row" style="margin-top:8px;align-items:flex-start">
        <div class="meta" style="flex:1">{scorers(row["team_id"])}</div>
        <div class="meta" style="flex:1;text-align:right">{scorers(away["team_id"])}</div>
      </div>
      <div class="row" style="margin-top:8px">
        <div>{bonus(row)}</div><div style="text-align:right">{bonus(away)}</div>
      </div>
    </div>"""


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
    cols = st.columns(2, gap="medium")
    for i, (_, h) in enumerate(home.iterrows()):
        aw = day[(day["match_id"] == h["match_id"]) & ~day["domicile"]].iloc[0]
        with cols[i % 2]:
            st.html(_match_card(h, aw, goals[goals["match_id"] == h["match_id"]], team_id))

    section("Mon équipe match par match")
    charts.show(charts.gw_points(tm, team_id))
    st.caption("Couleur de la barre : vert victoire, jaune nul, rouge défaite (le résultat est aussi écrit au-dessus).")

    section("Calendrier restant")
    rem = a.remaining.merge(a.standings[["team_id", "team_name"]], on="team_id")
    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        charts.show(
            charts.ranked_bars(
                rem,
                "force_adv_restante",
                "team_name",
                team_id,
                "Difficulté du calendrier restant",
                fmt="+.2f",
                ascending=True,
                x_title="Indice de force moyen des adversaires restants",
            )
        )
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
        st.markdown(f"**Prochains matchs de {a.league.team_names[team_id]}**")
        st.dataframe(
            todo[["gw", "date", "lieu", "adversaire", "rang_adv", "force_adv"]],
            hide_index=True,
            height=420,
            column_config={
                "gw": st.column_config.NumberColumn("J", format="J%d"),
                "date": st.column_config.DateColumn("Date", format="DD/MM"),
                "lieu": "Lieu",
                "adversaire": "Adversaire",
                "rang_adv": st.column_config.NumberColumn("Rang actuel"),
                "force_adv": st.column_config.NumberColumn("Force a priori", format="%+.2f"),
            },
        )
