"""Banc d'essai : face à quelle compo adverse le coach prédit-il le mieux le match, l'optimale ou la compo type ?

Chaque journée MPG g ≥ 2 de chaque saison est rejouée avec ce qui était connu avant elle (`backtest_engine.snapshot` ;
sans FPL pour les saisons passées). Pour chaque match et chaque camp (« moi »), ma compo est celle réellement posée,
et celle de l'adversaire est prédite de plusieurs façons :
- optimale : ce que fait le coach aujourd'hui, compo optimisée par le moteur contre mon 11 naïf, tactiques comprises ;
- type : `mpg.coach.typical`, pour plusieurs demi-vies de la pondération des journées ;
- réaliste : formation habituelle et meilleurs joueurs par contribution espérée, sans les habitudes de l'équipe.
On compte les titulaires réels de l'adversaire que chaque prédiction retrouve, puis on mesure le RPS du résultat
simulé (ma vraie compo contre la prédiction), à côté de celui des deux vraies compos (borne basse du RPS).

Usage : uv run python -m experiments.backtest_opponent
"""

import logging
import time

import numpy as np
import pandas as pd

from experiments.backtest_engine import (
    SEED,
    _usual_formation,
    actual_lineup,
    paired_bootstrap,
    realistic_lineup,
    snapshot,
)
from mpg.analysis import run
from mpg.coach import optimizer as op
from mpg.coach import projection as pr
from mpg.coach.rules import FORMATIONS, simulate
from mpg.coach.typical import typical_lineup, usage
from mpg.forecast.evaluation import scores, season_dirs
from mpg.forecast.models import RESULT_TO_IDX
from mpg.loader import COACH_PICKS
from mpg.playing_time import split_history

N_DRAWS = 2000
HALF_LIVES = (0.25, 1.0, 4.0, float("inf"))
OPTIMAL = "Optimale (coach actuel)"
REAL = "Vraie compo (référence)"

log = logging.getLogger(__name__)


def match_cases(snap, fx: pd.DataFrame, full, season: str) -> list[dict]:
    lu_all = full.lineups
    out = []
    for i, m in enumerate(fx.itertuples()):
        h, w = int(m.home_team_id), int(m.away_team_id)
        proj = snap.proj[snap.proj["team_id"].isin([h, w])].reset_index(drop=True)
        d = pr.sample_draws(proj, snap.model, N_DRAWS, seed=SEED + 97 * snap.gw + i)
        hold = pr.sample_draws(proj, snap.model, N_DRAWS, seed=SEED + 10_000 + 97 * snap.gw + i)
        index = {k: j for j, k in enumerate(proj["player_key"])}
        rows = {t: [index[k] for k in proj.loc[proj["team_id"] == t, "player_key"]] for t in (h, w)}
        contrib = op.contribution(d)
        forms = {h: m.home_formation, w: m.away_formation}
        real = {t: actual_lineup(full, m.match_id, t, forms[t], d, index) for t in (h, w)}
        for me, opp in ((h, w), (w, h)):
            if real[me] is None:
                continue
            opp_home = opp == h
            # les effectifs des saisons passées sont ceux de fin de saison : un poste peut manquer à mi-saison
            try:
                naive = max(
                    (lu for f in FORMATIONS if (lu := op.initial_lineup(rows[me], d, f, contrib)) is not None),
                    key=lambda lu: float(contrib[list(lu.starters)].sum()),
                )
                optimal = op.optimise(rows[opp], op.Evaluator(d, naive, home=opp_home))[0]
                preds = {
                    OPTIMAL: op.prune_tactics(optimal, op.Evaluator(hold, naive, home=opp_home)),
                    "Réaliste (sans habitudes)": realistic_lineup(
                        rows[opp], d, contrib, _usual_formation(snap.a, opp, snap.gw)
                    ),
                }
                for hl in HALF_LIVES:
                    preds[f"Type, demi-vie {hl:g}"] = typical_lineup(rows[opp], d, usage(snap.a, opp, snap.gw, hl))
            except ValueError as exc:
                log.warning("%s J%d %s, camp %d écarté : %s", season, snap.gw, m.match_id, me, exc)
                continue
            if real[opp] is not None:
                preds[REAL] = real[opp]

            sheet = lu_all[(lu_all["match_id"] == m.match_id) & (lu_all["team_id"] == opp)]
            picks = sheet[sheet["statut"].isin(COACH_PICKS) & sheet["player_key"].notna()]
            xi = set(picks["player_key"])
            cap = set(picks.loc[picks["capitaine"] == 1, "player_key"])
            for name, lu in preds.items():
                res = simulate(real[me], lu, hold) if me == h else simulate(lu, real[me], hold)
                out.append(
                    {
                        "saison": season,
                        "gw": snap.gw,
                        "match_id": m.match_id,
                        "prediction": name,
                        "titulaires_trouves": len({d.keys[r] for r in lu.starters} & xi),
                        "formation_ok": lu.formation == forms[opp],
                        "capitaine_ok": lu.captain is not None and d.keys[lu.captain] in cap,
                        "p_dom": res.outcome_probs()[0],
                        "p_nul": res.outcome_probs()[1],
                        "p_ext": res.outcome_probs()[2],
                        "issue": RESULT_TO_IDX[m.resultat_dom],
                    }
                )
    return out


def season_cases(name: str, path) -> list[dict]:
    a = run(path, n_sim=50)
    lg = a.league
    mapping, hist = None, {}
    if lg.fpl_players is not None and lg.fpl_history is not None:
        mapping, hist = lg.fpl_players[["player_key", "element_id"]], split_history(lg.fpl_history)
    played = lg.played.sort_values(["gw", "match_id"])
    out = []
    for g in sorted(played["gw"].unique()):
        if g < 2:
            continue
        t0 = time.perf_counter()
        snap = snapshot(a, int(g), mapping, hist)
        fx = played[played["gw"] == g].reset_index(drop=True)
        out += match_cases(snap, fx, a, name)
        log.warning("%s J%d : %d matchs en %.0f s", name, g, len(fx), time.perf_counter() - t0)
    return out


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    pd.set_option("display.width", 200)
    cases = pd.DataFrame([c for name, path in season_dirs().items() for c in season_cases(name, path)])
    cases["rps"] = scores(cases[["p_dom", "p_nul", "p_ext"]].to_numpy(), cases["issue"].to_numpy())["rps"].to_numpy()

    # chaque match compte deux fois (un cas par camp) : moyenne par match avant le bootstrap
    by_match = cases.pivot_table(index="match_id", columns="prediction", values="rps", aggfunc="mean")
    rng = np.random.default_rng(SEED)
    table = []
    for name, grp in cases.groupby("prediction"):
        both = by_match[[name, OPTIMAL]].dropna()
        diff = paired_bootstrap((both[name] - both[OPTIMAL]).to_numpy(), rng)
        table.append(
            {
                "prédiction de l'adversaire": name,
                "cas": len(grp),
                "titulaires retrouvés /11": grp["titulaires_trouves"].mean(),
                "formation juste": grp["formation_ok"].mean(),
                "capitaine juste": grp["capitaine_ok"].mean(),
                "RPS": grp["rps"].mean(),
                "Δ RPS vs optimale [IC 90 %]": f"{diff[0]:+.4f} [{diff[1]:+.4f} ; {diff[2]:+.4f}]",
            }
        )
    n_matches = cases["match_id"].nunique()
    print(f"\n=== {n_matches} matchs, J2 et suivantes, saisons {', '.join(cases['saison'].unique())} ===")
    print(pd.DataFrame(table).sort_values("RPS").round(3).to_string(index=False))
    print("\n=== RPS par saison ===")
    print(cases.pivot_table(index="prediction", columns="saison", values="rps").round(3).to_string())


if __name__ == "__main__":
    main()
