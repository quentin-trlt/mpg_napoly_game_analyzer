from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import callout, fixture_grid, fmt_pct, hero, how, kpi_row, prob_bar, section, table_height
from app.state import data_signature, get_forecast
from mpg.analysis import Analysis
from mpg.forecast.evaluation import frozen_frames
from mpg.forecast.season import simulate_season
from mpg.glossary import explain

OPTIONS = ["—", "H", "D", "A"]
STORE = "et_si"


def _next_gw(a: Analysis, fc: dict, team_id: int) -> None:
    mp = fc["baseline"].match_probs
    gw = int(mp["gw"].min())
    nxt = mp[mp["gw"] == gw]
    section(f"Journée {gw} : les pronostics", "Probabilités de l'ensemble des trois modèles.")
    cards = [
        f'<div class="fixture{" me" if team_id in (m["home_team_id"], m["away_team_id"]) else ""}">'
        f'<div class="team">{escape(m["home_team"])}</div><div class="vs">contre</div>'
        f'<div class="team">{escape(m["away_team"])}</div>'
        f'<div class="foot">{prob_bar(m["p_dom"], m["p_nul"], m["p_ext"])}'
        f'<div class="meta" style="margin-top:8px">Score le plus probable : <b>{m["score_probable"]}</b></div></div></div>'
        for _, m in nxt.iterrows()
    ]
    fixture_grid(cards, min(len(cards), 5))
    with st.expander("Ce que dit chaque modèle"):
        by_model = fc["draws"].mean_probs()
        by_model = by_model[by_model["gw"] == gw]
        by_model["match"] = by_model["home_team"] + " – " + by_model["away_team"]
        st.dataframe(
            by_model[["match", "modele", "p_dom", "p_nul", "p_ext"]],
            hide_index=True,
            column_config={
                "match": "Match",
                "modele": "Modèle",
                "p_dom": st.column_config.ProgressColumn("Victoire dom.", min_value=0, max_value=1, format="percent"),
                "p_nul": st.column_config.ProgressColumn("Nul", min_value=0, max_value=1, format="percent"),
                "p_ext": st.column_config.ProgressColumn("Victoire ext.", min_value=0, max_value=1, format="percent"),
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
    st.dataframe(
        s[["team_name", "pts_actuels", "pts_moy", "intervalle", "rang_moy", "p_titre", "p_podium", "p_dernier"]],
        hide_index=True,
        column_config={
            "team_name": "Équipe",
            "pts_actuels": "Pts actuels",
            "pts_moy": st.column_config.NumberColumn("Pts attendus", format="%.1f"),
            "intervalle": st.column_config.TextColumn("Intervalle 90 %"),
            "rang_moy": st.column_config.NumberColumn("Rang moyen", format="%.1f"),
            "p_titre": st.column_config.ProgressColumn("Titre", min_value=0, max_value=1, format="percent"),
            "p_podium": st.column_config.ProgressColumn("Podium", min_value=0, max_value=1, format="percent"),
            "p_dernier": st.column_config.ProgressColumn("Dernier", min_value=0, max_value=1, format="percent"),
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
    c1, c2 = st.columns([3, 1])
    with c1:
        gw = st.selectbox("Journée à modifier", options=gws, format_func=lambda g: f"Journée {g}", key="etsi_gw")
    with c2:
        st.html('<div style="height:28px"></div>')
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
                f'<div style="padding-top:6px"><b>{escape(home)}</b> <span class="muted">contre</span> '
                f"<b>{escape(away)}</b></div>"
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
        st.caption("Fixez au moins un résultat pour voir son effet sur la fin de saison.")
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
                "label": f"Titre, {me['team_name']}",
                "value": fmt_pct(me["titre_apres"]),
                "sub": f"avant : {fmt_pct(me['titre_avant'])} ({me['delta_titre']:+.0f} pts de %)",
            },
            {
                "label": "Podium",
                "value": fmt_pct(me["podium_apres"]),
                "sub": f"avant : {fmt_pct(me['podium_avant'])} ({me['delta_podium']:+.0f} pts de %)",
            },
            {
                "label": "Dernière place",
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
        st.dataframe(
            comp.sort_values("titre_apres", ascending=False)[
                [
                    "team_name",
                    "titre_avant",
                    "titre_apres",
                    "podium_avant",
                    "podium_apres",
                    "dernier_apres",
                    "pts_apres",
                ]
            ],
            hide_index=True,
            column_config={
                "team_name": "Équipe",
                "titre_avant": st.column_config.NumberColumn("Titre avant", format="percent", width="small"),
                "titre_apres": st.column_config.ProgressColumn(
                    "Titre après", min_value=0, max_value=1, format="percent"
                ),
                "podium_avant": st.column_config.NumberColumn("Podium avant", format="percent", width="small"),
                "podium_apres": st.column_config.ProgressColumn(
                    "Podium après", min_value=0, max_value=1, format="percent"
                ),
                "dernier_apres": st.column_config.NumberColumn("Dernier après", format="percent"),
                "pts_apres": st.column_config.NumberColumn("Pts attendus", format="%.1f"),
            },
            height=table_height(len(comp)),
        )


def _model_quality(a: Analysis, fc: dict, meta: dict) -> None:
    summ = fc["backtest_summary"]
    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        st.markdown("**Rejeu du passé** (chaque journée prédite avec les seules journées précédentes)")
        st.dataframe(
            summ,
            hide_index=True,
            column_config={
                "modele": "Modèle",
                "matchs": st.column_config.NumberColumn("Matchs", width="small"),
                "rps": st.column_config.NumberColumn("RPS ↓", format="%.3f", width="small"),
                "log_loss": st.column_config.NumberColumn("Log-loss ↓", format="%.3f", width="small"),
                "brier": st.column_config.NumberColumn("Brier ↓", format="%.3f", width="small"),
                "proba_issue_reelle": st.column_config.ProgressColumn(
                    "Vrai résultat",
                    min_value=0,
                    max_value=1,
                    format="percent",
                    help="Probabilité moyenne donnée au résultat qui s'est produit",
                ),
            },
        )
        how(["scores_prevision", "fuite_backtest"], meta)
    with right:
        st.markdown("**Pronostics figés**")
        fm = fc["frozen_matches"]
        if fm.empty:
            st.info("Aucun pronostic figé pour l'instant.")
        else:
            figees = sorted(fm["gw"].unique())
            notees = sorted(fm.loc[fm["joue"], "gw"].unique())
            st.caption(
                f"Journées figées : {', '.join(f'J{g}' for g in figees)}. "
                + (f"Déjà notées : {', '.join(f'J{g}' for g in notees)}." if notees else "Aucune n'est encore jouée.")
                + " Le détail est sur la page Suivi des pronostics."
            )
        matches, season = frozen_frames(a, fc["baseline"], fc["draws"])
        gw = int(matches["gw"].min())
        c1, c2 = st.columns(2)
        with c1:
            st.download_button(
                f"Pronostics J{gw}",
                matches.to_csv(index=False).encode("utf-8"),
                file_name=f"J{gw:02d}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )
        with c2:
            st.download_button(
                f"Instantané saison J{gw}",
                season.to_csv(index=False).encode("utf-8"),
                file_name=f"saison_J{gw:02d}.csv",
                mime="text/csv",
                icon=":material/download:",
                width="stretch",
            )
        how("pronostics_figes", meta)


def _bonus_effect(fc: dict, team_id: int, meta: dict) -> None:
    be = fc.get("bonus_effect")
    section("Ce que valent les bonus restants")
    if be is None:
        st.caption(
            "Dotation de bonus inconnue (fichier `data/bonus_stock.csv` absent) : les prévisions ignorent les "
            "bonus à venir."
        )
        return
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                be,
                "effet_pts",
                "team_name",
                team_id,
                "Effet net des bonus restants sur les points attendus",
                x_title="Points attendus en fin de saison",
                fmt="+.2f",
            )
        )
    with right:
        st.dataframe(
            be[["team_name", "restants", "effet_pts", "effet_titre", "effet_dernier"]],
            hide_index=True,
            column_config={
                "team_name": "Équipe",
                "restants": st.column_config.NumberColumn("Restants", width="small"),
                "effet_pts": st.column_config.NumberColumn("Pts", format="%+.2f", width="small"),
                "effet_titre": st.column_config.NumberColumn("P(titre)", format="percent", width="small"),
                "effet_dernier": st.column_config.NumberColumn("P(dernier)", format="percent", width="small"),
            },
            height=table_height(len(be)),
        )
        st.caption(
            "Les probabilités des matchs et de fin de saison de cette page incluent déjà l'usage attendu des "
            "bonus restants."
        )
    how("bonus_prevision", meta)


def render(a: Analysis, team_id: int) -> None:
    fc = get_forecast()
    names = a.league.team_names
    hero(
        "Prédictions",
        "Qui va gagner la ligue ?",
        "Trois modèles combinés, la fin de saison simulée des milliers de fois, et un mode « et si » pour tester "
        "les scénarios.",
    )
    if fc["baseline"] is None:
        callout("La saison est terminée : il n'y a plus de match à prédire.")
        return

    sim = fc["baseline"]
    draws = fc["draws"]
    models = {m.name: m for m in draws.models}
    poisson = next(m for m in draws.models if hasattr(m, "tau"))
    struct = next(m for m in draws.models if hasattr(m, "rotaldo_note"))
    meta = {
        **a.meta,
        "n_saisons": draws.ensemble.shape[0],
        "matchs_backtest": int(fc["backtest_summary"]["matchs"].max()),
        "tau": poisson.tau,
        "rotaldo": struct.rotaldo_note,
        "sigma": struct.sigma_match,
        "note_slope": struct.link.b,
    }

    s = sim.summary.set_index("team_id")
    fav = sim.summary.iloc[0]
    danger = sim.summary.sort_values("p_dernier").iloc[-1]
    me = s.loc[team_id]
    remaining = len(draws.fixtures)
    kpi_row(
        [
            {
                "label": "Favori pour le titre",
                "value": names[int(fav["team_id"])],
                "small": True,
                "sub": f"{fmt_pct(fav['p_titre'])} de chances, {fav['pts_moy']:.0f} pts attendus",
            },
            {
                "label": f"Titre, {names[team_id]}",
                "value": fmt_pct(me["p_titre"]),
                "sub": f"podium {fmt_pct(me['p_podium'])}, rang moyen {me['rang_moy']:.1f}",
                "me": True,
            },
            {
                "label": "Points attendus",
                "value": f"{me['pts_moy']:.0f}",
                "sub": f"entre {me['pts_p05']:.0f} et {me['pts_p95']:.0f} (90 %)",
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

    _next_gw(a, fc, team_id)

    section(
        "Fin de saison simulée",
        f"{remaining} matchs restants sur {remaining // 5} journées, {meta['n_saisons']} saisons simulées par "
        f"{len(models)} modèles.",
    )
    _season_table(sim, names, team_id)
    how(["simulation_saison", "ensemble"], meta)
    _bonus_effect(fc, team_id, meta)
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(charts.rank_heatmap(sim.rank_probs, names, sim.summary["team_id"].tolist()))
    with right:
        charts.show(charts.final_points_box(sim, names, team_id), height=460)
    metric = st.segmented_control(
        "Courbe",
        options=["p_titre", "p_podium", "p_dernier"],
        default="p_titre",
        required=True,
        key="hist_metric",
        format_func={"p_titre": "Titre", "p_podium": "Podium", "p_dernier": "Dernier"}.get,
    )
    label = {
        "p_titre": "Probabilité de titre",
        "p_podium": "Probabilité de podium",
        "p_dernier": "Probabilité de finir dernier",
    }[metric]
    charts.show(charts.title_history(fc["history"], names, team_id, metric, label))
    st.caption("Recalculé après chaque journée avec les seuls résultats connus à ce moment.")

    section(
        f"Les matchs de la prochaine journée qui comptent pour {names[team_id]}",
        "Probabilités de ton équipe selon l'issue de chaque match (1 = victoire à domicile, N = nul, 2 = victoire "
        "à l'extérieur).",
    )
    stakes = _stakes(a, draws, data_signature(), team_id)
    focus = "titre" if me["p_titre"] >= 0.05 else "podium" if me["p_podium"] >= 0.05 else "dernier"
    focus_label = {"titre": "titre", "podium": "podium", "dernier": "dernière place"}[focus]
    stakes["enjeu"] = stakes[[f"{focus}_1", f"{focus}_N", f"{focus}_2"]].max(axis=1) - stakes[
        [f"{focus}_1", f"{focus}_N", f"{focus}_2"]
    ].min(axis=1)
    st.dataframe(
        stakes.sort_values("enjeu", ascending=False)[["match", f"{focus}_1", f"{focus}_N", f"{focus}_2", "enjeu"]],
        hide_index=True,
        column_config={
            "match": "Match",
            f"{focus}_1": st.column_config.NumberColumn(f"P({focus_label}) si 1", format="percent"),
            f"{focus}_N": st.column_config.NumberColumn(f"P({focus_label}) si N", format="percent"),
            f"{focus}_2": st.column_config.NumberColumn(f"P({focus_label}) si 2", format="percent"),
            "enjeu": st.column_config.ProgressColumn(
                "Enjeu",
                min_value=0,
                max_value=float(max(stakes["enjeu"].max(), 0.01)),
                format="percent",
                help="Écart entre la meilleure et la pire issue",
            ),
        },
    )

    section("Et si…", "Imposez des résultats et regardez la fin de saison bouger.")
    with st.container(border=True):
        _what_if(a, fc, team_id)
    how("et_si", meta)

    section("Quels modèles, et sont-ils fiables ?")
    with st.expander("Les trois modèles"):
        st.markdown("\n\n".join(explain(k, **meta) for k in ("modele_structurel", "modele_poisson", "modele_elo")))
    _model_quality(a, fc, meta)
