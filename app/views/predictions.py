from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from app import charts
from app.components import (
    PCT_FORMAT,
    as_pct,
    callout,
    fixture_grid,
    fmt_pct,
    how,
    kpi_row,
    pct_column,
    prob_bar,
    section,
    short_table,
    table_height,
    volet_title,
)
from app.state import data_signature, get_forecast_light, get_frozen, get_title_history
from app.views.forecast_common import FILM_INTRO, count_word, film, forecast_meta, model_keys, score
from app.views.suivi import last_gameweek
from mpg.analysis import Analysis
from mpg.forecast.season import simulate_season

OPTIONS = ["—", "H", "D", "A"]
STORE = "et_si"
SEASON_OVER = "La saison est terminée : il n'y a plus de match à prédire."


def _next_gw(fc: dict, team_id: int) -> None:
    mp = fc["baseline"].match_probs
    gw = int(mp["gw"].min())
    nxt = mp[mp["gw"] == gw]
    n_models = len(model_keys(fc["draws"]))
    section(
        f"Journée {gw} : les pronostics",
        f"Probabilités de la moyenne des {count_word(n_models)} modèles : victoire à domicile, nul, victoire à l'extérieur.",
    )
    cards = [
        f'<div class="fixture{" me" if team_id in (m["home_team_id"], m["away_team_id"]) else ""}">'
        f'<div class="pair"><div class="team">{escape(m["home_team"])}</div><div class="vs">contre</div>'
        f'<div class="team">{escape(m["away_team"])}</div></div>'
        f'<div class="foot">{prob_bar(m["p_dom"], m["p_nul"], m["p_ext"])}'
        f'<div class="meta mt-8">Score le plus probable : <b>{score(m["score_probable"])}</b></div></div></div>'
        for _, m in nxt.iterrows()
    ]
    fixture_grid(cards, len(cards))
    with st.expander("Ce que dit chaque modèle"):
        by_model = fc["draws"].mean_probs()
        by_model = by_model[by_model["gw"] == gw]
        by_model["match"] = by_model["home_team"] + " – " + by_model["away_team"]
        st.dataframe(
            as_pct(by_model[["match", "modele", "p_dom", "p_nul", "p_ext"]], ["p_dom", "p_nul", "p_ext"]),
            hide_index=True,
            alt="Probabilités de chaque modèle",
            column_config={
                "match": "Match",
                "modele": "Modèle",
                "p_dom": pct_column("Victoire dom.", bar=True),
                "p_nul": pct_column("Nul", bar=True),
                "p_ext": pct_column("Victoire ext.", bar=True),
            },
        )
        st.caption(
            "Les modèles divergent surtout quand des joueurs clés sont blessés ou incertains : seul le modèle "
            "structurel en tient compte."
        )


def _season_table(sim, names: dict[int, str], team_id: int) -> None:
    s = sim.summary.copy()
    s["team_name"] = s["team_id"].map(names)
    s["intervalle"] = s["pts_p05"].map("{:.0f}".format) + " – " + s["pts_p95"].map("{:.0f}".format)
    short_table(
        as_pct(s, ["p_titre", "p_podium", "p_dernier"]),
        ["team_name", "pts_moy", "p_titre", "p_podium", "p_dernier"],
        full=["team_name", "pts_moy", "p_titre", "p_podium", "p_dernier", "intervalle", "rang_moy", "pts_actuels"],
        alt="Prévisions de fin de saison",
        column_config={
            "team_name": "Équipe",
            "pts_actuels": "Points actuels",
            "pts_moy": st.column_config.NumberColumn(
                "Pts prévus", format="%.1f", help="Points prévus en fin de saison, en moyenne"
            ),
            "intervalle": st.column_config.TextColumn(
                "Fourchette de points", help="Dans 9 cas sur 10, l'équipe finit entre ces deux totaux"
            ),
            "rang_moy": st.column_config.NumberColumn("Rang moyen", format="%.1f"),
            "p_titre": pct_column("Titre", bar=True),
            "p_podium": pct_column("Podium", bar=True),
            "p_dernier": pct_column("Dernier", bar=True),
        },
        height=table_height(len(s)),
    )


@st.cache_data(show_spinner="Calcul des enjeux…")
def _stakes(_a: Analysis, _draws, signature: tuple, team_id: int) -> pd.DataFrame:
    fx = _draws.fixtures
    gw = int(fx["gw"].min())
    rows = []
    for j in fx.index[fx["gw"] == gw]:
        row = {"match": f"{fx.at[j, 'home_team']} – {fx.at[j, 'away_team']}"}
        for k, lab in zip("HDA", ("1", "N", "2")):
            s = simulate_season(_a, _draws, forced={int(j): k}).summary.set_index("team_id").loc[team_id]
            row.update({f"titre_{lab}": s["p_titre"], f"podium_{lab}": s["p_podium"], f"dernier_{lab}": s["p_dernier"]})
        rows.append(row)
    return pd.DataFrame(rows)


def _what_if(a: Analysis, fc: dict, team_id: int) -> None:
    draws = fc["draws"]
    fx = draws.fixtures
    names = a.league.team_names
    store = st.session_state.setdefault(STORE, {})
    gws = sorted(fx["gw"].unique().tolist())
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    with c1:
        gw = st.selectbox("Journée à modifier", options=gws, format_func=lambda g: f"Journée {g}", key="etsi_gw")
    with c2:
        if st.button("Tout réinitialiser", icon=":material/restart_alt:", disabled=not store, width="stretch"):
            store.clear()
            for k in [k for k in st.session_state if str(k).startswith("etsi_m_")]:
                del st.session_state[k]
            st.rerun()

    labels = {"—": "Simulé", "H": "1", "D": "N", "A": "2"}
    for j in fx.index[fx["gw"] == gw]:
        home, away = fx.at[j, "home_team"], fx.at[j, "away_team"]
        c_match, c_ctrl = st.columns([2.2, 1.8])
        with c_match:
            st.html(
                f'<div class="pt-6"><b>{escape(home)}</b> <span class="muted">contre</span> <b>{escape(away)}</b></div>'
            )
        with c_ctrl:
            choice = st.segmented_control(
                f"Issue {home} – {away}",
                options=OPTIONS,
                default=store.get(int(j), "—"),
                required=True,
                format_func=labels.get,
                key=f"etsi_m_{int(j)}",
                label_visibility="collapsed",
                help="1 = victoire à domicile, N = nul, 2 = victoire à l'extérieur",
            )
        if choice == "—":
            store.pop(int(j), None)
        else:
            store[int(j)] = choice

    if not store:
        st.caption("Fixe au moins un résultat pour voir son effet sur la fin de saison.")
        return

    forced_desc = ", ".join(
        f"{fx.at[j, 'home_team']} – {fx.at[j, 'away_team']} : {labels[v]} (J{fx.at[j, 'gw']})"
        for j, v in sorted(store.items())
    )
    callout(f"{len(store)} résultat(s) imposé(s) : {escape(forced_desc)}")
    base = fc["baseline"].summary.set_index("team_id")
    new = simulate_season(a, draws, forced=dict(store)).summary.set_index("team_id")
    comp = pd.DataFrame(
        {
            "team_id": base.index,
            "team_name": base.index.map(names),
            "titre_avant": base["p_titre"],
            "titre_apres": new["p_titre"].reindex(base.index),
            "podium_avant": base["p_podium"],
            "podium_apres": new["p_podium"].reindex(base.index),
            "dernier_avant": base["p_dernier"],
            "dernier_apres": new["p_dernier"].reindex(base.index),
            "pts_apres": new["pts_moy"].reindex(base.index),
        }
    ).reset_index(drop=True)
    comp["delta_titre"] = (comp["titre_apres"] - comp["titre_avant"]) * 100
    comp["delta_podium"] = (comp["podium_apres"] - comp["podium_avant"]) * 100

    me = comp.set_index("team_id").loc[team_id]
    kpi_row(
        [
            {
                "label": f"Chances de titre, {me['team_name']}",
                "value": fmt_pct(me["titre_apres"]),
                "sub": f"avant : {fmt_pct(me['titre_avant'])} ({me['delta_titre']:+.0f} points de pourcentage)",
            },
            {
                "label": "Chances de podium",
                "value": fmt_pct(me["podium_apres"]),
                "sub": f"avant : {fmt_pct(me['podium_avant'])} ({me['delta_podium']:+.0f} points de pourcentage)",
            },
            {
                "label": "Chances de finir dernier",
                "value": fmt_pct(me["dernier_apres"]),
                "sub": f"avant : {fmt_pct(me['dernier_avant'])}",
            },
        ]
    )
    left, right = st.columns([1, 1.3], gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                comp,
                "delta_titre",
                "team_name",
                team_id,
                "Variation de la probabilité de titre",
                x_title="Points de pourcentage",
                fmt="+.1f",
            )
        )
    with right:
        pct_cols = ["titre_avant", "titre_apres", "podium_avant", "podium_apres", "dernier_apres"]
        short_table(
            as_pct(comp.sort_values("titre_apres", ascending=False), pct_cols),
            ["team_name", "titre_avant", "titre_apres", "podium_apres", "pts_apres"],
            full=[
                "team_name",
                "titre_avant",
                "titre_apres",
                "podium_avant",
                "podium_apres",
                "dernier_apres",
                "pts_apres",
            ],
            alt="Fin de saison avant et après tes résultats imposés",
            column_config={
                "team_name": "Équipe",
                "titre_avant": pct_column("Titre avant", width="small"),
                "titre_apres": pct_column("Titre après", bar=True),
                "podium_avant": pct_column("Podium avant", width="small"),
                "podium_apres": pct_column("Podium après", bar=True),
                "dernier_apres": pct_column("Dernier après"),
                "pts_apres": st.column_config.NumberColumn(
                    "Pts prévus", format="%.1f", help="Points prévus en fin de saison, en moyenne"
                ),
            },
            height=table_height(len(comp)),
        )


def _stakes_table(a: Analysis, fc: dict, team_id: int) -> None:
    names = a.league.team_names
    me = fc["baseline"].summary.set_index("team_id").loc[team_id]
    section(
        f"Les matchs qui comptent pour {names[team_id]}",
        "Probabilités de ton équipe selon l'issue de chaque match de la prochaine journée "
        "(1 = victoire à domicile, N = nul, 2 = victoire à l'extérieur).",
    )
    stakes = _stakes(a, fc["draws"], data_signature(), team_id)
    focus = "titre" if me["p_titre"] >= 0.05 else "podium" if me["p_podium"] >= 0.05 else "dernier"
    focus_label = {"titre": "titre", "podium": "podium", "dernier": "finir dernier"}[focus]
    outcomes = [f"{focus}_1", f"{focus}_N", f"{focus}_2"]
    stakes["enjeu"] = stakes[outcomes].max(axis=1) - stakes[outcomes].min(axis=1)
    stake_columns = [*outcomes, "enjeu"]
    st.dataframe(
        as_pct(stakes.sort_values("enjeu", ascending=False)[["match", *stake_columns]], stake_columns),
        hide_index=True,
        alt="Enjeux de la prochaine journée",
        column_config={
            "match": "Match",
            f"{focus}_1": pct_column(f"Chances de {focus_label} si 1"),
            f"{focus}_N": pct_column(f"Chances de {focus_label} si N"),
            f"{focus}_2": pct_column(f"Chances de {focus_label} si 2"),
            "enjeu": st.column_config.ProgressColumn(
                "Enjeu",
                min_value=0,
                max_value=100 * float(max(stakes["enjeu"].max(), 0.01)),
                format=PCT_FORMAT,
                help="Écart entre la meilleure et la pire issue",
            ),
        },
    )


def _key_figures(a: Analysis, sim, team_id: int) -> None:
    names = a.league.team_names
    summary = sim.summary
    me = summary.set_index("team_id").loc[team_id]
    fav = summary.iloc[0]
    danger = summary.sort_values("p_dernier").iloc[-1]
    kpi_row(
        [
            {
                "label": "Favori pour le titre",
                "value": names[int(fav["team_id"])],
                "small": True,
                "sub": f"{fmt_pct(fav['p_titre'])} de chances, {fav['pts_moy']:.0f} points prévus",
            },
            {
                "label": f"Chances de titre, {names[team_id]}",
                "value": fmt_pct(me["p_titre"]),
                "sub": f"podium {fmt_pct(me['p_podium'])}, rang moyen {me['rang_moy']:.1f}",
                "me": True,
            },
            {
                "label": "Points en fin de saison",
                "value": f"{me['pts_moy']:.0f}",
                "sub": f"entre {me['pts_p05']:.0f} et {me['pts_p95']:.0f} dans 9 cas sur 10",
                "me": True,
            },
            {
                "label": "Le plus menacé",
                "value": names[int(danger["team_id"])],
                "small": True,
                "sub": f"{fmt_pct(danger['p_dernier'])} de finir dernier",
            },
        ]
    )


def render_journee(a: Analysis, team_id: int) -> None:
    volet_title(
        "Qui est favori cette journée ?",
        "Les pronostics de la prochaine journée, ce qu'ils changent pour ton équipe, et ce qu'on avait prédit pour "
        "la dernière journée jouée.",
    )
    fc = get_forecast_light()
    if fc["baseline"] is None:
        callout(SEASON_OVER)
        return
    _next_gw(fc, team_id)
    _stakes_table(a, fc, team_id)
    fm = get_frozen()["frozen_matches"]
    if fm.empty:
        callout(
            "Aucun pronostic figé pour l'instant : on ne peut pas encore dire si on avait vu juste. Les pronostics "
            "sont enregistrés avant chaque journée, puis notés une fois les matchs joués.",
            warn=True,
        )
        return
    last_gameweek(fm, team_id)


def render_fin_de_saison(a: Analysis, team_id: int) -> None:
    volet_title(
        "Où finira chaque équipe ?",
        "La fin de saison est jouée des milliers de fois au hasard, selon les chances de chaque match restant.",
    )
    fc = get_forecast_light()
    if fc["baseline"] is None:
        callout(SEASON_OVER)
        return
    sim, draws = fc["baseline"], fc["draws"]
    meta = forecast_meta(a, draws)
    _key_figures(a, sim, team_id)

    section(
        "Fin de saison simulée",
        f"{len(draws.fixtures)} matchs restants sur {draws.fixtures['gw'].nunique()} journées, "
        f"{meta['n_saisons']:,} saisons simulées".replace(",", " ")
        + f" avec la moyenne de {count_word(len(model_keys(draws)))} modèles.",
    )
    _season_table(sim, a.league.team_names, team_id)
    how(["simulation_saison", "ensemble"], meta)
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(charts.rank_heatmap(sim.rank_probs, a.league.team_names, sim.summary["team_id"].tolist()))
    with right:
        charts.show(charts.final_points_box(sim, a.league.team_names, team_id), height=460)

    section("Le film de la saison", FILM_INTRO)
    film(get_title_history(), a.league.team_names, team_id)


def render_et_si(a: Analysis, team_id: int) -> None:
    volet_title("Et si… ?", "Impose des résultats pour les matchs à venir et regarde la fin de saison bouger.")
    fc = get_forecast_light()
    if fc["baseline"] is None:
        callout(SEASON_OVER)
        return
    with st.container(border=True):
        _what_if(a, fc, team_id)
    how("et_si", a.meta)


def render_film(a: Analysis, team_id: int, season_path: Path) -> None:
    volet_title("Le film de la saison", FILM_INTRO)
    st.caption(
        f"Pas de pronostic figé pour la saison {a.meta['saison']} : les pronostics ne sont enregistrés qu'avant les "
        "journées de la saison en cours."
    )
    film(get_title_history(season_path), a.league.team_names, team_id)
