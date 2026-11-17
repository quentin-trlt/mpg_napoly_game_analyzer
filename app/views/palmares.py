from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import callout, fmt_signed, form_badges, grid, hero, kpi_row, medal, no_data, section
from app.state import get_analysis, seasons, selected_coach
from mpg.analysis import Analysis
from mpg.history import career, head_to_head, honours
from mpg.seasons import Season

MIN_MATCHES = 10
GRID_TEMPLATE = "minmax(0, 1.6fr) repeat({n}, minmax(0, .8fr)) minmax(0, .9fr)"


def _ordinal(rank: int) -> str:
    return "1er" if rank == 1 else f"{rank}e"


def _md(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*")


def _signed(x: int) -> str:
    return "0" if x == 0 else f"{x:+d}".replace("-", "−")


def _champions(season_list: list[Season], car: pd.DataFrame, coach: str) -> str:
    cards = []
    for s in reversed(season_list):
        table = car[car["saison"] == s.key].sort_values("rang")
        first = table.iloc[0]
        me = table[table["coach"] == coach]
        mine = (
            f"Toi : {_ordinal(int(me.iloc[0]['rang']))} avec {me.iloc[0]['equipe']}, {int(me.iloc[0]['pts'])} pts"
            if not me.empty
            else "Tu ne jouais pas cette saison"
        )
        played = int(table["j"].max())
        state = f"en cours, J{played}" if s.current else f"{len(table)} équipes, {played} journées"
        cards.append(
            f'<div class="champ"><div><div class="season">{escape(s.key)}</div><div class="meta">{state}</div></div>'
            f'<div><div class="team">{escape(first["equipe"])}</div>'
            f'<div class="meta">{"leader" if s.current else "champion"}, coach {escape(first["coach"])}, '
            f"{int(first['pts'])} pts</div></div>"
            f'<div class="mine">{escape(mine)}</div></div>'
        )
    return f'<div class="champs">{"".join(cards)}</div>'


def _coach_grid(season_list: list[Season], car: pd.DataFrame, totals: pd.DataFrame, coach: str) -> str:
    cells = ['<div class="h">Coach</div>']
    cells += [f'<div class="h">{escape(s.short)}{"*" if s.current else ""}</div>' for s in season_list]
    cells.append('<div class="h">Pts / match</div>')
    ranks = car.pivot(index="coach", columns="saison", values="rang")
    sizes = car.groupby("saison")["n_equipes"].first()
    last_team = car.groupby("coach")["equipe"].last()
    for row in totals.itertuples():
        me = " me" if row.coach == coach else ""
        cells.append(
            f'<div class="name{me}"><b>{escape(row.coach)}</b><span>{escape(last_team[row.coach])}</span></div>'
        )
        for s in season_list:
            cells.append(f'<div class="c{me}">{medal(ranks.at[row.coach, s.key], int(sizes[s.key]))}</div>')
        ppm = "·" if pd.isna(row.ppm) else f"{row.ppm:.2f}"
        cells.append(f'<div class="c{me}"><b>{ppm}</b></div>')
    return grid(cells, GRID_TEMPLATE.format(n=len(season_list)))


def _footnote(season_list: list[Season], car: pd.DataFrame) -> str:
    sizes = car.groupby("saison")["n_equipes"].first()
    parts = []
    current = car[car["en_cours"]]
    if not current.empty:
        parts.append(f"* saison en cours, classement après la J{int(current['j'].max())}.")
    by_size = ", ".join(f"{int(sizes[s.key])} en {s.key}" for s in season_list)
    parts.append(f"Le petit chiffre est le nombre d'équipes ({by_size}). Un point : le coach ne jouait pas.")
    return f'<div class="tagline">{escape(" ".join(parts))}</div>'


def _record(h2h: pd.DataFrame) -> pd.DataFrame:
    ordered = h2h.sort_values(["saison", "gw"])
    return (
        ordered.groupby("adversaire")
        .agg(
            matchs=("resultat", "size"),
            v=("resultat", lambda s: int((s == "V").sum())),
            n=("resultat", lambda s: int((s == "N").sum())),
            d=("resultat", lambda s: int((s == "D").sum())),
            bp=("bp", "sum"),
            bc=("bc", "sum"),
            serie=("resultat", lambda s: "".join(s.tail(5))),
        )
        .assign(solde=lambda d: d["v"] - d["d"])
        .sort_values(["solde", "matchs"], ascending=[False, False])
    )


def _record_rows(record: pd.DataFrame) -> str:
    rows = "".join(
        f'<div class="r"><div class="pos">{r.matchs}</div><div class="minw0"><div class="who">{escape(str(c))}</div>'
        f'<div class="sub">{r.v}V {r.n}N {r.d}D · buts {int(r.bp)}–{int(r.bc)}</div></div>'
        f'<div class="side">{form_badges(r.serie)}</div>'
        f'<div class="big">{_signed(int(r.solde))}</div></div>'
        for c, r in record.iterrows()
    )
    return f'<div class="ranks">{rows}</div>'


def _head_to_head(season_list: list[Season], h2h: pd.DataFrame, coach: str) -> None:
    section("Face-à-face", f"Bilan de {_md(coach)} contre chaque coach, toutes saisons confondues.")
    if h2h.empty:
        no_data(f"{coach} n'a pas encore joué de match : pas de face-à-face à montrer.")
        return
    record = _record(h2h)
    st.html(_record_rows(record))
    st.html(
        '<div class="tagline">À gauche le nombre de matchs, au centre les derniers résultats '
        "(du plus ancien au plus récent), à droite victoires moins défaites.</div>"
    )
    rival = st.selectbox("Voir les matchs contre", options=record.index.tolist())
    short = {s.key: s.short for s in season_list}
    games = h2h[h2h["adversaire"] == rival].sort_values(["saison", "gw"], ascending=False)
    games = games.assign(
        journee=games["saison"].map(short) + " J" + games["gw"].astype(str),
        lieu=games["domicile"].map({True: "Dom.", False: "Ext."}),
        score=games["bp"].astype(str) + " – " + games["bc"].astype(str),
    )
    st.dataframe(
        games[["journee", "lieu", "opp_name", "score", "resultat"]],
        hide_index=True,
        alt="Matchs contre ce coach",
        column_config={
            "journee": st.column_config.TextColumn("Journée", width="small"),
            "lieu": st.column_config.TextColumn("Lieu", width="small"),
            "opp_name": st.column_config.TextColumn("Son équipe", width="medium"),
            "score": st.column_config.TextColumn("Score", width="small"),
            "resultat": st.column_config.TextColumn("Résultat", width="small"),
        },
    )


def _merit_charts(totals: pd.DataFrame, coach: str) -> None:
    section(
        "Mérite et réussite",
        f"Coachs avec au moins {MIN_MATCHES} matchs. Les points mérités sont ceux que les notes de l'équipe auraient "
        "rapportés en moyenne contre toutes les équipes de la journée.",
    )
    solid = totals[totals["matchs"] >= MIN_MATCHES].reset_index(drop=True)
    if solid.empty:
        no_data(f"Aucun coach n'a encore {MIN_MATCHES} matchs : pas de comparaison possible.")
        return
    solid["team_id"] = solid.index
    solid["chance_par_match"] = solid["chance"] / solid["matchs"]
    mine = solid.index[solid["coach"] == coach]
    focus = int(mine[0]) if len(mine) else -1
    if focus < 0:
        played = int(totals.set_index("coach").at[coach, "matchs"])
        st.caption(
            f"{_md(coach)} n'a joué que {played} matchs (moins de {MIN_MATCHES}) : "
            "il n'apparaît pas dans ces graphiques."
        )
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.ranked_bars(
                solid, "xppm", "coach", focus, "Points mérités par match", fmt=".2f", x_title="Points par match"
            ),
            height=420,
        )
    with right:
        charts.show(
            charts.diverging_bars(
                solid, "chance_par_match", "coach", focus, "Points gagnés ou perdus à la chance, par match", x_title="Points par match"
            ),
            height=420,
        )
    with st.expander("Comment c'est calculé"):
        st.markdown(
            "Les points mérités comparent la note moyenne de l'équipe à celle de toutes les autres équipes de la "
            "même journée. La chance est l'écart entre les points réellement pris et ces points mérités, rapporté au "
            "nombre de matchs joués pour rendre les coachs comparables quelle que soit la longueur de leur saison."
        )


def _figures(totals: pd.DataFrame, coach: str) -> None:
    me = totals.set_index("coach").loc[coach]
    played = int(me["matchs"])
    best = int(me["meilleur_rang"])
    champions = totals[totals["titres"] > 0].sort_values("titres", ascending=False)
    if played:
        rank = int(totals["ppm"].rank(ascending=False, method="min").loc[totals["coach"] == coach].iloc[0])
        value, sub = f"{me['ppm']:.2f}", f"point par match, {_ordinal(rank)} sur {len(totals)} coachs ({played} matchs)"
    else:
        value, sub = "·", "pas encore de match joué"
    kpi_row(
        [
            {"label": f"{coach}, toutes saisons", "value": value, "sub": sub, "me": True},
            {
                "label": "Ton meilleur classement",
                "value": _ordinal(best),
                "sub": f"{me['meilleure_saison']}, {me['meilleure_equipe']}",
                "me": True,
            },
            {
                "label": "Titres",
                "value": str(int(me["titres"])),
                "sub": "Champions : " + ", ".join(f"{r.coach} ({r.titres})" for r in champions.itertuples())
                if not champions.empty
                else "Aucun titre pour l'instant",
            },
            {
                "label": "Points gagnés à la chance",
                "value": fmt_signed(float(me["chance"]), 0),
                "sub": "points pris en plus ou en moins de ce que valaient tes notes, cumulés",
            },
        ]
    )


def render(a: Analysis, team_id: int) -> None:
    season_list = seasons()
    loaded = [(s, get_analysis(s.path)) for s in season_list]
    coach = selected_coach()
    car = career(loaded)
    totals = honours(loaded)

    hero(
        f"Palmarès · {len(season_list)} saisons, {len(totals)} coachs",
        "Qui domine la ligue depuis le début ?",
        f"{int(car['j'].sum() / 2)} matchs joués depuis {season_list[0].key}. "
        "Les coachs sont suivis par leur pseudo MPG, les noms d'équipe changent chaque saison.",
    )
    _figures(totals, coach)

    section("Les champions")
    st.html(_champions(season_list, car, coach))

    section(
        "Les coachs, saison par saison",
        "Classement de chaque saison (provisoire pour la saison en cours), coachs triés par points par match.",
    )
    st.html(_coach_grid(season_list, car, totals, coach))
    st.html(_footnote(season_list, car))

    _merit_charts(totals, coach)
    _head_to_head(season_list, head_to_head(loaded, coach), coach)

    past = set(car.loc[~car["en_cours"], "coach"])
    newcomers = sorted(set(car.loc[car["en_cours"], "coach"]) - past, key=str.lower)
    if newcomers:
        callout(f"Nouveaux cette saison, sans historique dans la ligue : {escape(', '.join(newcomers))}.")
