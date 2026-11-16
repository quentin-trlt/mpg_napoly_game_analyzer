import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
VIEW_FILES = sorted((APP / "views").glob("*.py"))
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")
FORBIDDEN_IN_VIEWS = {
    "attribut style=": re.compile(r"style\s*="),
    "balise <style": re.compile(r"<style", re.IGNORECASE),
    "unsafe_allow_html": re.compile(r"unsafe_allow_html"),
}


@pytest.mark.parametrize("path", VIEW_FILES, ids=lambda p: p.name)
def test_view_has_no_inline_styling(path: Path):
    source = path.read_text(encoding="utf-8")
    found = [label for label, pattern in FORBIDDEN_IN_VIEWS.items() if pattern.search(source)]
    assert not found, f"{path.name} contient : {', '.join(found)}"


@pytest.mark.parametrize("path", VIEW_FILES, ids=lambda p: p.name)
def test_view_has_no_hardcoded_color(path: Path):
    colors = HEX_COLOR.findall(path.read_text(encoding="utf-8"))
    assert not colors, f"{path.name} contient des couleurs en dur : {sorted(set(colors))}"


@pytest.mark.parametrize("name", ["components.py", "charts.py"])
def test_helper_module_has_no_hardcoded_color(name: str):
    colors = HEX_COLOR.findall((APP / name).read_text(encoding="utf-8"))
    assert not colors, f"{name} contient des couleurs en dur : {sorted(set(colors))}"
