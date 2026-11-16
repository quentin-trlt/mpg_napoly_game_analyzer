from html import escape

import pandas as pd
import streamlit as st

from app.theme import RESULT_COLORS, TEXT_2
from mpg.glossary import explain

ROW_PX = 35
MAX_SHORT_COLUMNS = 5
DEFAULT_PROB_LABELS = ("Dom.", "Nul", "Ext.")
CHIP_TONES = (None, "good", "bad")
ALERT_TONES = ("good", "warn", "bad", "mid")
MEDAL_CLASSES = {1: "gold", 2: "silver", 3: "bronze"}


def hero(eyebrow: str, title: str, subtitle: str = "") -> None:
    sub = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    st.html(
        f'<div class="hero"><div class="eyebrow">{escape(eyebrow)}</div>'
        f'<div class="title">{escape(title)}</div>{sub}</div>'
    )


def _stat(label: str, value: str, sub: str = "", small: bool = False, me: bool = False) -> str:
    cls = "value small" if small else "value"
    sub_html = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    return (
        f'<div class="stat{" me" if me else ""}"><div class="label">{escape(label)}</div>'
        f'<div class="{cls}">{escape(value)}</div>{sub_html}</div>'
    )


def kpi_row(items: list[dict]) -> None:
    cells = "".join(_stat(**item) for item in items)
    st.html(f'<div class="stats" style="--n:{len(items)}">{cells}</div>')


def stat_grid(cells: list[str], per_row: int = 4) -> str:
    pad = (-len(cells)) % per_row
    filler = '<div class="stat" aria-hidden="true"></div>' * pad
    return f'<div class="stats" style="--n:{per_row}">{"".join(cells)}{filler}</div>'


def fixture_grid(cards: list[str], cols: int) -> None:
    st.html(f'<div class="fixtures" style="--cols:{cols}">{"".join(cards)}</div>')


def rank_tone(rank: int, n: int) -> str:
    return "tone-good" if rank <= 3 else "tone-bad" if rank > n - 3 else "tone-mid"


def table_height(n_rows: int) -> int:
    return ROW_PX * (n_rows + 1) + 3


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
    return RESULT_COLORS.get(r, TEXT_2)


def section(title: str, caption: str = "") -> None:
    st.subheader(title, anchor=False)
    if caption:
        st.caption(caption)


def fmt_m(x: float) -> str:
    return f"{x:,.0f} M€".replace(",", " ")


def fmt_pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f} %"


def fmt_signed(x: float, digits: int = 1) -> str:
    return f"{x:+.{digits}f}".replace("-", "−")


def names_list(names: list[str]) -> str:
    return ", ".join(names)


def no_data(msg: str = "Pas encore de données pour cette section.") -> None:
    st.info(msg)


def team_rows_first(df: pd.DataFrame, team_id: int) -> pd.DataFrame:
    return pd.concat([df[df["team_id"] == team_id], df[df["team_id"] != team_id]])


def prob_bar(p_dom: float, p_nul: float, p_ext: float, labels: tuple[str, str, str] = DEFAULT_PROB_LABELS) -> str:
    default = tuple(labels) == DEFAULT_PROB_LABELS
    titles = ("Domicile", "Nul", "Extérieur") if default else labels
    spoken = ("Victoire domicile", "nul", "victoire extérieur") if default else labels

    def seg(cls: str, p: float, label: str) -> str:
        return f'<div class="{cls}" style="flex:{max(p, 0.04):.3f}" title="{escape(label)} {p:.0%}">{p:.0%}</div>'

    aria = ", ".join(f"{escape(t)} {p:.0%}" for t, p in zip(spoken, (p_dom, p_nul, p_ext)))
    legend = "".join(f"<span>{escape(label)}</span>" for label in labels)
    return (
        f'<div class="pbar" role="img" aria-label="{aria}">{seg("h", p_dom, titles[0])}{seg("d", p_nul, titles[1])}'
        f'{seg("a", p_ext, titles[2])}</div><div class="plegend">{legend}</div>'
    )


def rank_list(table: pd.DataFrame, team_id: int | None, coach_by_team: dict[int, str]) -> str:
    rows = []
    for r in table.itertuples():
        me = " me" if r.team_id == team_id else ""
        diff = f"{int(r.diff):+d}".replace("-", "−")
        coach = escape(str(coach_by_team.get(r.team_id, "")))
        forme = r.forme if isinstance(r.forme, str) else ""
        rows.append(
            f'<div class="r{me}"><div class="pos">{int(r.rang)}</div>'
            f'<div class="minw0"><div class="who">{escape(str(r.team_name))}</div>'
            f'<div class="sub">{coach} · {int(r.g)}V {int(r.n)}N {int(r.p)}D · {diff}</div></div>'
            f'<div class="side hide-s">{form_badges(forme)}</div>'
            f'<div class="big">{int(r.pts)}<small>pts</small></div></div>'
        )
    return f'<div class="ranks" role="table" aria-label="Classement">{"".join(rows)}</div>'


def next_match(when: str, value: str, value_label: str, detail_html: str, bar_html: str = "") -> str:
    return (
        f'<div class="next"><div class="when">{escape(when)}</div>'
        f'<div class="odds">{escape(value)}<span>{escape(value_label)}</span></div>'
        f'<div class="line">{detail_html}</div>{bar_html}</div>'
    )


def alert(icon: str, text_html: str, detail: str = "", tone: str = "warn") -> str:
    if tone not in ALERT_TONES:
        raise ValueError(f"Ton d'alerte inconnu : {tone!r} (attendu : {', '.join(ALERT_TONES)})")
    sub = f"<span>{escape(detail)}</span>" if detail else ""
    return (
        f'<div class="alert tone-{tone}"><div class="ic" aria-hidden="true">{escape(icon)}</div>'
        f'<div class="tx">{text_html}{sub}</div></div>'
    )


def alerts(items: list[str]) -> str:
    return f'<div class="alerts">{"".join(items)}</div>'


def chip(text: str, tone: str | None = None, off: bool = False) -> str:
    if tone not in CHIP_TONES:
        raise ValueError(f"Ton de pastille inconnu : {tone!r} (attendu : None, 'good' ou 'bad')")
    cls = "chip" + (f" {tone}" if tone else "") + (" off" if off else "")
    return f'<span class="{cls}">{escape(text)}</span>'


def chips(items: list[str | dict]) -> str:
    return "".join(chip(item) if isinstance(item, str) else chip(**item) for item in items)


def medal(rank: float | None, n: int | None = None) -> str:
    if rank is None or rank != rank:
        return '<span class="medal none" aria-label="n\'a pas joué">·</span>'
    rank = int(rank)
    cls = MEDAL_CLASSES.get(rank)
    of = f"<small>/{n}</small>" if n else ""
    return f'<span class="medal{f" {cls}" if cls else ""}">{rank}{of}</span>'


def grid(cells: list[str], template: str) -> str:
    return f'<div class="grid" style="--tpl:{escape(template)}">{"".join(cells)}</div>'


def short_table(
    df: pd.DataFrame,
    columns: list[str],
    *,
    more: str = "Toutes les colonnes",
    column_config: dict | None = None,
    **kwargs,
) -> None:
    if len(columns) > MAX_SHORT_COLUMNS:
        raise ValueError(
            f"short_table accepte {MAX_SHORT_COLUMNS} colonnes au plus, {len(columns)} reçues : {', '.join(columns)}"
        )
    kwargs.setdefault("hide_index", True)
    config = column_config or {}
    st.dataframe(df[columns], column_config={c: config[c] for c in columns if c in config} or None, **kwargs)
    if len(df.columns) > len(columns):
        with st.expander(more):
            st.dataframe(df, hide_index=kwargs["hide_index"], column_config=config or None)


def limit_banner(caps: list[str], title: str = "Saison passée, données partielles") -> None:
    if not caps:
        return
    items = "".join(f"<li>{escape(c)}</li>" for c in caps)
    st.html(f'<div class="banner"><div class="title">{escape(title)}</div><ul>{items}</ul></div>')


def empty_state(title: str, reason: str) -> None:
    st.html(
        f'<div class="empty"><div class="title">{escape(title)}</div><div class="reason">{escape(reason)}</div></div>'
    )
