from pathlib import Path

from streamlit.testing.v1 import AppTest

ENTRYPOINT = Path(__file__).resolve().parent.parent / "coach_app.py"


def _page(state_dir: str, with_snapshot: bool, click: bool) -> None:
    from dataclasses import replace
    from pathlib import Path
    from unittest import mock

    import build_fpl
    from app.state import get_analysis
    from app.views import coach
    from mpg import fpl

    coach.STATE_DIR = Path(state_dir)
    coach._load_fpl.clear()
    coach._recommend.clear()
    a = get_analysis()
    if not with_snapshot:
        a = replace(a, league=replace(a.league, fpl_players=None, fpl_history=None))
    with (
        mock.patch.object(fpl.FplClient, "__init__", side_effect=AssertionError("réseau interdit")),
        mock.patch.object(fpl.FplClient, "get", side_effect=AssertionError("réseau interdit")),
        mock.patch.object(coach, "get_analysis", return_value=a),
        mock.patch.object(build_fpl, "refresh") as refresh,
    ):
        coach.render(a)
    if click:
        coach.st.session_state["refresh_calls"] = refresh.call_count


def _run(*args: object) -> AppTest:
    at = AppTest.from_function(_page, args=(*args,), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    return at


def test_coach_page_renders_without_snapshot(tmp_path):
    at = _run(str(tmp_path), False, False)
    assert any("Pas d'instantané FPL" in w.value for w in at.sidebar.warning)
    assert (tmp_path / "settings.json").exists()
    assert len(at.dataframe) >= 2


def test_coach_reads_snapshot_without_network(tmp_path):
    at = _run(str(tmp_path), True, False)
    assert not at.sidebar.warning, [w.value for w in at.sidebar.warning]
    assert any("Instantané FPL du" in c.value for c in at.sidebar.caption)
    assert len(at.dataframe) >= 2


def test_refresh_button_calls_build_fpl(tmp_path):
    at = AppTest.from_function(_page, args=(str(tmp_path), True, True), default_timeout=300)
    at.run()
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert at.session_state["refresh_calls"] == 1
