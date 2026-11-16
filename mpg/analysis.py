from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mpg import coaching, luck, mercato, players, standings, strength
from mpg.facts import line_ratings, lineups_enriched, team_match
from mpg.loader import DEFAULT_DATA_DIR, League, load_league
from mpg.stats import spearman


@dataclass
class Analysis:
    league: League
    lineups: pd.DataFrame
    team_match: pd.DataFrame
    standings: pd.DataFrame
    standings_by_gw: pd.DataFrame
    favourites: pd.DataFrame
    correlations: dict
    luck: pd.DataFrame
    coaching: pd.DataFrame
    optimal_lineups: pd.DataFrame
    captains: pd.DataFrame
    bonus_usage: pd.DataFrame
    substitutions: pd.DataFrame
    formations: pd.DataFrame
    player_stats: pd.DataFrame
    player_value: pd.DataFrame
    mercato: pd.DataFrame
    mercato_scenarios: pd.DataFrame
    clubs: pd.DataFrame
    remaining: pd.DataFrame
    bonus_remaining: pd.DataFrame | None
    next_fixtures: pd.DataFrame
    lines: pd.DataFrame
    strength_scenarios: pd.DataFrame
    strength_scenarios_fit: pd.DataFrame
    feature_set: pd.DataFrame
    meta: dict = field(default_factory=dict)


def run(data_dir: Path | str = DEFAULT_DATA_DIR, n_sim: int = 10_000, seed: int = 0) -> Analysis:
    league = load_league(data_dir)
    lu = lineups_enriched(league)
    tm = team_match(league)
    table = standings.standings_full(tm, league.teams)
    fav = strength.favourites_vs_reality(league, tm, table)
    lk = luck.luck_table(tm, fav, n_sim=n_sim, seed=seed)
    ps = players.player_stats(league, lu)
    pv = mercato.player_value(ps)
    merc, scen = mercato.mercato_ranking(pv, fav.set_index("team_id")["cote_banc"])
    names = league.team_names
    scen_ranks, scen_fit = strength.strength_scenarios(fav, fav.set_index("team_id")["pts"])
    scen_ranks.insert(1, "team_name", scen_ranks["team_id"].map(names))
    lines = line_ratings(lu).assign(team_name=lambda d: d["team_id"].map(names))
    coach = coaching.coaching_table(lu, tm, league.bonus, league.substitutions)
    absents = coach.set_index("team_id")["absents_total"]
    corr_fiab = spearman(merc.set_index("team_id")["disponibilite_ponderee"], absents)
    corr_abs = spearman(coach.set_index("team_id")["absents_attendus"], absents)
    app = players.player_appearances(lu).merge(
        league.players[["player_key", "note_moy_reelle", "points_mpg_moy"]], on="player_key"
    )
    rmse = {c: float(((app["note_brute"] - app[c]) ** 2).mean() ** 0.5) for c in ("note_moy_reelle", "points_mpg_moy")}
    merc["team_name"] = merc["team_id"].map(names)
    scen.insert(1, "team_name", scen["team_id"].map(names))
    lk.insert(1, "team_name", lk["team_id"].map(names))

    return Analysis(
        league=league,
        lineups=lu,
        team_match=tm,
        standings=table,
        standings_by_gw=standings.standings_by_gw(tm),
        favourites=fav,
        correlations=strength.strength_correlations(fav),
        luck=lk,
        coaching=coach,
        optimal_lineups=coaching.optimal_lineups(lu, tm).assign(team_name=lambda d: d["team_id"].map(names)),
        captains=coaching.captain_report(lu, league.bonus).assign(team_name=lambda d: d["team_id"].map(names)),
        bonus_usage=coaching.bonus_usage(league.bonus, tm),
        substitutions=coaching.substitution_report(league.substitutions).assign(
            team_name=lambda d: d["team_id"].map(names)
        ),
        formations=coaching.formation_report(tm),
        player_stats=ps,
        player_value=pv,
        mercato=merc,
        mercato_scenarios=scen,
        clubs=mercato.club_exposure(league.players),
        remaining=strength.remaining_schedule(league, fav),
        bonus_remaining=coaching.remaining_bonuses(league.bonus, league.bonus_stock, sorted(names))
        if league.bonus_stock is not None
        else None,
        next_fixtures=standings.next_fixtures(league.fixtures, table, league.teams),
        lines=lines,
        strength_scenarios=scen_ranks,
        strength_scenarios_fit=scen_fit,
        feature_set=fav,
        meta={
            "derniere_journee": league.last_gw,
            "nb_journees": league.n_gw,
            "matchs_joues": len(league.played),
            "bande_nul": lk.attrs["bande_nul"],
            "concordance_regle_note": lk.attrs["concordance"],
            "k_shrinkage": ps.attrs["k_shrinkage"],
            "k_postes": ", ".join(f"{g} {k:.0f}" for g, k in ps.attrs["k_postes"].items())
            if ps.attrs.get("k_postes")
            else None,
            "n_sim": n_sim,
            "prix": strength.price_column(league.players),
            "corr_fiabilite_absents": f"corrélation avec les absences MPG {corr_fiab}",
            "corr_absents_attendus": f"corrélation entre absences attendues et réelles {corr_abs}",
            "rmse_note_reelle": rmse["note_moy_reelle"],
            "rmse_points_mpg": rmse["points_mpg_moy"],
        },
    )


def _ties(df: pd.DataFrame, col: str, label: str) -> tuple[list[str], float]:
    values = df[col].dropna()
    if values.empty:
        raise ValueError(f"Aucune valeur renseignée dans la colonne {col!r}")
    best = values.max()
    return df.loc[df[col] == best, label].tolist(), float(best)


def _league_scorers(league: League) -> pd.DataFrame:
    """Buts marqués par joueur dans les matchs MPG (buts réels et accordés par MPG, hors buts bloqués)."""
    goals = league.scored_goals
    goals = goals[goals["type_but"].isin(["reel", "mpg"])]
    goals = goals.assign(key=goals["player_key"].fillna(goals["buteur_affiche"]))
    names = league.players.set_index("player_key")["joueur"]
    counts = goals.groupby("key").agg(buts=("key", "size"), affiche=("buteur_affiche", "first")).reset_index()
    counts["joueur"] = counts["key"].map(names).fillna(counts["affiche"])
    return counts


def key_figures(a: Analysis) -> dict[str, dict | None]:
    """Chiffres clés de la ligue. Les ex aequo sont tous renvoyés.

    `buteur_pl` vaut `None` quand les buts de Premier League ne sont pas renseignés (saison passée).
    """
    st = a.standings
    leader = st.iloc[0]
    ps = a.player_stats
    mpg_names, mpg_goals = _ties(_league_scorers(a.league), "buts", "joueur")
    rot_names, rot_n = _ties(st, "rotaldos", "team_name")
    buteur_pl = None
    if ps["buts_reels_saison"].notna().any():
        pl_names, pl_goals = _ties(ps, "buts_reels_saison", "joueur")
        buteur_pl = {
            "joueurs": pl_names,
            "buts": int(pl_goals),
            "equipes": ps.loc[ps["joueur"].isin(pl_names), "team_name"].tolist(),
        }
    return {
        "leader": {
            "equipe": leader["team_name"],
            "coach": leader["coach"],
            "pts": int(leader["pts"]),
            "ecart_2e": int(leader["pts"] - st.iloc[1]["pts"]) if len(st) > 1 else 0,
        },
        "buteur_pl": buteur_pl,
        "buteur_mpg": {"joueurs": mpg_names, "buts": int(mpg_goals)},
        "roi_rotaldos": {"equipes": rot_names, "rotaldos": int(rot_n)},
    }


def team_card(a: Analysis, team_id: int) -> dict[str, float | int | str | None]:
    """Tuiles d'une équipe : rang, budget payé, valeur actuelle, concentration, niveau de l'effectif.

    Une donnée absente vaut `None`, jamais un chiffre de remplacement. Sans cote MPG (saison passée, `meta["prix"]`
    vaut « enchere ») : `valeur_actuelle`, `valeur_effectif` et `ratio_valeur_prix`. Sans statistiques de Premier League
    (`buts_reels_saison` vide) : `note_reelle_mediane`, `disponibilite`, `indisponibles` et `ga_saison`. `rang_attendu`
    vaut `None` quand l'effectif de l'équipe est incomplet.
    """
    st = a.standings.set_index("team_id").loc[team_id]
    fav = a.favourites.set_index("team_id").loc[team_id]
    merc = a.mercato.set_index("team_id").loc[team_id]
    roster = a.player_stats[a.player_stats["team_id"] == team_id]
    has_cote = a.meta.get("prix", "cote") == "cote"
    has_pl_stats = a.league.players["buts_reels_saison"].notna().any()
    budget = float(merc["enchere_totale"])
    return {
        "rang": int(st["rang"]),
        "pts": int(st["pts"]),
        "serie": st["serie"],
        "budget_paye": budget,
        "valeur_actuelle": float(fav["total_cote"]) if has_cote else None,
        "valeur_effectif": float(fav["valeur_effectif_meur"]) if has_cote else None,
        "ratio_valeur_prix": float(fav["total_cote"] / budget) if has_cote else None,
        "part_top3": float(merc["part_top3"]),
        "note_reelle_mediane": float(roster["note_moy_reelle"].median()) if has_pl_stats else None,
        "note_mpg_moy": float(st["note_moy"]),
        "disponibilite": float(merc["disponibilite_ponderee"]) if has_pl_stats else None,
        "indisponibles": int(merc["nb_indisponibles"]) if has_pl_stats else None,
        "ga_saison": float(merc["ga_saison"]) if has_pl_stats else None,
        "rang_attendu": None if bool(fav.get("effectif_incomplet", False)) else int(fav["rang_attendu"]),
        "rang_mercato": int(merc["rang"]),
    }
