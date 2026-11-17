from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import (
    as_pct,
    callout,
    chip,
    fixture_grid,
    fmt_pct,
    how,
    pct_column,
    prob_bar,
    section,
    short_table,
    table_height,
    volet_title,
)
from app.state import get_backtest, get_forecast_light, get_frozen
from app.views.forecast_common import BASE_LABEL, count_word, error_gain, forecast_meta, gain_phrase, model_keys, score
from mpg.analysis import Analysis
from mpg.forecast.evaluation import calibration, frozen_frames, rps_by_gameweek, scored_summary, season_moves
from mpg.forecast.season import REFERENCE
from mpg.glossary import explain

ISSUES = {0: "victoire à domicile", 1: "nul", 2: "victoire à l'extérieur"}
MIN_CALIBRATION = 30
ENSEMBLE = "Ensemble"


def verdict(gw: int, favourites_won: int, played: int) -> str:
    """« J5 : 4 favoris sur 5 ont gagné »."""
    noun = "favoris" if favourites_won > 1 else "favori"
    verb = "ont" if favourites_won > 1 else "a"
    return f"J{gw} : {favourites_won} {noun} sur {played} {verb} gagné"


def season_verdict(fm: pd.DataFrame) -> dict | None:
    """Bilan en chiffres des pronostics figés déjà joués : favoris vainqueurs et erreur face au pronostic de base."""
    played = fm[fm["joue"]]
    ens = played[played["modele"] == ENSEMBLE]
    if ens.empty:
        return None
    ref = played[played["modele"] == REFERENCE]
    return {
        "matchs": len(ens),
        "favoris": int(ens["favori_gagne"].sum()),
        "p_reelle": float(ens["p_issue_reelle"].mean()),
        "gain": error_gain(ens["rps"].mean(), ref["rps"].mean() if not ref.empty else float("nan")),
    }


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
            f'<div class="row mt-12"><div class="score">{score(exact)}</div>{badge}</div>'
            f'<div class="meta mt-6">On donnait {fmt_pct(r["p_issue_reelle"])} à la '
            f"{ISSUES[int(r['issue'])]}. Score prédit : {escape(score(r['score_probable']))}{exact_note}.</div>"
        )
    return (
        f'<div class="fixture{" me" if me else ""}"><div class="pair"><div class="team">{escape(r["home_team"])}</div>'
        f'<div class="vs">contre</div><div class="team">{escape(r["away_team"])}</div></div>'
        f'<div class="foot">{prob_bar(r["p_dom"], r["p_nul"], r["p_ext"])}{result}</div></div>'
    )


def _surprise_caption(day: pd.DataFrame, reference: pd.DataFrame) -> str:
    surprise = day.sort_values("p_issue_reelle").iloc[0]
    parts = [
        f"Plus grosse surprise : {surprise['home_team']} – {surprise['away_team']} "
        f"({int(surprise['home_goals'])}-{int(surprise['away_goals'])}), on n'y croyait qu'à "
        f"{fmt_pct(surprise['p_issue_reelle'])}."
    ]
    gain = error_gain(day["rps"].mean(), reference["rps"].mean() if not reference.empty else float("nan"))
    if gain is not None:
        parts.append(f"Sur la journée, {gain_phrase(gain)}.")
    return " ".join(parts)


def last_gameweek(fm: pd.DataFrame, team_id: int) -> None:
    """Dernière journée jouée revue avec les pronostics figés avant elle : verdict en tête, puis les matchs."""
    ens = fm[fm["modele"] == ENSEMBLE]
    scored = ens[ens["joue"]]
    if scored.empty:
        gw = int(ens["gw"].min())
        frozen_on = pd.to_datetime(ens.loc[ens["gw"] == gw, "fige_le"].iloc[0]).strftime("%d/%m/%Y")
        callout(
            f"Les pronostics de la J{gw} sont figés depuis le {frozen_on}. "
            "Ils seront notés automatiquement dès que ces matchs seront joués."
        )
        return

    gw = int(scored["gw"].max())
    day = ens[ens["gw"] == gw]
    played = day[day["joue"]]
    remaining = len(day) - len(played)
    caption = _surprise_caption(played, fm[(fm["modele"] == REFERENCE) & (fm["gw"] == gw) & fm["joue"]])
    if remaining:
        caption += f" {remaining} match{'s' if remaining > 1 else ''} encore à jouer."
    section(verdict(gw, int(played["favori_gagne"].sum()), len(played)), caption)
    fixture_grid([_match_card(r, team_id) for _, r in day.iterrows()], min(len(day), 5))

    with st.expander("Ce que disait chaque modèle sur cette journée"):
        detail = (
            fm[(fm["gw"] == gw) & fm["joue"]]
            .replace({"modele": {REFERENCE: BASE_LABEL}})
            .assign(
                match=lambda x: x["home_team"] + " – " + x["away_team"],
                score=lambda x: x["home_goals"].astype(int).astype(str) + "-" + x["away_goals"].astype(int).astype(str),
            )
        )
        st.dataframe(
            as_pct(detail[["match", "score", "modele", "p_issue_reelle", "rps"]], ["p_issue_reelle"]),
            hide_index=True,
            alt="Ce que disait chaque modèle",
            column_config={
                "match": "Match",
                "score": "Score",
                "modele": "Modèle",
                "p_issue_reelle": pct_column("Chances données au vrai résultat", bar=True),
                "rps": st.column_config.NumberColumn("Erreur de prévision ↓", format="%.3f", help="Plus bas = mieux"),
            },
        )


def _season_sentences(summary: dict) -> str:
    n, wins = summary["matchs"], summary["favoris"]
    text = (
        f"Sur les <b>{n} matchs</b> déjà joués depuis que les pronostics sont figés, le favori a gagné "
        f"<b>{wins} fois ({fmt_pct(wins / n)})</b>."
    )
    if summary["gain"] is not None:
        text += f" Nos pronostics font <b>{gain_phrase(summary['gain'])}</b>."
    return (
        f"{text} En moyenne, on donnait {fmt_pct(summary['p_reelle'])} de chances au résultat qui s'est produit "
        "(33 % = pas mieux que le hasard)."
    )


def _scores_table(summary: pd.DataFrame, **kwargs) -> None:
    summary = summary.replace({"modele": {REFERENCE: BASE_LABEL}})
    visible = [c for c in ("modele", "matchs", "favoris_gagnants", "proba_issue_reelle", "rps") if c in summary]
    short_table(
        as_pct(summary, ["proba_issue_reelle", "favoris_gagnants"]),
        visible,
        full=[*visible, "log_loss", "brier"],
        more="Toutes les mesures d'erreur",
        column_config={
            "modele": "Modèle",
            "matchs": "Matchs",
            "rps": st.column_config.NumberColumn("Erreur de prévision ↓", format="%.3f", help="Plus bas = mieux"),
            "log_loss": st.column_config.NumberColumn("Log-loss ↓", format="%.3f"),
            "brier": st.column_config.NumberColumn("Brier ↓", format="%.3f"),
            "proba_issue_reelle": pct_column("Chances données au vrai résultat", bar=True),
            "favoris_gagnants": pct_column("Favoris vainqueurs"),
        },
        height=table_height(len(summary)),
        **kwargs,
    )


def _season_quality(fm: pd.DataFrame, meta: dict) -> None:
    summary = season_verdict(fm)
    if summary is None:
        callout("Aucun pronostic figé n'a encore été noté : le bilan apparaîtra après la première journée jouée.")
        return
    callout(_season_sentences(summary))
    st.caption(
        "Le pronostic de base annonce partout les mêmes chances : la fréquence moyenne des victoires à domicile, "
        "des nuls et des victoires à l'extérieur."
    )
    n_scored = summary["matchs"]
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(charts.rps_evolution(rps_by_gameweek(fm)))
    with right:
        if n_scored >= MIN_CALIBRATION:
            charts.show(charts.calibration_chart(calibration(fm)))
        else:
            st.caption(
                f"La courbe qui compare les chances annoncées à ce qui s'est réellement produit apparaîtra à partir "
                f"de {MIN_CALIBRATION} matchs notés ({n_scored} aujourd'hui) : en dessous, elle ne serait que du bruit."
            )
    st.caption("Chaque modèle est noté par son erreur de prévision : plus elle est basse, mieux c'est.")
    _scores_table(scored_summary(fm))
    how(["scores_prevision", *(["calibration"] if n_scored >= MIN_CALIBRATION else [])], meta)


def _season_evolution(a: Analysis, fc: dict, team_id: int) -> None:
    names = a.league.team_names
    df = fc["frozen_seasons"]
    if df.empty:
        st.info("Aucun instantané de fin de saison n'a encore été figé.")
        return
    x_col = "avant_journee"
    labels = {g: f"Avant J{g}" for g in df[x_col].unique()}
    finished = a.league.played["gw"].max() == a.league.fixtures["gw"].max()
    final = a.standings.set_index("team_id")["rang"].to_dict() if finished else None
    if df[x_col].nunique() >= 2:
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
            "En attendant, voici le classement final prédit à cette date."
        )

    latest = df[df[x_col] == df[x_col].max()].sort_values("rang_moy")
    label = labels[df[x_col].max()]
    st.markdown(f"**Classement final prédit, {label[0].lower()}{label[1:]}**")
    short_table(
        as_pct(latest.assign(rang_predit=range(1, len(latest) + 1)), ["p_titre", "p_podium", "p_dernier"]),
        ["rang_predit", "team_name", "p_titre", "p_podium", "p_dernier"],
        full=["rang_predit", "team_name", "p_titre", "p_podium", "p_dernier", "pts_actuels", "pts_moy", "rang_moy"],
        alt="Classement final prédit",
        column_config={
            "rang_predit": st.column_config.NumberColumn("#", width="small"),
            "team_name": "Équipe",
            "pts_actuels": "Points à cette date",
            "pts_moy": st.column_config.NumberColumn("Points prévus", format="%.1f"),
            "rang_moy": st.column_config.NumberColumn("Rang moyen", format="%.1f"),
            "p_titre": pct_column("Titre", bar=True),
            "p_podium": pct_column("Podium", bar=True),
            "p_dernier": pct_column("Dernier", bar=True),
        },
        height=table_height(len(latest)),
    )

    moves = season_moves(df, a.team_match)
    if moves.empty:
        return
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
        short_table(
            as_pct(moves, ["delta_p_titre", "delta_p_podium", "delta_p_dernier"]),
            ["team_name", "resultats", "delta_p_titre", "delta_p_podium", "delta_p_dernier"],
            full=[
                "team_name",
                "resultats",
                "delta_p_titre",
                "delta_p_podium",
                "delta_p_dernier",
                "delta_pts_moy",
                "delta_rang_moy",
            ],
            alt="Variations depuis le dernier instantané",
            column_config={
                "team_name": "Équipe",
                "resultats": st.column_config.TextColumn("Résultat(s)", width="medium"),
                "delta_pts_moy": st.column_config.NumberColumn("Points prévus (variation)", format="%+.1f"),
                "delta_rang_moy": st.column_config.NumberColumn(
                    "Rang moyen (variation)", format="%+.1f", help="Négatif = l'équipe monte"
                ),
                "delta_p_titre": pct_column("Titre +/-", signed=True, help="Variation de la chance de titre"),
                "delta_p_podium": pct_column("Podium +/-", signed=True, help="Variation de la chance de podium"),
                "delta_p_dernier": pct_column(
                    "Dernier +/-", signed=True, help="Variation de la chance de finir dernier"
                ),
            },
        )


def _replayed_quality(fc: dict, meta: dict) -> None:
    summary = fc["backtest_summary"]
    ens = summary[summary["modele"] == ENSEMBLE]
    ref = summary[summary["modele"] == REFERENCE]
    if not ens.empty and not ref.empty:
        n = int(ens["matchs"].iloc[0])
        gain = error_gain(float(ens["rps"].iloc[0]), float(ref["rps"].iloc[0]))
        if gain is not None:
            callout(f"Sur les <b>{n} matchs</b> rejoués, nos pronostics font <b>{gain_phrase(gain)}</b>.")
    _scores_table(summary)
    how("fuite_backtest", meta)


def _frozen_files(a: Analysis, fc: dict, meta: dict) -> None:
    fm = fc["frozen_matches"]
    if fm.empty:
        st.info("Aucun pronostic figé pour l'instant.")
    else:
        figees = sorted(fm["gw"].unique())
        notees = sorted(fm.loc[fm["joue"], "gw"].unique())
        st.caption(
            f"Journées figées : {', '.join(f'J{g}' for g in figees)}. "
            + (f"Déjà notées : {', '.join(f'J{g}' for g in notees)}." if notees else "Aucune n'est encore jouée.")
            + " La dernière journée jouée est revue dans le volet Cette journée."
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


def render_fiabilite(a: Analysis, team_id: int) -> None:
    volet_title(
        "Peut-on se fier aux pronostics ?",
        "On compare ce qui était annoncé avant chaque journée à ce qui s'est vraiment passé. "
        "La première fois, le rejeu du passé demande quelques secondes de calcul.",
    )
    fc = {**get_forecast_light(), **get_frozen(), **get_backtest()}
    if fc["baseline"] is None:
        callout("La saison est terminée : il n'y a plus de pronostic à évaluer.")
        return
    draws = fc["draws"]
    meta = forecast_meta(a, draws)
    fm = fc["frozen_matches"]

    section("Sur toute la saison", "Les pronostics figés avant chaque journée, comparés aux vrais résultats.")
    if fm.empty:
        callout(
            "Aucun pronostic figé pour l'instant. Ils sont enregistrés avant chaque journée, puis notés une fois "
            "les matchs joués.",
            warn=True,
        )
    else:
        _season_quality(fm, meta)

    section("Évolution du classement final prédit")
    _season_evolution(a, fc, team_id)

    section("Comment sont faits les pronostics")
    keys = model_keys(draws)
    with st.expander(f"Les {count_word(len(keys))} modèles"):
        st.markdown("\n\n".join(explain(k, **meta) for k in keys))

    section("Rejeu du passé", "Chaque journée déjà jouée est prédite à nouveau avec les seules journées précédentes.")
    _replayed_quality(fc, meta)

    section("Pronostics figés")
    _frozen_files(a, fc, meta)
