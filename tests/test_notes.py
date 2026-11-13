import dataclasses

import numpy as np
import pandas as pd
import pytest

from mpg.analysis import run
from mpg.coach import projection as pr
from mpg.forecast.models import StructuralModel
from mpg.forecast.season import build_context
from mpg.notes import fit_postes, player_notes
from mpg.point_in_time import pl_kickoff
from mpg.premier_league import pl_gw_for


def synthetic(n_players: int = 60, n_matches: int = 30, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    keys = [f"p{i}" for i in range(n_players)]
    true = 5.5 + 0.4 * rng.standard_normal(n_players)
    rows = []
    for key, mu in zip(keys, true):
        for _ in range(n_matches):
            start = rng.random() < 0.8
            note = mu + 1.0 * rng.standard_normal() if start else 4.8 + 0.5 * rng.standard_normal()
            rows.append({"player_key": key, "note": note, "titulaire": int(start), "a_joue": 1})
    players = pd.DataFrame({"player_key": keys, "poste_groupe": "M", "true": true})
    return pd.DataFrame(rows), players


def test_fit_postes_recovers_simulated_parameters():
    notes, players = synthetic()
    m = fit_postes(notes.assign(poste_groupe="M"))["M"]
    assert m.m_titulaire == pytest.approx(5.5, abs=0.15)
    assert np.sqrt(m.s2_titulaire) == pytest.approx(1.0, abs=0.1)
    assert np.sqrt(m.tau2) == pytest.approx(0.4, abs=0.15)
    assert m.m_remplacant == pytest.approx(4.8, abs=0.1)
    assert m.p_titulaire == pytest.approx(0.8, abs=0.03)


def test_shrunk_means_beat_raw_means():
    notes, players = synthetic(n_matches=6, seed=1)
    est = player_notes(notes, players).join(players.set_index("player_key"))
    raw = notes[notes["titulaire"] == 1].groupby("player_key")["note"].mean()
    err_shrunk = ((est["note_titulaire"] - est["true"]) ** 2).mean()
    err_raw = ((raw.reindex(est.index) - est["true"]) ** 2).mean()
    assert err_shrunk < err_raw


def test_player_without_notes_gets_the_poste_prior():
    notes, players = synthetic(n_players=10, n_matches=5)
    players = pd.concat([players, pd.DataFrame({"player_key": ["nouveau"], "poste_groupe": ["M"], "true": [5.5]})])
    est = player_notes(notes, players)
    prior = fit_postes(notes.assign(poste_groupe="M"))["M"]
    new = est.loc["nouveau"]
    assert new["n_notes_pl"] == 0
    assert new["note_titulaire"] == pytest.approx(prior.m_titulaire)
    assert new["p_titulaire_si_joue"] == pytest.approx(prior.p_titulaire)
    assert new["note_titulaire_sd"] == pytest.approx(np.sqrt(prior.tau2))
    assert (est["note_titulaire_sd"] <= np.sqrt(prior.tau2) + 1e-12).all()
    lo = est[["note_titulaire", "note_remplacant"]].min(axis=1)
    hi = est[["note_titulaire", "note_remplacant"]].max(axis=1)
    assert est["note_esperee"].between(lo, hi).all()


@pytest.fixture(scope="module")
def analysis():
    return run(n_sim=50)


def test_past_note_model_ignores_later_notes(analysis):
    league = analysis.league
    notes = league.player_match_notes.copy()
    later = notes["date"] >= pl_kickoff(league, 3)
    notes.loc[later & notes["note"].notna(), "note"] = 9.0
    tampered = dataclasses.replace(analysis, league=dataclasses.replace(league, player_match_notes=notes))
    cols = ["note_titulaire", "note_titulaire_sd", "p_titulaire_si_joue", "note_esperee"]
    pd.testing.assert_frame_equal(build_context(tampered, 2).players[cols], build_context(analysis, 2).players[cols])


def test_structural_model_uses_the_mixture_when_notes_exist(analysis):
    ctx = build_context(analysis)
    q = np.concatenate([grp["q"] for t in StructuralModel().fit(ctx).teams.values() for grp in t.values()])
    assert (q < 1).any() and ((q > 0) & (q <= 1)).all()

    bare = dataclasses.replace(ctx, players=ctx.players.drop(columns=["note_titulaire"]))
    q = np.concatenate([grp["q"] for t in StructuralModel().fit(bare).teams.values() for grp in t.values()])
    assert (q == 1).all()


def test_substitutes_are_simulated_with_the_substitute_note(analysis):
    m = StructuralModel().fit(build_context(analysis))
    m.team_effect = {}
    team = next(iter(m.teams))
    for grp in m.teams[team].values():
        n = len(grp["p"])
        assert n >= grp["k"]
        grp |= {"p": np.ones(n), "q": np.zeros(n), "sub_mean": np.full(n, 4.0), "sub_sigma": np.zeros(n)}
        grp["statut"] = np.full(n, "ok")
    notes = m.team_notes(team, np.array([m.next_gw]), 50, np.random.default_rng(0))
    assert np.allclose(notes, 4.0)


def test_coach_draws_use_the_substitute_note(analysis):
    league = analysis.league
    model = pr.fit_note_model(analysis)
    strength = pr.fit_club_strength(league.club_results)
    proj = pr.project_players(analysis, [0, 1], pl_gw_for(league, league.last_gw + 1), model, strength)
    assert (proj["p_titulaire"] < 1).any()
    subs = proj.assign(p_titulaire=0.0, note_remplacant_attendue=4.0, sigma_remplacant_note=0.0, lambda_buts=0.0)
    assert np.allclose(pr.sample_draws(subs, model, n_draws=200, seed=0).note, 4.0)
