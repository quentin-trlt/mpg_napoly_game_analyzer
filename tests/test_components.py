import re
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from app import components, theme
from app.components import (
    PCT_FORMAT,
    PCT_SIGNED_FORMAT,
    alert,
    alerts,
    as_pct,
    chip,
    chips,
    grid,
    medal,
    next_match,
    pct_column,
    prob_bar,
    rank_list,
    rank_tone,
    result_color,
    short_table,
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


def test_pct_column_formats():
    assert PCT_FORMAT == "%.0f %%"
    assert PCT_SIGNED_FORMAT == "%+.0f %%"
    plain = pct_column("Victoire")
    signed = pct_column("Écart", signed=True)
    bar = pct_column("Chances", bar=True)
    assert plain["label"] == "Victoire"
    assert plain["type_config"]["format"] == PCT_FORMAT
    assert signed["type_config"]["format"] == PCT_SIGNED_FORMAT
    assert bar["type_config"]["type"] == "progress"
    assert (bar["type_config"]["min_value"], bar["type_config"]["max_value"]) == (0, 100)
    assert bar["type_config"]["format"] == PCT_FORMAT


def test_pct_column_forwards_kwargs():
    assert pct_column("Victoire", help="Chance de gagner")["help"] == "Chance de gagner"


def test_pct_column_rejects_bar_with_sign():
    with pytest.raises(ValueError, match="exclusifs"):
        pct_column("Écart", bar=True, signed=True)


def test_as_pct_scales_copy_and_ignores_missing_columns():
    df = pd.DataFrame({"team": ["A", "B"], "p": [0.415, 0.5], "q": [0.1, 0.2]})
    before = df.copy()
    out = as_pct(df, ["p", "absente"])
    assert out is not df
    assert out["p"].tolist() == pytest.approx([41.5, 50.0])
    assert out["q"].tolist() == [0.1, 0.2]
    assert out["team"].tolist() == ["A", "B"]
    pd.testing.assert_frame_equal(df, before)


def test_as_pct_with_no_matching_column_returns_equal_copy():
    df = pd.DataFrame({"p": [0.5]})
    out = as_pct(df, ["absente"])
    assert out is not df
    pd.testing.assert_frame_equal(out, df)


@pytest.fixture
def shown(monkeypatch):
    calls: list[dict] = []
    expanders: list[str] = []

    def fake_dataframe(data, **kwargs):
        calls.append({"data": data, **kwargs})

    def fake_expander(label, *args, **kwargs):
        expanders.append(label)
        return nullcontext()

    monkeypatch.setattr(components.st, "dataframe", fake_dataframe)
    monkeypatch.setattr(components.st, "expander", fake_expander)
    monkeypatch.setattr(components, "is_mobile", lambda: False)
    return calls, expanders


def _wide() -> pd.DataFrame:
    return pd.DataFrame({c: [1, 2] for c in "abcdefg"})


def test_short_table_shows_listed_columns_then_all_in_expander(shown):
    calls, expanders = shown
    short_table(_wide(), ["a", "b"], alt="Équipes", height=120)
    assert [list(c["data"].columns) for c in calls] == [list("ab"), list("abcdefg")]
    assert calls[0]["alt"] == "Équipes"
    assert calls[0]["height"] == 120
    assert calls[0]["hide_index"] is True
    assert "height" not in calls[1]
    assert calls[1]["alt"] == "Équipes, toutes les colonnes"
    assert calls[1]["hide_index"] is True
    assert expanders == ["Toutes les colonnes"]


def test_short_table_without_alt_passes_none(shown):
    calls, _ = shown
    short_table(_wide(), ["a"])
    assert all(c["alt"] is None for c in calls)


def test_short_table_no_expander_when_nothing_more_to_show(shown):
    calls, expanders = shown
    short_table(_wide()[list("abc")], list("abc"))
    assert len(calls) == 1
    assert expanders == []


def test_short_table_full_is_ordered_and_filtered(shown):
    calls, expanders = shown
    short_table(_wide(), ["a", "b"], full=["c", "a", "absente", "b", "e"], hide_index=False)
    assert list(calls[1]["data"].columns) == ["c", "a", "b", "e"]
    assert calls[1]["hide_index"] is False
    assert expanders == ["Toutes les colonnes"]


def test_short_table_full_not_larger_than_visible_hides_expander(shown):
    calls, expanders = shown
    short_table(_wide(), ["a", "b"], full=["a", "b", "absente"])
    assert len(calls) == 1
    assert expanders == []


def test_short_table_pins_first_full_column_without_mutating_config(shown):
    calls, _ = shown
    config = {"a": "Équipe", "b": pct_column("Chances"), "e": "Cinq"}
    snapshot = {"a": "Équipe", "b": dict(config["b"]), "e": "Cinq"}
    short_table(_wide(), ["a", "b"], column_config=config)
    visible, full = calls[0]["column_config"], calls[1]["column_config"]
    assert visible == {"a": "Équipe", "b": snapshot["b"]}
    assert full["a"] == {"label": "Équipe", "pinned": True}
    assert full["b"] == snapshot["b"]
    assert full["e"] == "Cinq"
    assert config == snapshot
    assert config["b"].get("pinned") is None


def test_short_table_pins_first_column_given_as_dict_config(shown):
    calls, _ = shown
    config = {"c": pct_column("Chances")}
    short_table(_wide(), ["a", "b"], full=["c", "a", "b"], column_config=config)
    assert calls[0]["column_config"] is None
    assert calls[1]["column_config"]["c"]["pinned"] is True
    assert calls[1]["column_config"]["c"]["label"] == "Chances"
    assert config["c"].get("pinned") is None


def test_short_table_pins_first_column_even_without_config(shown):
    calls, _ = shown
    short_table(_wide(), ["a", "b"])
    assert calls[1]["column_config"] == {"a": {"pinned": True}}


def test_short_table_desktop_leaves_visible_config_untouched(shown):
    calls, _ = shown
    config = {"a": "Équipe", "b": pct_column("Chances", bar=True)}
    short_table(_wide(), ["a", "b", "c"], column_config=config)
    assert calls[0]["column_config"] == {"a": "Équipe", "b": config["b"]}


def test_short_table_phone_pins_first_and_narrows_others(shown, monkeypatch):
    calls, _ = shown
    monkeypatch.setattr(components, "is_mobile", lambda: True)
    config = {"a": "Équipe", "b": pct_column("Chances", bar=True), "c": "Trois"}
    snapshot = {"a": "Équipe", "b": dict(config["b"]), "c": "Trois"}
    short_table(_wide(), ["a", "b", "c", "d"], column_config=config)
    visible = calls[0]["column_config"]
    assert visible["a"] == {"label": "Équipe", "pinned": True}
    assert visible["b"]["width"] == "small"
    assert visible["b"]["label"] == "Chances"
    assert visible["b"].get("pinned") is None
    assert visible["c"] == {"label": "Trois", "width": "small"}
    assert visible["d"] == {"width": "small"}
    assert config == snapshot
    assert config["b"].get("width") is None


def test_short_table_phone_keeps_explicit_width(shown, monkeypatch):
    calls, _ = shown
    monkeypatch.setattr(components, "is_mobile", lambda: True)
    config = {"a": pct_column("Nom", width="large"), "b": pct_column("Chances", width="medium")}
    short_table(_wide(), ["a", "b"], column_config=config)
    visible = calls[0]["column_config"]
    assert visible["a"]["width"] == "large"
    assert visible["a"]["pinned"] is True
    assert visible["b"]["width"] == "medium"


def test_short_table_phone_expander_table_is_unchanged(shown, monkeypatch):
    calls, _ = shown
    monkeypatch.setattr(components, "is_mobile", lambda: True)
    short_table(_wide(), ["a", "b"], column_config={"b": "Deux"})
    assert calls[1]["column_config"] == {"b": "Deux", "a": {"pinned": True}}


def _short_table_config_app() -> None:
    import pandas as pd
    import streamlit as st

    from app.components import pct_column, short_table

    df = pd.DataFrame({"team": ["A", "B"], "p": [0.4, 0.6], "x": [1, 2], "y": [3, 4]})
    short_table(
        df.assign(p=df["p"] * 100),
        ["team", "p"],
        column_config={"team": "Équipe", "p": pct_column("Victoire", bar=True)},
        alt="Équipes",
    )
    st.write("ok")


def test_short_table_accepts_real_column_config_in_streamlit():
    at = AppTest.from_function(_short_table_config_app).run()
    assert not at.exception
    assert len(at.dataframe) == 2


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
