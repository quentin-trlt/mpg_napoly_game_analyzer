from types import SimpleNamespace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from app import charts

TEAM = 3
NAMES = {
    1: "Tractou'pelle",
    2: "TheFC",
    3: "Thérèsse",
    4: "Les Invincibles de Paris",
    5: "Rouges",
    6: "Bleus",
    7: "Verts",
    8: "Jaunes",
    9: "Noirs",
    10: "Blancs",
}


def _ticks(fig: go.Figure) -> list:
    return list(fig.layout.xaxis.ticktext)


def _end_labels(fig: go.Figure) -> list:
    return [a for a in fig.layout.annotations if a.xanchor == "left" and a.xshift]


def _season(n_gw: int) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for gw in range(1, n_gw + 1):
        ranks = rng.permutation(10) + 1
        rows += [
            {"gw": gw, "team_id": t, "team_name": NAMES[t], "rang": int(r), "pts": gw * 3} for t, r in zip(NAMES, ranks)
        ]
    return pd.DataFrame(rows)


def _history(n_gw: int) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    rows = []
    for gw in range(0, n_gw + 1):
        p = rng.dirichlet(np.ones(10))
        rows += [{"apres_journee": gw, "team_id": t, "p_titre": float(v)} for t, v in zip(NAMES, p)]
    return pd.DataFrame(rows)


def _snapshots(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    rows = []
    for gw in range(1, n + 1):
        ranks = rng.permutation(10) + 1
        rows += [{"avant_journee": gw, "team_id": t, "rang_moy": float(r)} for t, r in zip(NAMES, ranks)]
    return pd.DataFrame(rows)


def _rps(n_gw: int) -> pd.DataFrame:
    rows = []
    for k, model in enumerate(["Ensemble", "Référence (fréquences)", "Elo", "Poisson bayésien", "Structurel (xG)"]):
        for gw in range(1, n_gw + 1):
            rows.append(
                {"modele": model, "gw": gw, "rps_cumule": 0.2 + 0.001 * k + 0.0001 * gw, "rps": 0.2, "matchs": 10}
            )
    return pd.DataFrame(rows)


def _matches(n_gw: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "team_id": TEAM,
            "gw": range(1, n_gw + 1),
            "note_moy": [5.5 + 0.01 * g for g in range(n_gw)],
            "resultat": (["V", "N", "D"] * (n_gw // 3 + 1))[:n_gw],
            "opp_name": "Rouges",
            "note_moy_adv": 5.4,
            "bp": 2,
            "bc": 1,
        }
    )


def _teams() -> pd.DataFrame:
    return pd.DataFrame({"team_id": list(NAMES), "team_name": list(NAMES.values())})


def _hovers(fig: go.Figure) -> list[str]:
    return [t.hovertemplate for t in fig.data if getattr(t, "hovertemplate", None)]


@pytest.mark.parametrize(
    "n_gw",
    [38, 18],
)
def test_thin_ticks_cap_and_keep_last(n_gw):
    kept = charts._thin(range(1, n_gw + 1))
    assert len(kept) <= charts.MAX_TICKS
    assert kept[-1] == n_gw
    steps = {b - a for a, b in zip(kept, kept[1:])}
    assert len(steps) == 1


def test_thin_ticks_keeps_short_lists():
    assert charts._thin([1, 2, 3]) == [1, 2, 3]


def test_gw_axis_shortens_labels_and_names_the_phase():
    ticks, text, title = charts._gw_axis([0, 1, 2], {0: "Avant J1", 1: "Après J1", 2: "Après J2"})
    assert ticks == [0, 1, 2]
    assert text == ["Avant J1", "J1", "J2"]
    assert title == "Après la journée"


def test_gw_axis_default_is_before_the_gameweek():
    _, text, title = charts._gw_axis([5, 6])
    assert text == ["J5", "J6"]
    assert title == "Avant la journée"


@pytest.mark.parametrize("n_gw", [38, 18])
def test_bump_chart_axis_and_end_labels(n_gw):
    fig = charts.bump_chart(_season(n_gw), TEAM, 10)
    assert len(_ticks(fig)) <= 10
    assert _ticks(fig)[-1] == f"J{n_gw}"
    labels = _end_labels(fig)
    assert len(labels) <= 4
    assert NAMES[TEAM] in [a.text for a in labels]


def test_bump_chart_labels_best_ranks():
    sbg = _season(5)
    fig = charts.bump_chart(sbg, TEAM, 10)
    last = sbg[sbg["gw"] == 5].sort_values("rang")
    expected = {NAMES[t] for t in [TEAM, *last["team_id"].head(3)]}
    assert {a.text for a in _end_labels(fig)} == {charts._clip(n) for n in expected}


@pytest.mark.parametrize("n_gw", [38, 18])
def test_title_history_axis_and_end_labels(n_gw):
    fig = charts.title_history(_history(n_gw), NAMES, TEAM)
    assert len(_ticks(fig)) <= 10
    assert _ticks(fig)[-1] == f"J{n_gw}"
    assert fig.layout.xaxis.title.text == "Après la journée"
    labels = _end_labels(fig)
    assert len(labels) <= 4
    assert NAMES[TEAM] in [a.text for a in labels]


def test_title_history_hover_is_rounded():
    fig = charts.title_history(_history(5), NAMES, TEAM)
    assert all(".1f" not in h for h in _hovers(fig))


@pytest.mark.parametrize("reverse", [True, False])
def test_snapshot_lines_limits_labels(reverse):
    df = _snapshots(30).assign(team_name=lambda d: d["team_id"].map(NAMES))
    labels = {g: f"Avant J{g}" for g in df["avant_journee"].unique()}
    fig = charts.snapshot_lines(
        df, "avant_journee", "rang_moy", NAMES, TEAM, "t", "Rang", reverse=reverse, x_labels=labels
    )
    assert len(_ticks(fig)) <= 10
    assert _ticks(fig)[-1] == "J30"
    assert fig.layout.xaxis.title.text == "Avant la journée"
    ends = _end_labels(fig)
    assert len(ends) <= 4
    assert NAMES[TEAM] in [a.text for a in ends]


def test_snapshot_lines_percent_hover_has_no_decimal():
    df = _snapshots(4).assign(p_titre=0.123)
    fig = charts.snapshot_lines(df, "avant_journee", "p_titre", NAMES, TEAM, "t", "%", pct=True)
    assert all(".1f" not in h for h in _hovers(fig))
    assert any(".0f} %" in h for h in _hovers(fig))


def test_snapshot_lines_final_legend_above():
    df = _snapshots(3)
    fig = charts.snapshot_lines(df, "avant_journee", "rang_moy", NAMES, TEAM, "t", "Rang", final={1: 2, 2: 1})
    assert fig.layout.legend.y > 1
    assert fig.layout.legend.orientation == "h"


@pytest.mark.parametrize("n_gw", [38, 18])
def test_rps_evolution_labels_only_the_two_references(n_gw):
    fig = charts.rps_evolution(_rps(n_gw))
    assert len(_ticks(fig)) <= 10
    assert _ticks(fig)[-1] == f"J{n_gw}"
    texts = [a.text.replace("<br>", " ") for a in _end_labels(fig)]
    assert sorted(texts) == ["Ensemble", "Pronostic de base"]
    assert fig.layout.legend.y > 1
    legend_names = [t.name for t in fig.data if t.showlegend]
    assert legend_names == ["Autres modèles"]


def test_end_labels_are_pushed_apart():
    fig = go.Figure()
    fig.update_layout(height=400)
    charts._end_labels(fig, 5, [("A", 1.0, "#000"), ("B", 1.01, "#000"), ("C", 1.02, "#000")], (0.0, 2.0))
    assert len({a.yshift for a in fig.layout.annotations}) == 3
    screen = sorted(a.y / 2.0 * 300 + a.yshift for a in fig.layout.annotations)
    assert all(b - a >= 14 for a, b in zip(screen, screen[1:]))


def test_end_labels_leave_distant_ones_alone():
    fig = go.Figure()
    fig.update_layout(height=400)
    charts._end_labels(fig, 5, [("A", 0.2, "#000"), ("B", 1.8, "#000")], (0.0, 2.0))
    assert all(a.yshift == 0 for a in fig.layout.annotations)


def test_end_margin_fits_long_names_without_truncation():
    assert charts._end_margin(["Tractou'pelle"]) >= 90
    assert charts._clip("Tractou'pelle") == "Tractou'pelle"
    assert charts._clip("Les Invincibles de Paris") == "Les Invincible…"
    assert charts._clip("Pronostic<br>de base") == "Pronostic<br>de base"


def test_compact_keeps_names_and_shrinks_margin():
    fig = charts.title_history(_history(5), NAMES, TEAM)
    before = fig.layout.margin.r
    charts._compact(fig)
    assert fig.layout.margin.r <= before
    assert "Thérèsse" in [a.text for a in fig.layout.annotations]


def test_gw_points_keeps_scores_in_ticks_only_when_few():
    few = charts.gw_points(_matches(4), TEAM)
    many = charts.gw_points(_matches(38), TEAM)
    assert "<br>" in few.layout.xaxis.ticktext[0]
    assert all("<br>" not in t for t in many.layout.xaxis.ticktext)
    assert "%{customdata[2]}" in many.data[0].hovertemplate


@pytest.mark.parametrize("n_gw", [38, 18, 4])
def test_gw_points_axis(n_gw):
    fig = charts.gw_points(_matches(n_gw), TEAM)
    assert len(_ticks(fig)) <= 10
    assert _ticks(fig)[-1].startswith(f"J{n_gw}")
    assert fig.layout.legend.y > 1


def _lines_pv() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    rows = []
    for g in "GDMA":
        for i in range(12):
            rows.append(
                {
                    "poste_groupe": g,
                    "n_notes": 5,
                    "enchere": 2 + i * 3,
                    "note_retrecie": 5 + rng.random(),
                    "note_attendue": 5 + i * 0.05,
                    "joueur": f"J{i}",
                    "team_id": TEAM if i % 2 else 1,
                    "team_name": "Rouges",
                    "residu_valeur": 0.1,
                }
            )
    return pd.DataFrame(rows)


def _sim() -> SimpleNamespace:
    rng = np.random.default_rng(4)
    return SimpleNamespace(
        summary=pd.DataFrame({"team_id": list(NAMES), "pts_moy": range(10), "pts_actuels": range(10)}),
        team_ids=list(NAMES),
        final_points=rng.integers(20, 80, size=(200, 10)),
    )


def _legend_figures() -> dict[str, go.Figure]:
    teams = _teams()
    shares = teams.assign(**{f"part_{g}": 0.25 for g in "GDMA"})
    goals = teams.assign(bp_reel=5, bp_mpg=2, bp_csc=1)
    pairs = teams.assign(a=3, b=4)
    ranks = teams.assign(a=range(1, 11), b=range(10, 0, -1), lo=1, hi=10, cur=range(1, 11))
    parts = teams.assign(x=1.0, y=-1.0)
    return {
        "budget_shares": charts.budget_shares(shares),
        "stacked_goals": charts.stacked_goals(goals),
        "paired_bars": charts.paired_bars(pairs, "team_name", "a", "b", "A", "B", "t", "x"),
        "dumbbell": charts.dumbbell_ranks(ranks, "a", "b", "A", "B", TEAM, "t"),
        "rank_ranges": charts.rank_ranges(ranks, "lo", "hi", "cur", TEAM, "t"),
        "stacked_components": charts.stacked_components(parts, [("x", "X"), ("y", "Y")], TEAM, "t"),
        "final_points_box": charts.final_points_box(_sim(), NAMES, TEAM),
        "price_note_facets": charts.price_note_facets(_lines_pv(), TEAM),
        "sim_distribution": charts.sim_distribution(
            np.random.default_rng(5).integers(10, 60, size=(50, 10)),
            list(NAMES),
            NAMES,
            pd.Series(range(10), index=list(NAMES)),
            TEAM,
        ),
    }


def test_every_legend_is_horizontal_above_the_plot():
    for name, fig in _legend_figures().items():
        assert fig.layout.legend.orientation == "h", name
        assert fig.layout.legend.y > 1, name


def test_legend_with_many_entries_gets_more_top_margin():
    fig = charts.budget_shares(_teams().assign(**{f"part_{g}": 0.25 for g in "GDMA"}))
    assert fig.layout.margin.t is None or fig.layout.margin.t >= charts.DEFAULT_TOP


def test_no_percent_with_decimal_in_any_hover():
    figs = list(_legend_figures().values())
    probs = pd.DataFrame(np.full((10, 10), 0.1), index=list(NAMES), columns=range(1, 11))
    figs.append(charts.rank_heatmap(probs, NAMES, list(NAMES)))
    figs.append(charts.title_history(_history(3), NAMES, TEAM))
    for fig in figs:
        for trace in fig.data:
            assert ".1f} %" not in (getattr(trace, "hovertemplate", None) or "")


def test_rank_heatmap_thins_place_labels():
    probs = pd.DataFrame(np.full((20, 20), 0.05), index=range(20), columns=range(1, 21))
    fig = charts.rank_heatmap(probs, {i: str(i) for i in range(20)}, list(range(20)))
    assert len(fig.layout.xaxis.ticktext) <= 10
    assert fig.layout.xaxis.ticktext[-1] == "20e"


def test_rank_axes_stay_light_with_many_teams():
    assert charts._rank_dtick(10) == 1
    assert charts._rank_dtick(18) == 2
    assert charts._rank_dtick(20) == 2


@pytest.mark.parametrize("mobile", [True, False])
def test_component_heatmap_labels_do_not_tilt(monkeypatch, mobile):
    monkeypatch.setattr(charts, "is_mobile", lambda: mobile)
    comps = ["rendement", "prix", "fiabilite"]
    labels = {"rendement": "Rendement", "prix": "Prix payé vs cote", "fiabilite": "Fiabilité"}
    m = _teams().assign(score=range(10), **{c: float(i) for i, c in enumerate(comps)})
    fig = charts.component_heatmap(m, comps, labels)
    assert fig.layout.xaxis.tickangle in (0, -90)
    if mobile:
        assert fig.layout.xaxis.tickangle == -90
        assert fig.data[0].showscale is False
    else:
        assert "<br>" in fig.data[0].x[1]
