from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ENTRYPOINT = Path(__file__).resolve().parent.parent / "streamlit_app.py"
VIEWS = [
    "ligue",
    "matchs",
    "equipe",
    "favoris",
    "chance",
    "coaching",
    "joueurs",
    "mercato",
    "analyse_mercato",
    "predictions",
    "suivi",
]


def _page(view: str, team_id: int) -> None:
    import importlib

    from app.state import get_analysis

    importlib.import_module(f"app.views.{view}").render(get_analysis(), team_id)


@pytest.mark.parametrize("view", VIEWS)
def test_view_renders(view):
    at = AppTest.from_function(_page, args=(view, 5), default_timeout=180)
    at.run()
    assert not at.exception, at.exception[0].message if at.exception else ""


def test_entrypoint_renders():
    at = AppTest.from_file(str(ENTRYPOINT), default_timeout=180)
    at.run()
    assert not at.exception
    assert at.selectbox[0].label == "Mon équipe"
