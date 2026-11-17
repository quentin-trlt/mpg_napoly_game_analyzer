from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import (
    fmt_m,
    fmt_pct,
    form_badges,
    how,
    kpi_row,
    limit_banner,
    rank_tone,
    section,
    stat_grid,
    table_height,
    volet_title,
)
from app.state import get_forecast_light
from mpg.analysis import Analysis, team_card
from mpg.premier_league import club_form

SQUAD_COLUMNS = [
    "joueur",
    "poste",
    "club",
    "forme_club",
    "prochain_match",
    "enchere",
    "cote",
    "surpaiement_x",
    "n_notes",
    "note_moy",
    "note_retrecie",
    "note_moy_reelle",
    "buts_reels",
    "buts_mpg",
    "buts_reels_saison",
    "passes_decisives_saison",
    "cartons_jaunes",
    "cartons_rouges",
    "taux_jeu",
    "statut_performance",
    "choisi_titulaire",
    "residu_valeur",
]
SQUAD_CONFIG = {
    "joueur": st.column_config.TextColumn("Joueur", pinned=True),
    "poste": "Poste",
    "club": "Club",
    "forme_club": st.column_config.TextColumn(
        "Forme du club", help="5 derniers résultats du club en PL, du plus ancien au plus récent"
    ),
    "prochain_match": st.column_config.TextColumn(
        "Prochain match", help="Adversaire du club, lieu et date (heure de Paris)"
    ),
    "enchere": st.column_config.NumberColumn("Prix", format="%d M€"),
    "cote": st.column_config.NumberColumn("Cote", format="%d M€"),
    "surpaiement_x": st.column_config.NumberColumn(
        "Prix ÷ cote", format="%.2f", help="Au-dessus de 1, tu as payé plus cher que la cote"
    ),
    "n_notes": st.column_config.NumberColumn("Notes", help="Matchs notés retenus pour la note fiabilisée"),
    "note_moy": st.column_config.NumberColumn("Moy. brute", format="%.2f", help="Moyenne de ces notes"),
    "note_retrecie": st.column_config.NumberColumn(
        "Note fiabilisée",
        format="%.2f",
        help="Note attendue quand il joue, corrigée pour les joueurs qui ont peu de matchs",
    ),
    "note_moy_reelle": st.column_config.NumberColumn("Moy. PL", format="%.1f"),
    "buts_reels": "Buts ligue",
    "buts_mpg": "Buts MPG",
    "buts_reels_saison": "Buts PL",
    "passes_decisives_saison": st.column_config.NumberColumn("Passes PL", format="%d"),
    "cartons_jaunes": st.column_config.NumberColumn("Jaunes", format="%d"),
    "cartons_rouges": st.column_config.NumberColumn("Rouges", format="%d"),
    "taux_jeu": st.column_config.ProgressColumn("Taux de jeu PL", min_value=0, max_value=1, format="percent"),
    "statut_performance": "Statut",
    "choisi_titulaire": st.column_config.NumberColumn("Titularisé (MPG)"),
    "residu_valeur": st.column_config.NumberColumn("Écart au prix", format="%+.2f"),
}


def _with_club_form(roster: pd.DataFrame, results: pd.DataFrame | None) -> pd.DataFrame:
    """Ajoute la forme récente du club (5 derniers, ordre chronologique) et son prochain match."""
    if results is None:
        return roster.assign(forme_club="", prochain_match="")
    form = club_form(results)
    date = form["prochain_date"].dt.tz_convert("Europe/Paris").dt.strftime("%d/%m")
    lieu = form["prochain_domicile"].map({True: "dom.", False: "ext."})
    form["prochain_match"] = (form["prochain_adversaire_short"] + " (" + lieu + "), " + date).fillna("")
    out = roster.merge(form[["club", "forme_club", "prochain_match"]], on="club", how="left")
    return out.fillna({"forme_club": "", "prochain_match": ""})


def _profile(a: Analysis, team_id: int, expected_rank: int | None) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Rangs calculables de l'équipe, et les dimensions écartées avec leur raison."""

    def rank(df, col, ascending=False) -> int | None:
        values = df.set_index("team_id")[col]
        if pd.isna(values.loc[team_id]):
            return None
        return int(values.rank(ascending=ascending, method="min").loc[team_id])

    dimensions = [
        ("Classement", int(a.standings.set_index("team_id").loc[team_id, "rang"]), "points", ""),
        ("Force sur le papier", expected_rank, "d'après les prix payés", "effectif incomplet"),
        ("Mercato", int(a.mercato.set_index("team_id").loc[team_id, "rang"]), "note globale du mercato", ""),
        ("Niveau de jeu", rank(a.standings, "note_moy"), "note moyenne", ""),
        ("Chance", rank(a.luck, "indice_chance"), "1 = le plus chanceux", ""),
        ("Coaching", rank(a.coaching, "regret_moy", ascending=True), "moins de points sur le banc", ""),
        (
            "Fiabilité",
            rank(a.mercato, "disponibilite_ponderee"),
            "joueurs qui jouent en PL",
            "pas de statistiques de Premier League",
        ),
        ("Attaque", rank(a.standings, "bp"), "buts marqués", ""),
        ("Défense", rank(a.standings, "bc", ascending=True), "buts encaissés", ""),
    ]
    kept = [(label, r, hint) for label, r, hint, _ in dimensions if r is not None]
    skipped = [f"{label} ({reason or 'donnée absente'})" for label, r, _, reason in dimensions if r is None]
    return kept, skipped


def _hero_subtitle(team: pd.Series, form: str) -> str:
    parts = []
    if pd.notna(team["president"]):
        parts.append(f"Président {escape(str(team['president']))}")
    if pd.notna(team["stade"]):
        parts.append(f"stade « {escape(str(team['stade']))} »")
    if form:
        parts.append(f"Forme {form_badges(form)}")
    return ", ".join(parts)


def _kpis(card: dict) -> list[dict]:
    top3 = f"{fmt_pct(card['part_top3'])} sur les 3 plus gros achats"
    has_value = card["valeur_actuelle"] is not None
    budget_sub = (
        f"valeur actuelle {fmt_m(card['valeur_actuelle'])} ({card['ratio_valeur_prix']:.0%}), {top3}"
        if has_value
        else top3
    )
    if card["note_reelle_mediane"] is not None:
        level = {
            "label": "Niveau de l'effectif",
            "value": f"{card['note_reelle_mediane']:.1f}",
            "sub": f"note PL médiane, {card['note_mpg_moy']:.2f} en MPG",
        }
    else:
        level = {
            "label": "Niveau de jeu",
            "value": f"{card['note_mpg_moy']:.2f}",
            "sub": "note moyenne en MPG, bonus compris",
        }
    if card["disponibilite"] is not None:
        fourth = {
            "label": "Fiabilité",
            "value": fmt_pct(card["disponibilite"]),
            "sub": f"taux de jeu PL, pondéré par les prix, {card['indisponibles']} indisponible(s)",
        }
    elif card["rang_attendu"] is not None:
        fourth = {
            "label": "Force de l'effectif",
            "value": f"{card['rang_attendu']}e",
            "sub": "rang d'après les prix payés",
        }
    else:
        fourth = {
            "label": "Force de l'effectif",
            "value": "Non calculée",
            "small": True,
            "sub": "l'effectif est incomplet : il manque au moins un poste",
        }
    return [
        {
            "label": "Classement",
            "value": f"{card['rang']}e",
            "sub": f"{card['pts']} pts, série {card['serie']}",
            "me": True,
        },
        {"label": "Budget payé", "value": fmt_m(card["budget_paye"]), "sub": budget_sub},
        level,
        fourth,
    ]


def _limits(a: Analysis) -> list[str]:
    caps = a.meta["capacites"]
    messages = [
        (
            caps.effectif_fin_saison,
            "Effectif de fin de saison : les joueurs partis en cours de route n'y figurent plus, les totaux "
            "(prix payés, force de l'effectif) peuvent donc être incomplets.",
        ),
        (
            not caps.cote,
            "Pas de cote MPG : la valeur actuelle de l'effectif et son écart avec le prix payé sont masqués.",
        ),
        (
            not caps.stats_pl,
            "Pas de statistiques de Premier League : la note réelle, la fiabilité et les indisponibles sont masquées.",
        ),
    ]
    return [text for active, text in messages if active]


def header(a: Analysis, team_id: int) -> None:
    team = a.league.teams.set_index("team_id").loc[team_id]
    stand = a.standings.set_index("team_id").loc[team_id]
    form = stand["forme"] if isinstance(stand["forme"], str) else ""
    subtitle = _hero_subtitle(team, form)
    coach = f"Coach {escape(str(team['coach']))}"
    volet_title(team["team_name"], f"{coach}, {subtitle}" if subtitle else coach)
    limit_banner(_limits(a))


def profil(a: Analysis, team_id: int) -> None:
    card = team_card(a, team_id)
    kpi_row(_kpis(card))

    profile, skipped = _profile(a, team_id, card["rang_attendu"])
    caption = "Rang de l'équipe dans chaque dimension, 1 = meilleur de la ligue. Vert : top 3, rouge : 3 derniers."
    if skipped:
        caption += f" {len(profile)} dimensions sur 9 affichées, non calculée(s) : {', '.join(skipped)}."
    section("Profil", caption)
    st.html(_profile_panel(profile, len(a.league.teams)))

    section("Match par match")
    charts.show(charts.gw_points(a.team_match, team_id))
    lines = a.lines.set_index("team_id").loc[team_id]
    st.caption(
        "Force par ligne (note brute) : "
        + ", ".join(f"{lab} {lines[lab]:.2f}" if pd.notna(lines[lab]) else f"{lab} aucun joueur" for lab in "GDMA")
    )


def effectif(a: Analysis, team_id: int) -> None:
    meta = a.meta
    roster = a.player_value[a.player_value["team_id"] == team_id]
    _price_section(roster, team_id, meta["capacites"].cote, meta)

    section("Effectif")
    squad = _with_club_form(roster, a.league.club_results)
    columns = [c for c in SQUAD_COLUMNS if squad[c].replace("", pd.NA).notna().any()]
    st.dataframe(
        squad.sort_values(["poste_groupe", "enchere"], ascending=[True, False])[columns],
        hide_index=True,
        column_config={c: SQUAD_CONFIG[c] for c in columns if c in SQUAD_CONFIG},
        height=table_height(len(roster)),
    )
    explained = [
        key for key, column in (("residu_valeur", "residu_valeur"), ("fiabilite", "taux_jeu")) if column in columns
    ]
    if explained:
        how(explained, meta)


def bonus(a: Analysis, team_id: int) -> None:
    _bonus_section(a, team_id, a.meta)
    if a.meta["saison_en_cours"]:
        _bonus_effect(get_forecast_light(), team_id, a.meta)


def _price_section(roster: pd.DataFrame, team_id: int, has_cote: bool, meta: dict) -> None:
    if not has_cote:
        section("Prix payé", "Pas de cote MPG sur cette saison : on montre ce que chaque joueur a coûté.")
        charts.show(
            charts.ranked_bars(
                roster,
                "enchere",
                "joueur",
                team_id,
                "Prix payé, joueur par joueur",
                fmt=".0f",
                ascending=True,
                x_title="M€",
            )
        )
        return
    section("Prix payé et cote actuelle")
    charts.show(
        charts.paired_bars(
            roster,
            "joueur",
            "enchere",
            "cote",
            "Prix payé",
            "Cote actuelle",
            "Prix payé et cote actuelle, joueur par joueur",
            "M€",
        )
    )
    how("surpaiement", meta)


def _bonus_cell(r, finished: bool) -> str:
    total = max(r.dotation, r.utilises)
    count = r.utilises if finished else max(r.restants, 0)
    off = count <= 0 if finished else r.restants <= 0
    lit = r.utilises if finished else r.restants
    dots = "".join(f'<span class="dot {"on" if i < lit else "off"}"></span>' for i in range(total))
    if r.utilises:
        detail = f"Utilisé : {escape(r.journees)}"
        if r.cibles and r.cibles != "—":
            detail += f", {escape(r.cibles)}"
    else:
        detail = "Jamais utilisé" if finished else "Pas encore utilisé"
    warn = '<div class="sub warn">Absent de la dotation</div>' if r.hors_dotation else ""
    state = f"{r.utilises} utilisé(s)" if finished else f"{r.restants} restant(s)"
    return (
        f'<div class="stat{" empty" if off else ""}" role="group" '
        f'aria-label="{escape(r.bonus)} : {state} sur {r.dotation}">'
        f'<div class="label">{escape(r.bonus)}</div>'
        f'<div class="value">{count}<span class="of">/{r.dotation}</span></div>'
        f'<div class="dots" aria-hidden="true">{dots}</div><div class="sub">{detail}</div>{warn}</div>'
    )


def _profile_panel(prof: list[tuple[str, int, str]], n: int) -> str:
    rungs = []
    for label, r, hint in prof:
        tone = rank_tone(r, n)
        track = "".join('<i class="on"></i>' if i == r else "<i></i>" for i in range(1, n + 1))
        rungs.append(
            f'<div class="rung {tone}" role="group" aria-label="{escape(label)} : {r}e sur {n}">'
            f'<div><div class="name">{escape(label)}</div><div class="hint">{escape(hint)}</div></div>'
            f'<div class="rank">{r}<span>/{n}</span></div>'
            f'<div class="track" aria-hidden="true">{track}</div></div>'
        )
    return f'<div class="panel"><div class="ladder">{"".join(rungs)}</div></div>'


def _bonus_section(a: Analysis, team_id: int, meta: dict) -> None:
    br = a.bonus_remaining
    finished = meta["capacites"].terminee
    section("Bonus utilisés" if finished else "Bonus restants")
    if br is None:
        st.info(
            "Ajoute un fichier `data/bonus_stock.csv` (colonnes `bonus`, `quantite`) avec la dotation de début "
            "de saison pour suivre les bonus restants."
        )
        return
    mine = br[br["team_id"] == team_id]
    total = int(mine["dotation"].sum())
    if finished:
        st.caption(
            f"{int(mine['utilises'].sum())} bonus utilisés sur {total} de dotation en {meta['nb_journees']} journées. "
            "Capitaine et bonus défensifs ne sont pas comptés : ils ne s'épuisent pas."
        )
    else:
        left_total = int(mine["restants"].clip(lower=0).sum())
        remaining_gw = a.league.n_gw - a.league.last_gw
        league_left = br.groupby("team_id")["restants"].apply(lambda s: s.clip(lower=0).sum())
        rank = int(league_left.rank(ascending=False, method="min").loc[team_id])
        st.caption(
            f"{left_total} bonus restants sur {total} pour {remaining_gw} journées à jouer, "
            f"{rank}e réserve de la ligue (médiane : {league_left.median():.0f}). Capitaine et bonus défensifs ne sont "
            "pas comptés : ils ne s'épuisent pas."
        )
        if (mine["restants"] < 0).any():
            st.warning(
                "Certains bonus ont été utilisés plus souvent que la dotation ne le permet : vérifie "
                "`data/bonus_stock.csv`."
            )
    st.html(stat_grid([_bonus_cell(r, finished) for r in mine.itertuples()], per_row=4))

    value = "utilises" if finished else "restants"
    with st.expander("Bonus utilisés par toutes les équipes" if finished else "Bonus restants de toutes les équipes"):
        pivot = br.pivot(index="team_id", columns="bonus", values=value)
        pivot = pivot[[b for b in dict.fromkeys(br["bonus"]) if b in pivot.columns]]
        pivot.insert(0, "Total", pivot.clip(lower=0).sum(axis=1))
        pivot.insert(0, "Équipe", pivot.index.map(a.league.team_names))
        st.dataframe(
            pivot.sort_values("Total", ascending=False),
            hide_index=True,
            column_config={
                "Total": st.column_config.ProgressColumn(
                    "Total",
                    min_value=0,
                    max_value=max(int(pivot["Total"].max()), 1) if finished else total,
                    format="%d",
                )
            },
        )
        if not finished:
            st.caption("Utile pour anticiper : un adversaire qui a encore son Suarez peut viser ton gardien.")
    if not finished:
        how("bonus_restants", meta)


def _bonus_effect(fc: dict, team_id: int, meta: dict) -> None:
    be = fc.get("bonus_effect")
    section("Ce que valent les bonus restants")
    if be is None:
        st.caption(
            "Dotation de bonus inconnue (fichier `data/bonus_stock.csv` absent) : les prévisions ignorent les "
            "bonus à venir."
        )
        return
    struct = next(m for m in fc["draws"].models if hasattr(m, "rotaldo_note"))
    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.diverging_bars(
                be,
                "effet_pts",
                "team_name",
                team_id,
                "Effet net des bonus restants sur les points prévus",
                x_title="Points prévus en fin de saison",
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
                "effet_pts": st.column_config.NumberColumn("Points", format="%+.2f", width="small"),
                "effet_titre": st.column_config.NumberColumn("Chances de titre", format="percent", width="small"),
                "effet_dernier": st.column_config.NumberColumn(
                    "Chances de finir dernier", format="percent", width="small"
                ),
            },
            height=table_height(len(be)),
        )
        st.caption(
            "Les probabilités des matchs et de fin de saison du volet Prédictions de la page Pronostics incluent déjà l'usage attendu "
            "des bonus restants."
        )
    how("bonus_prevision", {**meta, "note_slope": struct.link.b})
