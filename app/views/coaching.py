import pandas as pd
import streamlit as st

from app import charts
from app.components import as_pct, callout, how, kpi_row, pct_column, section, short_table, table_height, volet_title
from mpg.analysis import Analysis
from mpg.coaching import bonus_effect


def _replay_sentence(replayed: pd.DataFrame, skipped: int) -> str:
    """Points gagnés ou perdus si l'équipe avait aligné son meilleur 11, sur les matchs rejoués."""
    gain, real, best = (int(x) for x in (replayed["gain_pts"].sum(), replayed["pts"].sum(), replayed["pts_opt"].sum()))
    unit = "point" if abs(gain) == 1 else "points"
    if gain > 0:
        text = f"Avec ton meilleur 11 à chaque match, tu aurais {gain} {unit} de plus ({best} au lieu de {real})."
    elif gain < 0:
        text = f"Avec ton meilleur 11 à chaque match, tu aurais {-gain} {unit} de moins ({best} au lieu de {real})."
    else:
        text = f"Avec ton meilleur 11 à chaque match, tu aurais le même nombre de points ({real}) : le banc ne t'a rien coûté."
    played = f"{len(replayed)} match{'s' if len(replayed) > 1 else ''} rejoué{'s' if len(replayed) > 1 else ''}"
    suffix = f" {played}" + (f", {skipped} non rejoué{'s' if skipped > 1 else ''}." if skipped else ".")
    return text + suffix


def render(a: Analysis, team_id: int) -> None:
    meta = a.meta
    stats_pl = meta["capacites"].stats_pl
    co = a.coaching
    volet_title(
        "Qui compose le mieux ses équipes ?",
        "Points laissés sur le banc, titulaires absents, capitaines et bonus : ce que le coach contrôle, et ce qu'il ne "
        "contrôle pas.",
    )

    best = co.sort_values("regret_moy").iloc[0]
    worst = co.sort_values("regret_moy").iloc[-1]
    me = co.set_index("team_id").loc[team_id]
    kpi_row(
        [
            {
                "label": "Meilleur sélectionneur",
                "value": best["team_name"],
                "small": True,
                "sub": f"{best['regret_moy']:.1f} pts de note laissés sur le banc par match",
            },
            {
                "label": "Banc le plus gâché",
                "value": worst["team_name"],
                "small": True,
                "sub": f"{worst['regret_moy']:.1f} pts de note par match",
            },
            {
                "label": me["team_name"],
                "value": f"{me['regret_moy']:.1f} pts/match",
                "sub": f"{int(me['absents_total'])} absents"
                + (f" ({me['absents_attendus']:.1f} attendus)" if stats_pl else "")
                + f", {int(me['capitaines_manques'])} capitaine(s) manqué(s)",
                "me": True,
            },
        ]
    )

    if (a.league.bonus["bonus"] == "Chapron rouge").any():
        callout(
            "Cette saison, des bonus « Chapron rouge » ont été posés : il expulse un titulaire adverse, remplacé "
            "par un Rotaldo, et ce titulaire compte comme absent. Ces cas font monter les absents de l'équipe visée "
            "sans que son coach y soit pour quelque chose."
        )

    left, right = st.columns(2, gap="medium")
    with left:
        charts.show(
            charts.ranked_bars(
                co,
                "regret_moy",
                "team_name",
                team_id,
                "Points de note laissés sur le banc, par match",
                fmt=".1f",
                ascending=False,
                x_title="Somme des notes (11 optimal − 11 aligné)",
            ),
            height=440,
        )
        how("regret", meta)
    with right:
        if stats_pl:
            d = co.assign(absents_total=co["absents_total"].astype(float))
            fig = charts.dumbbell_ranks(
                d.rename(columns={"absents_attendus": "att", "absents_total": "reel"}),
                "att",
                "reel",
                "Absences attendues",
                "Absences réelles",
                team_id,
                "Titulaires absents : attendu et réel",
            )
            fig.update_xaxes(autorange=True, dtick=None, title="Nombre de titulaires absents")
            charts.show(fig)
            how(["absents_attendus", "absents"], meta)
        else:
            charts.show(
                charts.ranked_bars(
                    co.assign(absents_total=co["absents_total"].astype(float)),
                    "absents_total",
                    "team_name",
                    team_id,
                    "Titulaires absents sur la saison",
                    fmt=".0f",
                    ascending=False,
                    x_title="Nombre de titulaires absents",
                ),
                height=440,
            )
            st.caption(
                "Sans les statistiques de Premier League de cette saison, on ne peut pas estimer combien d'absences "
                "étaient attendues : seules les absences réelles sont affichées."
            )
            how("absents", meta)

    section(f"Le banc de {me['team_name']}, match par match")
    opt = a.optimal_lineups[a.optimal_lineups["team_id"] == team_id].merge(
        a.team_match[["match_id", "team_id", "gw", "opp_name", "resultat", "bp", "bc", "formation"]],
        on=["match_id", "team_id"],
    )
    opt = opt.merge(a.optimal_replay.drop(columns=["bp", "bc"]), on=["match_id", "team_id"], how="left")
    opt["score"] = opt["bp"].astype(str) + " – " + opt["bc"].astype(str)
    opt["meilleur_11"] = opt["bp_opt"].astype("Int64").astype(str) + " – " + opt["bc_opt"].astype("Int64").astype(str)
    opt["meilleur_11"] = opt["meilleur_11"].where(opt["bp_opt"].notna())
    opt["gain_pts"] = opt["pts_opt"] - opt["pts"]
    replayed = opt.dropna(subset=["pts_opt"])
    callout(_replay_sentence(replayed, len(opt) - len(replayed)))
    short_table(
        opt.sort_values("gw"),
        ["gw", "opp_name", "score", "meilleur_11", "regret"],
        full=[
            "gw",
            "opp_name",
            "resultat",
            "score",
            "meilleur_11",
            "gain_pts",
            "formation",
            "somme_notes_11",
            "somme_notes_optimal",
            "regret",
            "oublies_sur_banc",
        ],
        column_config={
            "gw": st.column_config.NumberColumn("J", format="J%d"),
            "opp_name": "Adversaire",
            "resultat": "Rés.",
            "score": "Score",
            "meilleur_11": st.column_config.TextColumn("Meilleur 11", help="Score rejoué avec le meilleur 11 possible"),
            "gain_pts": st.column_config.NumberColumn("Points gagnés", format="%+d", help="Points en plus ou en moins"),
            "formation": "Formation",
            "somme_notes_11": st.column_config.NumberColumn("Notes du 11", format="%.1f"),
            "somme_notes_optimal": st.column_config.NumberColumn("Notes du 11 optimal", format="%.1f"),
            "regret": st.column_config.NumberColumn("Sur le banc", format="%.1f", help="Notes laissées sur le banc"),
            "oublies_sur_banc": st.column_config.TextColumn("Auraient dû jouer", width="large"),
        },
        alt="Le banc de mon équipe, match par match",
    )
    st.caption(
        "Le meilleur 11 est rejoué avec la même formation, le même capitaine et les mêmes bonus que ceux que tu as "
        "posés. Les remplacements en cours de match ne sont pas rejoués. "
        "Quand le capitaine devrait sortir, le match n'est pas rejoué."
    )

    section("Capitaines")
    caps = a.captains
    cap_team = (
        caps.groupby("team_name")
        .agg(
            matchs=("capitaine_a_joue", "size"),
            capitaine_a_joue=("capitaine_a_joue", "sum"),
            ecart_equipe=("ecart_vs_equipe", "mean"),
            ecart_meilleur=("ecart_vs_meilleur", "mean"),
        )
        .reset_index()
    )
    cap_team["taux"] = cap_team["capitaine_a_joue"] / cap_team["matchs"]
    left, right = st.columns([1, 1.1], gap="medium")
    with left:
        st.dataframe(
            as_pct(cap_team.sort_values("ecart_equipe", ascending=False), ["taux"]),
            hide_index=True,
            alt="Capitaines, équipe par équipe",
            column_config={
                "team_name": "Équipe",
                "matchs": None,
                "capitaine_a_joue": None,
                "taux": pct_column("A joué", bar=True, help="Part des matchs où le capitaine a joué"),
                "ecart_equipe": st.column_config.NumberColumn(
                    "vs équipe", format="%+.2f", width="small", help="Écart à la note moyenne de l'équipe"
                ),
                "ecart_meilleur": st.column_config.NumberColumn(
                    "vs meilleur", format="%+.2f", width="small", help="Écart à la note du meilleur joueur"
                ),
            },
            column_order=["team_name", "taux", "ecart_equipe", "ecart_meilleur"],
            height=table_height(len(cap_team)),
        )
        how("capitaine", meta)
    with right:
        mine = (
            caps[caps["team_id"] == team_id]
            .assign(
                note_capitaine=lambda d: d["note_capitaine"].map(lambda v: "absent" if v != v else f"{v:.1f}"),
                cible_affiche=lambda d: d["cible_affiche"].fillna("non désigné"),
            )
            .merge(a.team_match[["match_id", "team_id", "gw"]], on=["match_id", "team_id"])
        )
        short_table(
            mine.sort_values("gw"),
            ["gw", "cible_affiche", "note_capitaine", "meilleur_choix", "note_meilleur_choix"],
            full=["gw", "cible_affiche", "note_capitaine", "meilleur_choix", "note_meilleur_choix", "capitaine_a_joue"],
            column_config={
                "gw": st.column_config.NumberColumn("J", format="J%d"),
                "cible_affiche": "Capitaine",
                "note_capitaine": st.column_config.TextColumn("Note"),
                "meilleur_choix": st.column_config.TextColumn("Meilleur", help="Le meilleur choix de capitaine"),
                "note_meilleur_choix": st.column_config.NumberColumn("Sa note", format="%.1f"),
                "capitaine_a_joue": st.column_config.CheckboxColumn("A joué"),
            },
            alt="Mes capitaines, match par match",
        )

    section("Bonus et remplacements")
    tab_bonus, tab_subs = st.tabs(["Bonus utilisés (hors capitaine)", "Remplacements tactiques"])
    with tab_bonus:
        bu = a.bonus_usage.merge(a.team_match[["match_id", "team_id", "team_name"]], on=["match_id", "team_id"])
        short_table(
            bu,
            ["team_name", "gw", "bonus", "effet", "cible_affiche"],
            full=["team_name", "gw", "bonus", "effet", "cible_affiche", "opp_name", "resultat"],
            column_config={
                "team_name": "Équipe",
                "gw": st.column_config.NumberColumn("J", format="J%d"),
                "bonus": "Bonus",
                "effet": "Effet",
                "cible_affiche": "Cible",
                "opp_name": "Adversaire",
                "resultat": "Résultat",
            },
            height=min(table_height(len(bu)), 388),
            alt="Bonus utilisés",
        )
        eff = bonus_effect(a.team_match)
        eff["avec_bonus"] = eff["avec_bonus"].map({True: "Avec bonus", False: "Sans bonus"})
        st.caption(
            "Points moyens avec et sans bonus : "
            + ", ".join(f"{r.avec_bonus.lower()} {r.pts_moy:.2f} pts ({r.matchs} matchs)" for r in eff.itertuples())
            + ". Descriptif seulement : les coachs posent un bonus quand ils en ont besoin."
        )
    with tab_subs:
        tac = a.substitutions[a.substitutions["type"] == "remplacement_tactique"]
        short_table(
            tac,
            ["team_name", "gw", "titulaire_sortant", "remplacant_entre", "gain_note"],
            full=[
                "team_name",
                "gw",
                "titulaire_sortant",
                "note_titulaire",
                "remplacant_entre",
                "note_remplacant",
                "gain_note",
            ],
            height=min(table_height(len(tac)), 388),
            column_config={
                "team_name": "Équipe",
                "gw": st.column_config.NumberColumn("J", format="J%d"),
                "titulaire_sortant": "Sortant",
                "note_titulaire": st.column_config.NumberColumn("Note du sortant", format="%.1f"),
                "remplacant_entre": "Entrant",
                "note_remplacant": st.column_config.NumberColumn("Note de l'entrant", format="%.1f"),
                "gain_note": st.column_config.NumberColumn("Gain", format="%+.1f"),
            },
            alt="Remplacements tactiques",
        )
        how("remplacements", meta)

    section("Formations")
    left, right = st.columns([1, 1.1], gap="medium")
    with left:
        short_table(
            a.formations,
            ["formation", "matchs", "pts_moy", "bp_moy", "bc_moy"],
            full=["formation", "matchs", "pts_moy", "bp_moy", "bc_moy", "note_moy"],
            column_config={
                "formation": "Formation",
                "matchs": "Matchs",
                "pts_moy": st.column_config.NumberColumn("Pts / match", format="%.2f"),
                "bp_moy": st.column_config.NumberColumn("BP / match", format="%.2f"),
                "bc_moy": st.column_config.NumberColumn("BC / match", format="%.2f"),
                "note_moy": st.column_config.NumberColumn("Note moy.", format="%.2f"),
            },
            alt="Résultats par formation",
        )
        st.caption("Peu de matchs par formation : ces moyennes sont indicatives.")
    with right:
        st.dataframe(
            co[["team_name", "formations", "bonus_utilises", "remplacements_tactiques", "gain_tactique_total"]],
            hide_index=True,
            column_config={
                "team_name": "Équipe",
                "formations": st.column_config.TextColumn("Formations utilisées", width="medium"),
                "bonus_utilises": st.column_config.NumberColumn("Bonus", width="small", help="Bonus posés"),
                "remplacements_tactiques": st.column_config.NumberColumn(
                    "Rempl.", width="small", help="Remplacements tactiques"
                ),
                "gain_tactique_total": st.column_config.NumberColumn(
                    "Gain", format="%+.1f", width="small", help="Gain de note total des remplacements tactiques"
                ),
            },
            alt="Choix tactiques, équipe par équipe",
        )
