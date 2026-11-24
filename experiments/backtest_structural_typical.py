"""Banc d'essai : le modèle structurel de l'app prédit-il mieux avec le 11 type qu'avec le 11 des meilleures notes ?

Rejoue `mpg.forecast.evaluation.backtest` sur les trois saisons, deux fois avec les mêmes tirages. La variante « 11
type » ne change que le contexte vu par le structurel : formation la plus utilisée pondérée (`mpg.coach.typical`,
demi-vie 0,25) au lieu de la plus fréquente, et candidats de chaque poste classés par habitude (part de
titularisations + moitié de la part de banc), la note espérée ne départageant que les égalités. La disponibilité
reste tirée au sort par le modèle (taux de jeu, blessures) : un habitué absent laisse sa place au suivant.

Usage : uv run python -m experiments.backtest_structural_typical
"""

import dataclasses
import logging
from types import SimpleNamespace

import pandas as pd

from mpg.analysis import run
from mpg.coach.typical import BENCH_WEIGHT, usage
from mpg.forecast.evaluation import _played_outcomes, paired_delta, scores, season_dirs
from mpg.forecast.models import StructuralModel
from mpg.forecast.season import build_context, ensemble_draws, fixtures_after

N_DRAWS = 1500
HABIT_SCALE = 100.0
KEYS = ["gw", "home_team_id", "away_team_id"]
MODELS = (StructuralModel.name, "Ensemble")


def typical_context(ctx, gw: int):
    """Contexte où le structurel aligne le 11 type : `note_esperee` ne sert qu'à classer les candidats."""
    if "note_titulaire" not in ctx.players:
        raise ValueError("variante limitée au structurel avec player_match_notes.csv (note_esperee = classement)")
    history = SimpleNamespace(team_match=ctx.tm, lineups=ctx.lineups)
    players, tm = ctx.players.copy(), ctx.tm.copy()
    for t in ctx.team_ids:
        use = usage(history, t, gw)
        if use.formation is not None:
            tm.loc[tm["team_id"] == t, "formation"] = use.formation
        rows = players["team_id"] == t
        habit = players.loc[rows, "player_key"].map(use.share["titulaire"] + BENCH_WEIGHT * use.share["banc"])
        players.loc[rows, "note_esperee"] += HABIT_SCALE * habit.fillna(0.0)
    return dataclasses.replace(ctx, players=players, tm=tm)


def season_rows(name: str, path) -> list[pd.DataFrame]:
    a = run(path, n_sim=50)
    played = a.league.played
    out = []
    for g in sorted(played["gw"].unique()):
        ctx = build_context(a, int(g) - 1)
        remaining = fixtures_after(a, int(g) - 1)
        sel = (remaining["gw"] == g).to_numpy()
        fx = remaining[sel][KEYS].merge(played[[*KEYS, "match_id", "home_goals", "away_goals"]], on=KEYS)
        outcome = _played_outcomes(fx)
        for variant, c in (("meilleures notes (actuel)", ctx), ("11 type", typical_context(ctx, int(g)))):
            draws = ensemble_draws(c, remaining, n_draws=N_DRAWS, seed=0)
            probs = {StructuralModel.name: draws.by_model[StructuralModel.name][:, sel].mean(axis=0)}
            probs["Ensemble"] = draws.ensemble[:, sel].mean(axis=0)
            for model, p in probs.items():
                out.append(
                    scores(p, outcome).assign(
                        modele=f"{model}, {variant}", saison=name, gw=int(g), match_id=fx["match_id"].to_numpy()
                    )
                )
        logging.warning("%s J%d", name, g)
    return out


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    pd.set_option("display.width", 200)
    bt = pd.concat([r for name, path in season_dirs().items() for r in season_rows(name, path)], ignore_index=True)
    print(f"\n=== {bt['match_id'].nunique()} matchs, saisons {', '.join(bt['saison'].unique())} ===")
    print(
        bt.pivot_table(index="modele", columns="saison", values="rps")
        .assign(tout=bt.groupby("modele")["rps"].mean())
        .round(4)
    )
    for model in MODELS:
        for metric in ("rps", "log_loss"):
            d = paired_delta(bt, f"{model}, 11 type", f"{model}, meilleures notes (actuel)", metric=metric)
            print(f"{model:24s} Δ {metric:8s} 11 type − actuel : {d[0]:+.4f} [IC 90 % {d[1]:+.4f} ; {d[2]:+.4f}]")
    late = bt[bt["gw"] >= 4]
    for model in MODELS:
        d = paired_delta(late, f"{model}, 11 type", f"{model}, meilleures notes (actuel)")
        print(f"{model:24s} Δ rps J4 et suivantes : {d[0]:+.4f} [IC 90 % {d[1]:+.4f} ; {d[2]:+.4f}]")


if __name__ == "__main__":
    main()
