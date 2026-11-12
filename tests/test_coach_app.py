from pathlib import Path

from streamlit.testing.v1 import AppTest

ENTRYPOINT = Path(__file__).resolve().parent.parent / "coach_app.py"


def _offline_page(state_dir: str) -> None:
    from pathlib import Path
    from unittest import mock

    from app.state import get_analysis
    from app.views import coach
    from mpg import fpl

    coach.STATE_DIR = Path(state_dir)
    with mock.patch.object(fpl.FplClient, "get", side_effect=fpl.FplError("hors ligne")):
        coach.render(get_analysis())


def test_coach_page_renders_without_fpl(tmp_path):
    at = AppTest.from_function(_offline_page, args=(str(tmp_path),), default_timeout=300)
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""
    assert any("FPL indisponible" in w.value for w in at.sidebar.warning)
    assert (tmp_path / "settings.json").exists()
    assert len(at.dataframe) >= 2
