import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import theme
from app.components import (
    alert,
    alerts,
    chip,
    chips,
    grid,
    medal,
    next_match,
    prob_bar,
    rank_list,
    rank_tone,
    result_color,
)


def _table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "rang": [1, 2],
            "team_id": [10, 20],
            "team_name": ["Les <b>Rouges</b>", "Bleus"],
            "g": [5, 3],
            "n": [1, 2],
            "p": [0, 1],
            "diff": [7, -2],
            "pts": [16, 11],
            "forme": ["VVN", None],
        }
    )


def test_prob_bar_default_labels_and_aria():
    html = prob_bar(0.6, 0.17, 0.23)
    assert 'aria-label="Victoire domicile 60%, nul 17%, victoire extérieur 23%"' in html
    assert "<span>Dom.</span><span>Nul</span><span>Ext.</span>" in html
    assert 'title="Domicile 60%"' in html


def test_prob_bar_custom_labels():
    html = prob_bar(0.6, 0.17, 0.23, labels=("Toi", "Nul", "Adversaire"))
    assert 'aria-label="Toi 60%, Nul 17%, Adversaire 23%"' in html
    assert "<span>Toi</span><span>Nul</span><span>Adversaire</span>" in html


def test_rank_tone_returns_class_names():
    assert rank_tone(1, 10) == "tone-good"
    assert rank_tone(3, 10) == "tone-good"
    assert rank_tone(5, 10) == "tone-mid"
    assert rank_tone(8, 10) == "tone-bad"
    assert rank_tone(7, 10) == "tone-mid"


def test_result_color_fallback_is_text_2():
    assert result_color("V") == theme.RES_V
    assert result_color("?") == theme.TEXT_2


def test_rank_list_marks_me_escapes_and_has_no_inline_style():
    html = rank_list(_table(), 10, {10: "Alice", 20: "Bob"})
    assert html.count('class="r me"') == 1
    assert "Les &lt;b&gt;Rouges&lt;/b&gt;" in html
    assert "<b>Rouges" not in html
    assert "16<small>pts</small>" in html
    assert "5V 1N 0D · +7" in html
    assert "3V 2N 1D · −2" in html
    assert "style=" not in html


def test_rank_list_without_team_has_no_me_row():
    assert 'class="r me"' not in rank_list(_table(), None, {})


def test_next_match_structure():
    html = next_match("Ton match", "60 %", "de chances", "Nul <b>17 %</b>", "<div>barre</div>")
    assert '<div class="when">Ton match</div>' in html
    assert '<div class="odds">60 %<span>de chances</span></div>' in html
    assert '<div class="line">Nul <b>17 %</b></div><div>barre</div>' in html


def test_alert_tone_and_escape():
    html = alert("!", "Brobbey est <b>blessé</b>", detail="<script>", tone="bad")
    assert 'class="alert tone-bad"' in html
    assert "Brobbey est <b>blessé</b>" in html
    assert "&lt;script&gt;" in html
    assert "style=" not in html
    assert alerts([html]).startswith('<div class="alerts">')


def test_alert_rejects_unknown_tone():
    with pytest.raises(ValueError, match="Ton d'alerte inconnu"):
        alert("!", "x", tone="#FF0000")


def test_chip_variants():
    assert chip("2 bonus") == '<span class="chip">2 bonus</span>'
    assert chip("a<b", tone="good", off=True) == '<span class="chip good off">a&lt;b</span>'
    assert chips(["a", {"text": "b", "tone": "bad"}]) == '<span class="chip">a</span><span class="chip bad">b</span>'
    with pytest.raises(ValueError, match="Ton de pastille inconnu"):
        chip("x", tone="warn")


def test_medal_nan_none_and_ranks():
    assert "medal none" in medal(float("nan")) and "n'a pas joué" in medal(float("nan"))
    assert "medal none" in medal(None)
    assert 'class="medal gold"' in medal(1, 10)
    assert "<small>/10</small>" in medal(1, 10)
    assert 'class="medal"' in medal(7.0)
    assert "style=" not in medal(2)


def test_grid_passes_template_as_variable():
    html = grid(["<div>a</div>", "<div>b</div>"], "40px minmax(0, 1fr)")
    assert 'style="--tpl:40px minmax(0, 1fr)"' in html
    assert html.endswith("<div>a</div><div>b</div></div>")


def test_short_table_rejects_more_than_five_columns():
    from app.components import short_table

    df = pd.DataFrame({c: [1] for c in "abcdef"})
    with pytest.raises(ValueError, match="5 colonnes au plus"):
        short_table(df, list("abcdef"))


def _short_table_app() -> None:
    import pandas as pd

    from app.components import short_table

    df = pd.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
    short_table(df, ["a", "b"], more="Voir tout")


def test_short_table_renders_table_and_expander():
    at = AppTest.from_function(_short_table_app).run()
    assert not at.exception
    assert [e.label for e in at.expander] == ["Voir tout"]


def _limit_banner_app() -> None:
    from app.components import limit_banner

    limit_banner([])
    limit_banner(["Pas de cote", "Pas de données FPL"])


def test_limit_banner_empty_renders_nothing_and_filled_renders_items():
    at = AppTest.from_function(_limit_banner_app).run()
    assert not at.exception
    html = [m.value for m in at.get("html")]
    assert len(html) == 1
    assert "Saison passée, données partielles" in html[0]
    assert "<li>Pas de cote</li>" in html[0]


def _empty_state_app() -> None:
    from app.components import empty_state

    empty_state("Rien à montrer", "Aucun match joué")


def test_empty_state_renders():
    at = AppTest.from_function(_empty_state_app).run()
    assert not at.exception
    assert "Aucun match joué" in at.get("html")[0].value


def test_css_has_no_remote_font_import_and_respects_font_floor():
    assert "fonts.googleapis" not in theme.CSS
    assert "@import" not in theme.CSS
    sizes = [float(m) for m in re.findall(r"font-size:\s*([\d.]+)rem", theme.CSS)]
    assert sizes
    assert min(sizes) >= theme.FONT_FLOOR_REM


def test_css_source_uses_tokens_only():
    source = Path(theme.__file__).read_text(encoding="utf-8")
    css_source = source[source.index('CSS = f"""') : source.index("def inject_css")]
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", css_source)
    assert not re.search(r"rgba?\(\s*\d", css_source)
