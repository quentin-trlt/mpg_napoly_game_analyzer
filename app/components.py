from html import escape

import pandas as pd
import streamlit as st

from app.theme import RESULT_COLORS
from mpg.glossary import explain


def hero(eyebrow: str, title: str, subtitle: str = "") -> None:
    sub = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    st.html(
        f'<div class="hero"><div class="eyebrow">{escape(eyebrow)}</div>'
        f'<div class="title">{escape(title)}</div>{sub}</div>'
    )


def kpi(label: str, value: str, sub: str = "", small: bool = False) -> None:
    cls = "value small" if small else "value"
    sub_html = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    st.html(
        f'<div class="kpi"><div class="accent"></div><div class="label">{escape(label)}</div>'
        f'<div class="{cls}">{escape(value)}</div>{sub_html}</div>'
    )


def kpi_row(items: list[dict]) -> None:
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            kpi(**item)


def callout(text: str, warn: bool = False) -> None:
    st.html(f'<div class="callout{" warn" if warn else ""}">{text}</div>')


def how(key: str | list[str], meta: dict, title: str = "Comment c'est calculé") -> None:
    keys = [key] if isinstance(key, str) else key
    with st.expander(title):
        st.markdown("\n\n".join(explain(k, **meta) for k in keys))


def form_badges(results: str) -> str:
    labels = {"V": "Victoire", "N": "Nul", "D": "Défaite"}
    return "".join(f'<span class="res {r}" title="{labels[r]}" aria-label="{labels[r]}">{r}</span>' for r in results)


def result_color(r: str) -> str:
    return RESULT_COLORS.get(r, "#94A3B8")


def section(title: str, caption: str = "") -> None:
    st.subheader(title)
    if caption:
        st.caption(caption)


def fmt_m(x: float) -> str:
    return f"{x:,.0f} M€".replace(",", " ")


def fmt_pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f} %"


def fmt_signed(x: float, digits: int = 1) -> str:
    return f"{x:+.{digits}f}".replace("-", "−")


def names_list(names: list[str]) -> str:
    return " · ".join(names)


def no_data(msg: str = "Pas encore de données pour cette section.") -> None:
    st.info(msg)


def team_rows_first(df: pd.DataFrame, team_id: int) -> pd.DataFrame:
    return pd.concat([df[df["team_id"] == team_id], df[df["team_id"] != team_id]])


def prob_bar(p_dom: float, p_nul: float, p_ext: float) -> str:
    def seg(cls: str, p: float, label: str) -> str:
        return f'<div class="{cls}" style="flex:{max(p, 0.04):.3f}" title="{label} {p:.0%}">{p:.0%}</div>'

    return (
        f'<div class="pbar" role="img" aria-label="Victoire domicile {p_dom:.0%}, nul {p_nul:.0%}, '
        f'victoire extérieur {p_ext:.0%}">{seg("h", p_dom, "Domicile")}{seg("d", p_nul, "Nul")}'
        f'{seg("a", p_ext, "Extérieur")}</div><div class="plegend"><span>Dom.</span><span>Nul</span>'
        f"<span>Ext.</span></div>"
    )
