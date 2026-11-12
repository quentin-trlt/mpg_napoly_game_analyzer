"""Banc d'essai : les briques du coach améliorent-elles les prédictions de l'app principale ?

Chaque journée MPG g est rejouée avec ce qui était connu avant elle : notes MPG des journées < g, historique FPL
des journées PL < r (r = journée PL de g), résultats de PL avant le premier coup d'envoi de r. Les statuts de
blessure du jour et `chance_of_playing_next_round` sont exclus (non archivés). Restent deux fuites, communes à
toutes les variantes : la note moyenne PL de la saison (a priori des notes rétrécies) et, pour Elo et le Poisson
de référence, l'indice de force calculé sur les effectifs du jour.

Usage : uv run python -m experiments.backtest_engine
"""

import dataclasses
import logging

import numpy as np
import pandas as pd

from mpg import fpl
from mpg import players as mplayers
from mpg import playing_time as pt
from mpg.analysis import Analysis, run
from mpg.coach import optimizer as op
from mpg.coach import projection as pr
from mpg.coach.rules import BENCH_SIZE, FORMATIONS, Lineup, simulate, slots_of
from mpg.forecast.evaluation import backtest, scores
from mpg.forecast.models import RESULT_TO_IDX, OrderedLogit, StructuralModel
from mpg.forecast.season import build_context
from mpg.loader import COACH_PICKS
from mpg.premier_league import pl_gw_for

N_DRAWS = 3000
N_BOOT = 10_000
SEED = 0
PRIOR_MODEL = pr.NoteModel(
    sigma_player=0.75,
    sigma_club=0.5,
    goal_bump=1.2,
    own_goal_rate=0.005,
    beta_for={},
    beta_against={},
    goals_mean=1.3,
    k_shrink=5.0,
)

log = logging.getLogger(__name__)


@dataclasses.dataclass
class Snapshot:
    gw: int
    pl_gw: int
    a: Analysis
    fpl_players: pd.DataFrame
    history: dict[int, pd.DataFrame]
    model: pr.NoteModel
    strength: pr.ClubStrength
    play_model: pt.PlayModel | None
    proj: pd.DataFrame


def load_fpl(a: Analysis) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    client = fpl.FplClient()
    els = fpl.elements(client.bootstrap())
    mapping = fpl.match_players(a.league.players, els)
    hist = {int(e): fpl.history(client.element_summary(int(e))) for e in mapping["element_id"].dropna()}
    return mapping[["player_key", "element_id"]], hist


def point_in_time_fpl(mapping: pd.DataFrame, hist: dict[int, pd.DataFrame], r: int) -> tuple[pd.DataFrame, pd.Series]:
    """Joueurs FPL tels qu'on les voyait avant la journée PL r : sans statut, xG et minutes des journées < r."""
    rows, rate = [], {}
    for key, eid in zip(mapping["player_key"], mapping["element_id"]):
        rounds = pt.by_round(hist.get(int(eid)) if pd.notna(eid) else None)
        past = rounds[rounds["round"] < r]
        minutes = float(past["minutes"].sum())
        rows.append(
            {
                "player_key": key,
                "element_id": eid,
                "status": "a",
                "chance_next": np.nan,
                "news": "",
                "minutes": minutes,
                "xg90": float(past["xg"].sum()) / minutes * 90 if minutes > 0 else 0.0,
                "web_name": "",
            }
        )
        rate[key] = float((past["minutes"] > 0).mean()) if len(past) else np.nan
    return pd.DataFrame(rows), pd.Series(rate)


def snapshot(a: Analysis, g: int, mapping: pd.DataFrame, hist: dict[int, pd.DataFrame]) -> Snapshot:
    league = a.league
    r = pl_gw_for(league, g)
    kickoff = league.club_results.loc[league.club_results["pl_gw"] == r, "date"].min()
    cr = league.club_results.copy()
    later = cr["date"] >= kickoff
    cr.loc[later, "statut"] = "a_venir"
    cr.loc[later, ["home_score", "away_score"]] = pd.NA

    fpl_pit, rate = point_in_time_fpl(mapping, hist, r)
    players = league.players.copy()
    players["taux_jeu"] = players["player_key"].map(rate).fillna(rate.median())
    players["statut_performance"] = "ok"
    sub_league = dataclasses.replace(
        league, players=players, club_results=cr, goals=league.goals[league.goals["gw"] < g]
    )
    lu = a.lineups[a.lineups["gw"] < g]
    ps = mplayers.player_stats(sub_league, lu)
    sub = dataclasses.replace(
        a,
        league=sub_league,
        lineups=lu,
        player_stats=ps,
        player_value=ps,
        meta={**a.meta, "k_shrinkage": ps.attrs["k_shrinkage"]},
    )
    model = pr.fit_note_model(sub) if g >= 3 else PRIOR_MODEL
    strength = pr.fit_club_strength(cr)
    play_model = pt.fit_play_model(fpl_pit, hist, players.set_index("player_key")["taux_jeu"], r)
    proj = pr.project_players(sub, sorted(league.team_names), r, model, strength, fpl_pit, hist, play_model=play_model)
    return Snapshot(g, r, sub, fpl_pit, hist, model, strength, play_model, proj)


def structural_probs(snap: Snapshot, fx: pd.DataFrame, play: bool, adjust: bool) -> np.ndarray:
    ctx = build_context(snap.a, snap.gw - 1)
    p = ctx.players.copy()
    proj = snap.proj.set_index("player_key")
    if play:
        p["taux_jeu"] = p["player_key"].map(proj["p_joue"]).fillna(p["taux_jeu"])
    if adjust:
        p["note_retrecie"] = p["note_retrecie"] + p["player_key"].map(proj["ajustement_adversaire"]).fillna(0.0)
    ctx = dataclasses.replace(ctx, players=p)
    model = StructuralModel().fit(ctx)
    return model.sample_probs(fx, N_DRAWS, np.random.default_rng(SEED)).mean(axis=0)


def _usual_formation(a: Analysis, team: int, g: int) -> str | None:
    tm = a.team_match
    f = tm.loc[(tm["team_id"] == team) & (tm["gw"] < g), "formation"]
    return f.mode().iloc[0] if len(f) else None


def realistic_lineup(rows: list[int], d, value: np.ndarray, formation: str | None) -> Lineup:
    if formation is not None and (lu := op.initial_lineup(rows, d, formation, value)) is not None:
        return lu
    starts = [lu for f in FORMATIONS if (lu := op.initial_lineup(rows, d, f, value)) is not None]
    return max(starts, key=lambda lu: float(value[list(lu.starters)].sum()))


def actual_lineup(a: Analysis, match_id: str, team: int, formation: str, d, index: dict[str, int]):
    """Feuille réellement posée (11 choisi, banc trié par valeur faute d'ordre connu, capitaine), None si incomplète."""
    lu = a.lineups
    rows = lu[(lu["match_id"] == match_id) & (lu["team_id"] == team) & lu["player_key"].notna()]
    picks = rows[rows["statut"].isin(COACH_PICKS)]
    slots = slots_of(formation)
    if len(picks) != len(slots) or not picks["player_key"].isin(list(index)).all():
        return None
    order = {g: i for i, g in enumerate("GDMA")}
    picks = picks.assign(o=picks["poste_groupe"].map(order)).sort_values("o")
    starters = tuple(index[k] for k in picks["player_key"])
    if [d.line[s] for s in starters] != list(slots):
        return None
    bench_rows = rows[
        rows["statut"].isin(["remplacant_entre", "remplacant_non_entre"]) & rows["player_key"].isin(list(index))
    ]
    bench = [index[k] for k in bench_rows["player_key"]]
    keepers = [b for b in bench if d.line[b] == "G"][:1]
    field = sorted((b for b in bench if d.line[b] != "G"), key=lambda b: ("DMA".index(d.line[b]), b))
    cap_rows = picks[(picks["capitaine"] == 1) & (picks["poste_groupe"] != "G")]
    captain = index[cap_rows["player_key"].iloc[0]] if len(cap_rows) else None
    return Lineup(
        formation=formation,
        starters=starters,
        bench=tuple(keepers + field)[:BENCH_SIZE],
        captain=captain,
    )


def engine_probs(snap: Snapshot, fx: pd.DataFrame, full: Analysis) -> tuple[dict[str, np.ndarray], list[dict]]:
    """Probabilités du moteur pour chaque variante de compo, et lois des buts (compos réalistes) par équipe."""
    out = {k: [] for k in ("Moteur, 11 réaliste (P(joue))", "Moteur, 11 réaliste (notes)", "Moteur, compos optimisées")}
    out["Moteur, vraies compos"] = []
    goals, e_diff, n_real = [], [], 0
    for i, m in enumerate(fx.itertuples()):
        h, w = int(m.home_team_id), int(m.away_team_id)
        proj = snap.proj[snap.proj["team_id"].isin([h, w])].reset_index(drop=True)
        d = pr.sample_draws(proj, snap.model, N_DRAWS, seed=SEED + 97 * snap.gw + i)
        index = {k: j for j, k in enumerate(proj["player_key"])}
        rows = {t: [index[k] for k in proj.loc[proj["team_id"] == t, "player_key"]] for t in (h, w)}
        contrib = op.contribution(d)
        note_only = proj["note_attendue"].to_numpy(float)
        forms = {t: _usual_formation(snap.a, t, snap.gw) for t in (h, w)}

        lus = {t: realistic_lineup(rows[t], d, contrib, forms[t]) for t in (h, w)}
        res = simulate(lus[h], lus[w], d)
        out["Moteur, 11 réaliste (P(joue))"].append(res.outcome_probs())
        e_diff.append(float((res.home_goals - res.away_goals).mean()))
        goals += [
            {"match_id": m.match_id, "team_id": h, "sim": res.home_goals, "reel": m.home_goals},
            {"match_id": m.match_id, "team_id": w, "sim": res.away_goals, "reel": m.away_goals},
        ]

        lus_n = {t: realistic_lineup(rows[t], d, note_only, forms[t]) for t in (h, w)}
        out["Moteur, 11 réaliste (notes)"].append(simulate(lus_n[h], lus_n[w], d).outcome_probs())

        opp = op.optimise(rows[w], op.Evaluator(d, lus[h], home=False), tactics=False)[0]
        mine = op.optimise(rows[h], op.Evaluator(d, opp, home=True), tactics=False)[0]
        out["Moteur, compos optimisées"].append(simulate(mine, opp, d).outcome_probs())

        real = {
            t: actual_lineup(full, m.match_id, t, f, d, index)
            for t, f in ((h, m.home_formation), (w, m.away_formation))
        }
        n_real += sum(v is not None for v in real.values())
        real = {t: v or lus[t] for t, v in real.items()}
        res_real = simulate(real[h], real[w], d)
        out["Moteur, vraies compos"].append(res_real.outcome_probs())
        goals[-2]["sim_vraies"], goals[-1]["sim_vraies"] = res_real.home_goals, res_real.away_goals
    log.warning("J%d : %d compos réelles reconstituées sur %d", snap.gw, n_real, 2 * len(fx))
    return {k: np.array(v) for k, v in out.items()}, goals, np.array(e_diff)


def paired_bootstrap(diff: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    idx = rng.integers(0, len(diff), size=(N_BOOT, len(diff)))
    boot = diff[idx].mean(axis=1)
    return float(diff.mean()), float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))


def availability_check(a: Analysis, mapping: pd.DataFrame, hist: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """P(minutes > 0) sur toutes les journées PL des journées MPG jouées, pour tous les joueurs de la ligue."""
    rows = []
    for g in sorted(a.league.played["gw"].unique()):
        r = pl_gw_for(a.league, int(g))
        fpl_pit, rate = point_in_time_fpl(mapping, hist, r)
        taux = rate.fillna(rate.median())
        pm = pt.fit_play_model(fpl_pit, hist, taux, r)
        for key, eid in zip(mapping["player_key"], mapping["element_id"]):
            h = hist.get(int(eid))
            now = pt.by_round(h)
            now = now[now["round"] == r]
            if now.empty:
                continue
            x = pt.play_features(h, r, float(taux[key]))
            recent = pt.recent(h, r)
            blend = ((recent["minutes"] > 0).sum() + 2 * taux[key]) / (len(recent) + 2)
            rows.append(
                {
                    "gw": g,
                    "joue": float(now["minutes"].iloc[0] > 0),
                    "Taux de la saison (actuel)": float(taux[key]),
                    "5 derniers rétrécis": float(blend),
                    "Logit temps de jeu (coach)": pm.prob(x) if (pm is not None and x is not None) else float(blend),
                }
            )
    return pd.DataFrame(rows)


def note_check(snaps: dict[int, Snapshot], a: Analysis) -> pd.DataFrame:
    lu = a.lineups
    app = lu[lu["a_joue_irl"] & lu["player_key"].notna()]
    rows = []
    for g, s in snaps.items():
        if g < 3:
            continue
        proj = s.proj.set_index("player_key")
        cur = app[app["gw"] == g]
        cur = cur[cur["player_key"].isin(proj.index)]
        base = cur["player_key"].map(proj["note_retrecie"])
        adj = cur["player_key"].map(proj["note_attendue"])
        rows.append(
            pd.DataFrame(
                {"gw": g, "note": cur["note_brute"], "Note rétrécie (actuel)": base, "+ ajustement adversaire": adj}
            )
        )
    return pd.concat(rows, ignore_index=True)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    pd.set_option("display.width", 200)
    a = run(n_sim=50)
    mapping, hist = load_fpl(a)
    played = a.league.played.sort_values(["gw", "match_id"])
    gws = sorted(played["gw"].unique())
    snaps = {int(g): snapshot(a, int(g), mapping, hist) for g in gws}

    probs: dict[str, list[np.ndarray]] = {}
    goals, diffs = [], []
    for g in gws:
        fx = played[played["gw"] == g].reset_index(drop=True)
        s = snaps[int(g)]
        for name, play, adjust in (
            ("Structurel sans fuite (actuel)", False, False),
            ("Structurel + P(joue) coach", True, False),
            ("Structurel + ajustement adversaire", False, True),
            ("Structurel + les deux", True, True),
        ):
            probs.setdefault(name, []).append(structural_probs(s, fx, play, adjust))
        eng, gl, ed = engine_probs(s, fx, a)
        goals += gl
        prev = np.concatenate(diffs) if diffs else np.array([])
        prev_out = played.loc[played["gw"] < g, "resultat_dom"].map(RESULT_TO_IDX).to_numpy()
        link = OrderedLogit(b0=1.0).fit(prev, prev_out)
        probs.setdefault("Moteur → logit appris (écart de buts)", []).append(link.probs(ed))
        diffs.append(ed)
        for name, p in eng.items():
            probs.setdefault(name, []).append(p)
    probs = {k: np.concatenate(v) for k, v in probs.items()}

    bt = backtest(a, n_draws=1500)
    ref = {}
    for name in ("Elo", "Poisson bayésien", "Structurel (joueurs)"):
        rows = bt[bt["modele"] == name].set_index("match_id").loc[played["match_id"]]
        ref[name] = rows[["p_dom", "p_nul", "p_ext"]].to_numpy()
    probs["Structurel (backtest actuel, avec fuite)"] = ref.pop("Structurel (joueurs)")
    probs.update(ref)
    combos = {
        "Ensemble actuel (Elo + Poisson + structurel)": ["Elo", "Poisson bayésien", "Structurel sans fuite (actuel)"],
        "Elo + Poisson + structurel amélioré": ["Elo", "Poisson bayésien", "Structurel + les deux"],
        "Elo + Poisson + moteur": ["Elo", "Poisson bayésien", "Moteur, 11 réaliste (P(joue))"],
        "Elo + Poisson + moteur → logit": ["Elo", "Poisson bayésien", "Moteur → logit appris (écart de buts)"],
        "Elo + Poisson + structurel amélioré + moteur": [
            "Elo",
            "Poisson bayésien",
            "Structurel + les deux",
            "Moteur, 11 réaliste (P(joue))",
        ],
    }
    for name, parts in combos.items():
        probs[name] = np.mean([probs[p] for p in parts], axis=0)

    outcome = played["resultat_dom"].map(RESULT_TO_IDX).to_numpy()
    late = (played["gw"] >= 3).to_numpy()
    rng = np.random.default_rng(SEED)
    ref_rps = scores(probs["Ensemble actuel (Elo + Poisson + structurel)"], outcome)["rps"].to_numpy()
    base_rps = scores(probs["Structurel sans fuite (actuel)"], outcome)["rps"].to_numpy()
    table = []
    for name, p in probs.items():
        sc = scores(p, outcome)
        d_ens = paired_bootstrap(sc["rps"].to_numpy() - ref_rps, rng)
        d_str = paired_bootstrap(sc["rps"].to_numpy() - base_rps, rng)
        table.append(
            {
                "modèle": name,
                "RPS": sc["rps"].mean(),
                "RPS J3-J5": sc["rps"][late].mean(),
                "log loss": sc["log_loss"].mean(),
                "Brier": sc["brier"].mean(),
                "P(nul) moy.": p[:, 1].mean(),
                "Δ RPS vs ensemble [IC 90 %]": f"{d_ens[0]:+.3f} [{d_ens[1]:+.3f} ; {d_ens[2]:+.3f}]",
                "Δ RPS vs structurel [IC 90 %]": f"{d_str[0]:+.3f} [{d_str[1]:+.3f} ; {d_str[2]:+.3f}]",
            }
        )
    print(f"\n=== Résultats des matchs : {len(outcome)} matchs J1-J5 (nuls observés {np.mean(outcome == 1):.0%}) ===")
    print(pd.DataFrame(table).sort_values("RPS").round(3).to_string(index=False))

    av = availability_check(a, mapping, hist)
    print(f"\n=== Temps de jeu : {len(av)} joueur-journées (a joué : {av['joue'].mean():.0%}) ===")
    for c in av.columns[2:]:
        p = av[c].clip(1e-4, 1 - 1e-4)
        ll = -np.mean(av["joue"] * np.log(p) + (1 - av["joue"]) * np.log(1 - p))
        print(f"{c:32s} Brier {np.mean((p - av['joue']) ** 2):.4f}   log loss {ll:.4f}")

    nc = note_check(snaps, a)
    print(f"\n=== Notes : {len(nc)} notes MPG J3-J5 ===")
    for c in nc.columns[2:]:
        err = nc["note"] - nc[c]
        print(
            f"{c:32s} RMSE {np.sqrt(np.mean(err**2)):.3f}   biais {err.mean():+.3f}   corr {nc['note'].corr(nc[c]):.3f}"
        )

    sim = np.stack([x["sim"] for x in goals])
    real = np.array([x["reel"] for x in goals])
    pmf = np.array([np.mean(s == r) for s, r in zip(sim, real)])
    print(f"\n=== Buts par équipe (moteur, 11 réaliste) : {len(real)} équipes-matchs ===")
    print(
        f"moyenne simulée {sim.mean():.2f}, observée {real.mean():.2f}, log score moyen {-np.log(np.clip(pmf, 1e-4, 1)).mean():.3f}"
    )
    sim_v = np.stack([x["sim_vraies"] for x in goals])
    print(f"avec les vraies compos : moyenne simulée {sim_v.mean():.2f}")
    for name in (
        "Structurel sans fuite (actuel)",
        "Moteur, 11 réaliste (P(joue))",
        "Moteur → logit appris (écart de buts)",
    ):
        p = probs[name]
        print(
            f"{name:40s} proba max moyenne {p.max(axis=1).mean():.3f}, issue la plus probable juste {np.mean(p.argmax(axis=1) == outcome):.0%}"
        )


if __name__ == "__main__":
    main()
