from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import callout, fmt_pct, hero, how, kpi_row, prob_bar, section
from app.state import get_forecast
from mpg.analysis import Analysis
from mpg.forecast.evaluation import calibration, rps_by_gameweek, scored_summary, season_moves

ISSUES = {0: "victoire à domicile", 1: "nul", 2: "victoire à l'extérieur"}
REFERENCE = "Référence (fréquences)"
MIN_CALIBRATION = 30


def _match_card(r: pd.Series, team_id: int) -> str:
    me = team_id in (r["home_team_id"], r["away_team_id"])
    if not r["joue"]:
        result = '<div class="meta" style="margin-top:8px">En attente du résultat</div>'
    else:
        ok = bool(r["favori_gagne"])
        badge = (
            '<span class="chip" style="border-color:rgba(12,163,12,.6)">Favori vainqueur</span>'
            if ok
            else '<span class="chip" style="border-color:rgba(208,59,59,.7)">Surprise</span>'
        )
        exact = f"{int(r['home_goals'])}-{int(r['away_goals'])}"
        exact_note = " · score exact trouvé" if exact == r["score_probable"] else ""
        result = (
            f'<div class="row" style="margin-top:10px"><div class="score">{exact}</div>{badge}</div>'
            f'<div class="meta" style="margin-top:6px">On donnait {r["p_issue_reelle"]:.0%} à la '
            f"{ISSUES[int(r['issue'])]}. Score prédit : {escape(str(r['score_probable']))}{exact_note}.</div>"
        )
    return (
        f'<div class="fixture{" me" if me else ""}"><div class="team">{escape(r["home_team"])}</div>'
        f'<div class="meta" style="margin:2px 0">contre</div><div class="team">{escape(r["away_team"])}</div>'
        f"{prob_bar(r['p_dom'], r['p_nul'], r['p_ext'])}{result}</div>"
    )


def _gameweek_review(fm: pd.DataFrame, team_id: int, meta: dict) -> None:
    ens = fm[fm["modele"] == "Ensemble"]
    scored_gws = sorted(ens.loc[ens["joue"], "gw"].unique())
    pending_gws = sorted(ens.loc[~ens["joue"], "gw"].unique())

    if not scored_gws:
        gw = pending_gws[0]
        callout(
            f"Les pronostics de la J{gw} sont figés depuis le {ens.loc[ens['gw'] == gw, 'fige_le'].iloc[0]}. "
            "Ils seront notés automatiquement dès que les fichiers de <code>data/</code> contiendront cette journée."
        )
        day = ens[ens["gw"] == gw]
        for col, (_, r) in zip(st.columns(len(day)), day.iterrows()):
            with col:
                st.html(_match_card(r, team_id))
        return

    gw = st.selectbox("Journée", options=scored_gws[::-1], format_func=lambda g: f"Journée {g}", key="suivi_gw")
    day = ens[ens["gw"] == gw]
    ref = fm[(fm["modele"] == REFERENCE) & (fm["gw"] == gw)]
    surprise = day.sort_values("p_issue_reelle").iloc[0]
    rps_ref = ref["rps"].mean() if not ref.empty else float("nan")
    gain = (1 - day["rps"].mean() / rps_ref) if rps_ref == rps_ref and rps_ref > 0 else float("nan")
    kpi_row(
        [
            {
                "label": "Favoris vainqueurs",
                "value": f"{int(day['favori_gagne'].sum())} / {len(day)}",
                "sub": "le résultat le plus probable s'est produit",
            },
            {
                "label": "Proba. moyenne du vrai résultat",
                "value": fmt_pct(day["p_issue_reelle"].mean()),
                "sub": "33 % = pas mieux que le hasard",
            },
            {
                "label": "RPS de la journée",
                "value": f"{day['rps'].mean():.3f}",
                "sub": (f"référence {rps_ref:.3f} · {gain:+.0%} " + ("de mieux" if gain > 0 else "de moins bien"))
                if gain == gain
                else "plus bas = meilleur",
            },
            {
                "label": "Plus grosse surprise",
                "value": f"{surprise['home_team']} – {surprise['away_team']}",
                "small": True,
                "sub": f"{int(surprise['home_goals'])}-{int(surprise['away_goals'])}, on n'y croyait qu'à "
                f"{surprise['p_issue_reelle']:.0%}",
            },
        ]
    )
    for col, (_, r) in zip(st.columns(len(day)), day.iterrows()):
        with col:
            st.html(_match_card(r, team_id))
    if pending_gws:
        st.caption(f"Pronostics figés en attente de résultat : {', '.join(f'J{g}' for g in pending_gws)}.")

    with st.expander("Ce que disait chaque modèle sur cette journée"):
        d = fm[fm["gw"] == gw].assign(
            match=lambda x: x["home_team"] + " – " + x["away_team"],
            score=lambda x: x["home_goals"].astype(int).astype(str) + "-" + x["away_goals"].astype(int).astype(str),
        )
        st.dataframe(
            d[["match", "score", "modele", "p_dom", "p_nul", "p_ext", "p_issue_reelle", "rps"]],
            hide_index=True,
            column_config={
                "match": "Match",
                "score": "Score",
                "modele": "Modèle",
                "p_dom": st.column_config.NumberColumn("Dom.", format="percent"),
                "p_nul": st.column_config.NumberColumn("Nul", format="percent"),
                "p_ext": st.column_config.NumberColumn("Ext.", format="percent"),
                "p_issue_reelle": st.column_config.ProgressColumn(
                    "Proba. du vrai résultat", min_value=0, max_value=1, format="percent"
                ),
                "rps": st.column_config.NumberColumn("RPS", format="%.3f"),
            },
        )

    section("Sur toute la saison")
    summ = scored_summary(fm)
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        charts.show(charts.rps_evolution(rps_by_gameweek(fm)))
    with right:
        st.dataframe(
            summ,
            hide_index=True,
            column_config={
                "modele": "Modèle",
                "matchs": "Matchs",
                "rps": st.column_config.NumberColumn("RPS ↓", format="%.3f"),
                "log_loss": st.column_config.NumberColumn("Log-loss ↓", format="%.3f"),
                "brier": st.column_config.NumberColumn("Brier ↓", format="%.3f"),
                "proba_issue_reelle": st.column_config.ProgressColumn(
                    "Proba. du vrai résultat", min_value=0, max_value=1, format="percent"
                ),
                "favoris_gagnants": st.column_config.NumberColumn("Favoris vainqueurs", format="percent"),
            },
        )
        how(["scores_prevision", "pronostics_figes"], meta)
    n_scored = int(ens["joue"].sum())
    if n_scored >= MIN_CALIBRATION:
        charts.show(charts.calibration_chart(calibration(fm)))
        how("calibration", meta)
    else:
        st.caption(
            f"La courbe de calibration apparaîtra à partir de {MIN_CALIBRATION} matchs notés "
            f"({n_scored} aujourd'hui) : en dessous, elle ne serait que du bruit."
        )


def _season_evolution(a: Analysis, fc: dict, team_id: int, meta: dict) -> None:
    names = a.league.team_names
    snaps = fc["frozen_seasons"]
    mode = st.segmented_control(
        "Source",
        options=["fige", "recalcule"],
        default="fige" if not snaps.empty else "recalcule",
        required=True,
        format_func={"fige": "Figé à l'époque", "recalcule": "Recalculé aujourd'hui"}.get,
        key="suivi_mode",
        help="Figé : ce que l'app affichait vraiment à chaque date. Recalculé : le modèle d'aujourd'hui rejoué sur les "
        "résultats connus à chaque date.",
    )
    if mode == "fige":
        if snaps.empty:
            st.info("Aucun instantané de fin de saison n'a encore été figé.")
            return
        df, x_col = snaps, "avant_journee"
        labels = {g: f"Avant J{g}" for g in df[x_col].unique()}
    else:
        df = fc["history"].assign(team_name=lambda d: d["team_id"].map(names))
        x_col = "apres_journee"
        labels = {g: "Avant J1" if g == 0 else f"Après J{g}" for g in df[x_col].unique()}

    n_points = df[x_col].nunique()
    finished = a.league.played["gw"].max() == a.league.fixtures["gw"].max()
    final = a.standings.set_index("team_id")["rang"].to_dict() if finished else None
    if n_points >= 2:
        metric = st.segmented_control(
            "Indicateur",
            options=["rang_moy", "pts_moy", "p_titre", "p_podium", "p_dernier"],
            default="rang_moy",
            required=True,
            key="suivi_metric",
            format_func={
                "rang_moy": "Rang prédit",
                "pts_moy": "Points attendus",
                "p_titre": "Titre",
                "p_podium": "Podium",
                "p_dernier": "Dernier",
            }.get,
        )
        titles = {
            "rang_moy": ("Classement final prédit (rang moyen)", "Rang moyen prédit"),
            "pts_moy": ("Points attendus en fin de saison", "Points"),
            "p_titre": ("Probabilité de titre", "%"),
            "p_podium": ("Probabilité de podium", "%"),
            "p_dernier": ("Probabilité de finir dernier", "%"),
        }
        title, y_title = titles[metric]
        charts.show(
            charts.snapshot_lines(
                df,
                x_col,
                metric,
                names,
                team_id,
                title,
                y_title,
                reverse=metric == "rang_moy",
                pct=metric.startswith("p_"),
                final=final if metric == "rang_moy" else None,
                x_labels=labels,
            )
        )
    else:
        callout(
            "Un seul instantané figé pour l'instant : les courbes apparaîtront après la prochaine journée. "
            "En attendant, voici le classement final prédit à cette date, et l'onglet « Recalculé aujourd'hui » "
            "montre déjà une évolution."
        )

    latest = df[df[x_col] == df[x_col].max()].sort_values("rang_moy")
    st.markdown(f"**Classement final prédit — {labels[df[x_col].max()].lower()}**")
    st.dataframe(
        latest.assign(rang_predit=range(1, len(latest) + 1))[
            ["rang_predit", "team_name", "pts_actuels", "pts_moy", "rang_moy", "p_titre", "p_podium", "p_dernier"]
        ],
        hide_index=True,
        column_config={
            "rang_predit": st.column_config.NumberColumn("#", width="small"),
            "team_name": "Équipe",
            "pts_actuels": "Pts à cette date",
            "pts_moy": st.column_config.NumberColumn("Pts attendus", format="%.1f"),
            "rang_moy": st.column_config.NumberColumn("Rang moyen", format="%.1f"),
            "p_titre": st.column_config.ProgressColumn("Titre", min_value=0, max_value=1, format="percent"),
            "p_podium": st.column_config.ProgressColumn("Podium", min_value=0, max_value=1, format="percent"),
            "p_dernier": st.column_config.ProgressColumn("Dernier", min_value=0, max_value=1, format="percent"),
        },
        height=38 * (len(latest) + 1) + 2,
    )

    if mode == "fige":
        moves = season_moves(snaps, a.team_match)
        if not moves.empty:
            section(
                "Qui monte, qui descend",
                "Écart entre les deux derniers instantanés, avec les résultats joués entre les deux.",
            )
            left, right = st.columns([1, 1.3], gap="medium")
            with left:
                charts.show(
                    charts.diverging_bars(
                        moves.assign(d=moves["delta_p_titre"] * 100),
                        "d",
                        "team_name",
                        team_id,
                        "Variation de la probabilité de titre",
                        x_title="Points de %",
                        fmt="+.1f",
                    )
                )
            with right:
                st.dataframe(
                    moves[
                        [
                            "team_name",
                            "resultats",
                            "delta_pts_moy",
                            "delta_rang_moy",
                            "delta_p_titre",
                            "delta_p_podium",
                            "delta_p_dernier",
                        ]
                    ],
                    hide_index=True,
                    column_config={
                        "team_name": "Équipe",
                        "resultats": st.column_config.TextColumn("Résultat(s)", width="medium"),
                        "delta_pts_moy": st.column_config.NumberColumn("Δ pts attendus", format="%+.1f"),
                        "delta_rang_moy": st.column_config.NumberColumn(
                            "Δ rang moyen", format="%+.1f", help="Négatif = l'équipe monte"
                        ),
                        "delta_p_titre": st.column_config.NumberColumn("Δ titre", format="percent"),
                        "delta_p_podium": st.column_config.NumberColumn("Δ podium", format="percent"),
                        "delta_p_dernier": st.column_config.NumberColumn("Δ dernier", format="percent"),
                    },
                )
    else:
        how("fuite_backtest", meta)


def render(a: Analysis, team_id: int) -> None:
    fc = get_forecast()
    meta = a.meta
    hero(
        "Suivi des pronostics",
        "Avait-on vu juste ?",
        "Les pronostics sont figés avant chaque journée puis confrontés aux résultats. On suit aussi comment le "
        "classement final prédit évolue, semaine après semaine.",
    )
    fm = fc["frozen_matches"]

    section("Pronostics contre résultats")
    if fm.empty:
        callout(
            "Aucun pronostic figé pour l'instant. Lancez <code>python -m mpg.forecast</code> avant la prochaine "
            "journée, puis commitez le dossier <code>content/pronostics/</code>.",
            warn=True,
        )
    else:
        _gameweek_review(fm, team_id, meta)

    section("Évolution du classement final prédit")
    _season_evolution(a, fc, team_id, meta)
