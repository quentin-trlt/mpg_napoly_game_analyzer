from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import (
    callout,
    chip,
    empty_state,
    fixture_grid,
    fmt_pct,
    how,
    kpi_row,
    prob_bar,
    section,
    table_height,
    volet_title,
)
from app.state import get_forecast
from mpg.analysis import Analysis
from mpg.forecast.evaluation import calibration, rps_by_gameweek, scored_summary, season_moves

ISSUES = {0: "victoire à domicile", 1: "nul", 2: "victoire à l'extérieur"}
REFERENCE = "Référence (fréquences)"
BASE_LABEL = "Pronostic de base"
MIN_CALIBRATION = 30
NON_BREAKING_HYPHEN = "\u2011"


def _score(text: object) -> str:
    return str(text).replace("-", NON_BREAKING_HYPHEN)


def _match_card(r: pd.Series, team_id: int) -> str:
    me = team_id in (r["home_team_id"], r["away_team_id"])
    if not r["joue"]:
        result = '<div class="meta mt-8">En attente du résultat</div>'
    else:
        ok = bool(r["favori_gagne"])
        badge = chip("Favori vainqueur", tone="good") if ok else chip("Surprise", tone="bad")
        exact = f"{int(r['home_goals'])}-{int(r['away_goals'])}"
        exact_note = " · score exact trouvé" if exact == r["score_probable"] else ""
        result = (
            f'<div class="row mt-12"><div class="score">{_score(exact)}</div>{badge}</div>'
            f'<div class="meta mt-6">On donnait {r["p_issue_reelle"]:.0%} à la '
            f"{ISSUES[int(r['issue'])]}. Score prédit : {escape(_score(r['score_probable']))}{exact_note}.</div>"
        )
    return (
        f'<div class="fixture{" me" if me else ""}"><div class="pair"><div class="team">{escape(r["home_team"])}</div>'
        f'<div class="vs">contre</div><div class="team">{escape(r["away_team"])}</div></div>'
        f'<div class="foot">{prob_bar(r["p_dom"], r["p_nul"], r["p_ext"])}{result}</div></div>'
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
        fixture_grid([_match_card(r, team_id) for _, r in day.iterrows()], min(len(day), 5))
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
                "label": "Probabilité moyenne du vrai résultat",
                "value": fmt_pct(day["p_issue_reelle"].mean()),
                "sub": "33 % = pas mieux que le hasard",
            },
            {
                "label": "Erreur de prévision de la journée",
                "value": f"{day['rps'].mean():.3f}",
                "sub": (
                    f"plus bas = mieux. {abs(gain):.0%} d'erreur "
                    + ("en moins" if gain > 0 else "en plus")
                    + f" que le pronostic de base ({rps_ref:.3f})"
                )
                if gain == gain
                else "plus bas = mieux",
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
    fixture_grid([_match_card(r, team_id) for _, r in day.iterrows()], min(len(day), 5))
    if pending_gws:
        st.caption(f"Pronostics figés en attente de résultat : {', '.join(f'J{g}' for g in pending_gws)}.")

    with st.expander("Ce que disait chaque modèle sur cette journée"):
        d = (
            fm[fm["gw"] == gw]
            .replace({"modele": {REFERENCE: BASE_LABEL}})
            .assign(
                match=lambda x: x["home_team"] + " – " + x["away_team"],
                score=lambda x: x["home_goals"].astype(int).astype(str) + "-" + x["away_goals"].astype(int).astype(str),
            )
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
                    "Probabilité du vrai résultat", min_value=0, max_value=1, format="percent"
                ),
                "rps": st.column_config.NumberColumn("Erreur de prévision ↓", format="%.3f", help="Plus bas = mieux"),
            },
        )

    section("Sur toute la saison")
    summ = scored_summary(fm).replace({"modele": {REFERENCE: BASE_LABEL}})
    left, right = st.columns([1.2, 1], gap="medium")
    with left:
        charts.show(charts.rps_evolution(rps_by_gameweek(fm)))
    with right:
        st.caption("Chaque modèle est noté par son erreur de prévision : plus elle est basse, mieux c'est.")
        with st.expander("Détail des erreurs de prévision (RPS, log-loss, Brier)"):
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
                        "Probabilité du vrai résultat", min_value=0, max_value=1, format="percent"
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
            f"La courbe de calibration (les probabilités annoncées se réalisent-elles ?) apparaîtra à partir de "
            f"{MIN_CALIBRATION} matchs notés "
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
                "pts_moy": "Points prévus",
                "p_titre": "Titre",
                "p_podium": "Podium",
                "p_dernier": "Dernier",
            }.get,
        )
        titles = {
            "rang_moy": ("Classement final prédit (rang moyen)", "Rang moyen prédit"),
            "pts_moy": ("Points prévus en fin de saison", "Points"),
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
    st.markdown(f"**Classement final prédit, {labels[df[x_col].max()][0].lower()}{labels[df[x_col].max()][1:]}**")
    st.dataframe(
        latest.assign(rang_predit=range(1, len(latest) + 1))[
            ["rang_predit", "team_name", "pts_actuels", "pts_moy", "rang_moy", "p_titre", "p_podium", "p_dernier"]
        ],
        hide_index=True,
        column_config={
            "rang_predit": st.column_config.NumberColumn("#", width="small"),
            "team_name": "Équipe",
            "pts_actuels": "Points à cette date",
            "pts_moy": st.column_config.NumberColumn("Points prévus", format="%.1f"),
            "rang_moy": st.column_config.NumberColumn("Rang moyen", format="%.1f"),
            "p_titre": st.column_config.ProgressColumn("Titre", min_value=0, max_value=1, format="percent"),
            "p_podium": st.column_config.ProgressColumn("Podium", min_value=0, max_value=1, format="percent"),
            "p_dernier": st.column_config.ProgressColumn("Dernier", min_value=0, max_value=1, format="percent"),
        },
        height=table_height(len(latest)),
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
                        x_title="Points de pourcentage",
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
                        "delta_pts_moy": st.column_config.NumberColumn("Points prévus (variation)", format="%+.1f"),
                        "delta_rang_moy": st.column_config.NumberColumn(
                            "Rang moyen (variation)", format="%+.1f", help="Négatif = l'équipe monte"
                        ),
                        "delta_p_titre": st.column_config.NumberColumn("Titre (variation)", format="percent"),
                        "delta_p_podium": st.column_config.NumberColumn("Podium (variation)", format="percent"),
                        "delta_p_dernier": st.column_config.NumberColumn("Dernier (variation)", format="percent"),
                    },
                )
    else:
        how("fuite_backtest", meta)


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    volet_title(
        "Avait-on vu juste ?",
        "Les pronostics sont figés avant chaque journée puis confrontés aux résultats. On suit aussi comment le "
        "classement final prédit évolue, semaine après semaine.",
    )
    if not meta["saison_en_cours"]:
        empty_state(
            f"Aucun pronostic figé pour la saison {meta['saison']}",
            "Les pronostics sont figés avant chaque journée de la saison en cours. Cette saison est terminée et "
            "n'en a pas : il n'y a rien à comparer aux résultats.",
        )
        return
    fc = get_forecast()
    fm = fc["frozen_matches"]

    section("Pronostics contre résultats")
    if fm.empty:
        callout(
            "Aucun pronostic figé pour l'instant. Lance <code>python -m mpg.forecast</code> avant la prochaine "
            "journée, puis commite le dossier <code>content/pronostics/</code>.",
            warn=True,
        )
    else:
        _gameweek_review(fm, team_id, meta)

    section("Évolution du classement final prédit")
    _season_evolution(a, fc, team_id, meta)
