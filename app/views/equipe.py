from html import escape

import pandas as pd
import streamlit as st

from app import charts
from app.components import fmt_m, fmt_pct, form_badges, hero, how, kpi_row, rank_tone, section, stat_grid, table_height
from mpg.analysis import Analysis, team_card
from mpg.premier_league import club_form


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


def _profile(a: Analysis, team_id: int) -> list[tuple[str, int, str]]:
    def rank(df, col, ascending=False):
        return int(df.set_index("team_id")[col].rank(ascending=ascending, method="min").loc[team_id])

    return [
        ("Classement", int(a.standings.set_index("team_id").loc[team_id, "rang"]), "points"),
        (
            "Force a priori",
            int(a.favourites.set_index("team_id").loc[team_id, "rang_attendu"]),
            "effectif sur le papier",
        ),
        ("Mercato", int(a.mercato.set_index("team_id").loc[team_id, "rang"]), "score composite"),
        ("Niveau de jeu", rank(a.standings, "note_moy"), "note moyenne"),
        ("Chance", rank(a.luck, "indice_chance"), "1 = le plus chanceux"),
        ("Coaching", rank(a.coaching, "regret_moy", ascending=True), "moins de points sur le banc"),
        ("Fiabilité", rank(a.mercato, "disponibilite_ponderee"), "joueurs qui jouent en PL"),
        ("Attaque", rank(a.standings, "bp"), "buts marqués"),
        ("Défense", rank(a.standings, "bc", ascending=True), "buts encaissés"),
    ]


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    card = team_card(a, team_id)
    team = a.league.teams.set_index("team_id").loc[team_id]
    stand = a.standings.set_index("team_id").loc[team_id]
    hero(
        f"Fiche équipe, coach {team['coach']}",
        team["team_name"],
        f"Président {escape(str(team['president']))}, stade « {escape(str(team['stade']))} ». "
        f"Forme {form_badges(stand['forme'])}",
    )

    kpi_row(
        [
            {
                "label": "Classement",
                "value": f"{card['rang']}e",
                "sub": f"{card['pts']} pts, série {card['serie']}",
                "me": True,
            },
            {
                "label": "Budget payé",
                "value": fmt_m(card["budget_paye"]),
                "sub": f"valeur actuelle {fmt_m(card['valeur_actuelle'])} ({card['ratio_valeur_prix']:.0%}), "
                f"{fmt_pct(card['part_top3'])} sur les 3 plus gros achats",
            },
            {
                "label": "Niveau de l'effectif",
                "value": f"{card['note_reelle_mediane']:.1f}",
                "sub": f"note PL médiane, {card['note_mpg_moy']:.2f} en MPG",
            },
            {
                "label": "Fiabilité",
                "value": fmt_pct(card["disponibilite"]),
                "sub": f"taux de jeu PL pondéré, {card['indisponibles']} indisponible(s)",
            },
        ]
    )

    section(
        "Profil",
        "Rang de l'équipe dans chaque dimension, 1 = meilleur de la ligue. Vert : top 3, rouge : 3 derniers.",
    )
    st.html(_profile_panel(_profile(a, team_id), len(a.league.teams)))

    _bonus_section(a, team_id, meta)

    section("Match par match")
    charts.show(charts.gw_points(a.team_match, team_id))
    lines = a.lines.set_index("team_id").loc[team_id]
    st.caption(
        "Force par ligne (note brute) : "
        + ", ".join(f"{lab} {lines[g]:.2f}" for g, lab in [("G", "G"), ("D", "D"), ("M", "M"), ("A", "A")])
    )

    roster = a.player_value[a.player_value["team_id"] == team_id]
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

    section("Effectif")
    squad = _with_club_form(roster, a.league.club_results)
    st.dataframe(
        squad.sort_values(["poste_groupe", "enchere"], ascending=[True, False])[
            [
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
        ],
        hide_index=True,
        column_config={
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
            "surpaiement_x": st.column_config.NumberColumn("× cote", format="%.2f"),
            "n_notes": st.column_config.NumberColumn("Notes", help="Matchs notés retenus pour la note estimée"),
            "note_moy": st.column_config.NumberColumn("Moy. brute", format="%.2f", help="Moyenne de ces notes"),
            "note_retrecie": st.column_config.NumberColumn(
                "Note estimée", format="%.2f", help="Note attendue quand il joue, tirée vers son poste"
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
        },
        height=table_height(len(roster)),
    )
    how(["residu_valeur", "fiabilite"], meta)


def _bonus_cell(r) -> str:
    total = max(r.dotation, r.utilises)
    dots = "".join(f'<span class="dot {"on" if i < r.restants else "off"}"></span>' for i in range(total))
    if r.utilises:
        detail = f"Utilisé : {escape(r.journees)}"
        if r.cibles and r.cibles != "—":
            detail += f", {escape(r.cibles)}"
    else:
        detail = "Pas encore utilisé"
    warn = '<div class="sub warn">Absent de la dotation</div>' if r.hors_dotation else ""
    return (
        f'<div class="stat{" empty" if r.restants <= 0 else ""}" role="group" '
        f'aria-label="{escape(r.bonus)} : {r.restants} restant(s) sur {r.dotation}">'
        f'<div class="label">{escape(r.bonus)}</div>'
        f'<div class="value">{max(r.restants, 0)}<span class="of">/{r.dotation}</span></div>'
        f'<div class="dots" aria-hidden="true">{dots}</div><div class="sub">{detail}</div>{warn}</div>'
    )


def _profile_panel(prof: list[tuple[str, int, str]], n: int) -> str:
    rungs = []
    for label, r, hint in prof:
        tone = rank_tone(r, n)
        track = "".join(f'<i style="background:{tone}"></i>' if i == r else "<i></i>" for i in range(1, n + 1))
        rungs.append(
            f'<div class="rung" role="group" aria-label="{escape(label)} : {r}e sur {n}">'
            f'<div><div class="name">{escape(label)}</div><div class="hint">{escape(hint)}</div></div>'
            f'<div class="rank" style="color:{tone}">{r}<span>/{n}</span></div>'
            f'<div class="track" aria-hidden="true">{track}</div></div>'
        )
    return f'<div class="panel"><div class="ladder">{"".join(rungs)}</div></div>'


def _bonus_section(a: Analysis, team_id: int, meta: dict) -> None:
    br = a.bonus_remaining
    section("Bonus restants")
    if br is None:
        st.info(
            "Ajoutez un fichier `data/bonus_stock.csv` (colonnes `bonus`, `quantite`) avec la dotation de début "
            "de saison pour suivre les bonus restants."
        )
        return
    mine = br[br["team_id"] == team_id]
    left_total = int(mine["restants"].clip(lower=0).sum())
    total = int(mine["dotation"].sum())
    remaining_gw = a.league.n_gw - a.league.last_gw
    league_left = br.groupby("team_id")["restants"].apply(lambda s: s.clip(lower=0).sum())
    rank = int(league_left.rank(ascending=False, method="min").loc[team_id])
    st.caption(
        f"{left_total} bonus restants sur {total} pour {remaining_gw} journées à jouer, "
        f"{rank}e réserve de la ligue (médiane : {league_left.median():.0f}). Capitaine et bonus défensifs ne sont pas "
        "comptés : ils ne s'épuisent pas."
    )
    if (mine["restants"] < 0).any():
        st.warning(
            "Certains bonus ont été utilisés plus souvent que la dotation ne le permet : vérifiez "
            "`data/bonus_stock.csv`."
        )
    st.html(stat_grid([_bonus_cell(r) for r in mine.itertuples()], per_row=4))

    with st.expander("Bonus restants de toutes les équipes"):
        pivot = br.pivot(index="team_id", columns="bonus", values="restants")
        pivot = pivot[[b for b in dict.fromkeys(br["bonus"]) if b in pivot.columns]]
        pivot.insert(0, "Total", pivot.clip(lower=0).sum(axis=1))
        pivot.insert(0, "Équipe", pivot.index.map(a.league.team_names))
        st.dataframe(
            pivot.sort_values("Total", ascending=False),
            hide_index=True,
            column_config={
                "Total": st.column_config.ProgressColumn("Total", min_value=0, max_value=total, format="%d")
            },
        )
        st.caption("Utile pour anticiper : un adversaire qui a encore son Suarez peut viser votre gardien.")
    how("bonus_restants", meta)
