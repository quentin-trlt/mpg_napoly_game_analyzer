from html import escape

import streamlit as st

from app import charts
from app.components import fmt_m, fmt_pct, form_badges, hero, how, kpi_row, section
from mpg.analysis import Analysis, team_card


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
        f"Fiche équipe · coach {team['coach']}",
        team["team_name"],
        f"Président {escape(str(team['president']))} · stade « {escape(str(team['stade']))} » · "
        f"forme {form_badges(stand['forme'])}",
    )

    kpi_row(
        [
            {"label": "Classement", "value": f"{card['rang']}e", "sub": f"{card['pts']} pts · série {card['serie']}"},
            {
                "label": "Budget payé",
                "value": fmt_m(card["budget_paye"]),
                "sub": f"rang mercato {card['rang_mercato']}e",
            },
            {
                "label": "Valeur actuelle",
                "value": fmt_m(card["valeur_actuelle"]),
                "sub": f"{card['ratio_valeur_prix']:.0%} du prix payé (somme des cotes)",
            },
            {"label": "Part des 3 plus gros achats", "value": fmt_pct(card["part_top3"]), "sub": "du budget dépensé"},
            {
                "label": "Niveau de l'effectif",
                "value": f"{card['note_reelle_mediane']:.1f}",
                "sub": f"note PL médiane · {card['note_mpg_moy']:.2f} en MPG",
            },
            {
                "label": "Fiabilité",
                "value": fmt_pct(card["disponibilite"]),
                "sub": f"taux de jeu PL pondéré · {card['indisponibles']} indisponible(s)",
            },
        ]
    )

    section("Profil", "Rang de l'équipe dans chaque dimension (1 = meilleur de la ligue).")
    prof = _profile(a, team_id)
    n = len(a.league.teams)
    cols = [c for row in (prof[:5], prof[5:]) for c in st.columns(5)[: len(row)]]
    for col, (label, r, sub) in zip(cols, prof):
        tone = "#0CA30C" if r <= 3 else "#D03B3B" if r > n - 3 else "#94A3B8"
        with col:
            st.html(
                f'<div class="kpi" style="min-height:96px"><div class="label">{label}</div>'
                f'<div class="value" style="color:{tone}">{r}<span style="font-size:.9rem;color:#7C8AA0">/{n}</span>'
                f'</div><div class="sub">{sub}</div></div>'
            )
    st.caption("Vert : top 3 · rouge : 3 derniers. Le rang est toujours écrit, la couleur n'est qu'un repère.")

    _bonus_section(a, team_id, meta)

    roster = a.player_value[a.player_value["team_id"] == team_id]
    left, right = st.columns([1, 1.1], gap="medium")
    with left:
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
    with right:
        charts.show(charts.gw_points(a.team_match, team_id))
        lines = a.lines.set_index("team_id").loc[team_id]
        st.caption(
            "Force par ligne (note brute) : "
            + " · ".join(f"{lab} {lines[g]:.2f}" for g, lab in [("G", "G"), ("D", "D"), ("M", "M"), ("A", "A")])
        )

    section("Effectif")
    st.dataframe(
        roster.sort_values(["poste_groupe", "enchere"], ascending=[True, False])[
            [
                "joueur",
                "poste",
                "club",
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
            "enchere": st.column_config.NumberColumn("Prix", format="%d M€"),
            "cote": st.column_config.NumberColumn("Cote", format="%d M€"),
            "surpaiement_x": st.column_config.NumberColumn("× cote", format="%.2f"),
            "n_notes": "Notes",
            "note_moy": st.column_config.NumberColumn("Moy. MPG", format="%.2f"),
            "note_retrecie": st.column_config.NumberColumn("Note rétrécie", format="%.2f"),
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
        height=38 * (len(roster) + 1) + 2,
    )
    how(["residu_valeur", "fiabilite"], meta)


def _bonus_tile(r) -> str:
    total = max(r.dotation, r.utilises)
    dots = "".join(f'<span class="dot {"on" if i < r.restants else "off"}"></span>' for i in range(total))
    if r.utilises:
        detail = f"Utilisé : {escape(r.journees)}"
        if r.cibles and r.cibles != "—":
            detail += f" · {escape(r.cibles)}"
    else:
        detail = "Pas encore utilisé"
    warn = '<div class="sub" style="color:#FAB219">Absent de la dotation</div>' if r.hors_dotation else ""
    return (
        f'<div class="kpi bonus{" empty" if r.restants <= 0 else ""}" role="group" '
        f'aria-label="{escape(r.bonus)} : {r.restants} restant(s) sur {r.dotation}">'
        f'<div class="label">{escape(r.bonus)}</div>'
        f'<div class="value">{max(r.restants, 0)}<span class="of">/{r.dotation}</span></div>'
        f'<div class="dots" aria-hidden="true">{dots}</div><div class="sub">{detail}</div>{warn}</div>'
    )


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
        f"{left_total} bonus restants sur {total} pour {remaining_gw} journées à jouer · "
        f"{rank}e réserve de la ligue (médiane : {league_left.median():.0f}). Capitaine et bonus défensifs ne sont pas "
        "comptés : ils ne s'épuisent pas."
    )
    if (mine["restants"] < 0).any():
        st.warning(
            "Certains bonus ont été utilisés plus souvent que la dotation ne le permet : vérifiez "
            "`data/bonus_stock.csv`."
        )
    tiles = list(mine.itertuples())
    for start in range(0, len(tiles), 4):
        cols = st.columns(4)
        for col, r in zip(cols, tiles[start : start + 4]):
            with col:
                st.html(_bonus_tile(r))

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
