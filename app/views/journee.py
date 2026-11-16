from html import escape

import pandas as pd
import streamlit as st

from app.components import (
    alert,
    alerts,
    chips,
    empty_state,
    fmt_pct,
    hero,
    kpi_row,
    next_match,
    prob_bar,
    rank_list,
    section,
)
from app.navigation import page_link
from app.state import get_forecast_light
from mpg.analysis import Analysis
from mpg.premier_league import LOCAL_TZ, club_form
from mpg.seasons import coach_by_team

STATUS = {"blesse": "blessé", "suspendu": "suspendu", "incertain": "incertain"}
STATUS_TONES = {"blesse": "bad", "suspendu": "bad", "incertain": "warn"}
TOP_PLAYERS = 12
NON_BREAKING_HYPHEN = "\u2011"
DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _rank(n: int) -> str:
    return "1er" if n == 1 else f"{n}e"


def _score(text: object) -> str:
    return str(text).replace("-", NON_BREAKING_HYPHEN)


def likely_rank(rank_probs: pd.DataFrame, team_id: int) -> tuple[int, float]:
    """Rang final le plus probable de l'équipe et sa probabilité."""
    dist = rank_probs.loc[team_id]
    return int(dist.idxmax()), float(dist.max())


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 and not word.endswith('s') else ''}"


def _when(date: pd.Timestamp, heure: object) -> str:
    text = f"{DAYS[date.weekday()]} {date:%d/%m}"
    return f"{text} à {heure}" if isinstance(heure, str) else text


def _my_fixture(a: Analysis, team_id: int) -> pd.Series | None:
    fx = a.league.fixtures
    todo = fx[(fx["statut"] != "joue") & ((fx["home_team_id"] == team_id) | (fx["away_team_id"] == team_id))]
    return None if todo.empty else todo.sort_values("gw").iloc[0]


def _row(pos: str, who: str, sub: str, side: str, big: str, small: bool = False) -> str:
    return (
        f'<div class="r"><div class="pos{" small" if small else ""}">{escape(pos)}</div>'
        f'<div class="minw0"><div class="who">{escape(who)}</div><div class="sub">{escape(sub)}</div></div>'
        f'<div class="side hide-s">{escape(side)}</div><div class="big">{escape(big)}</div></div>'
    )


def _ranks(rows: list[str]) -> str:
    return f'<div class="ranks">{"".join(rows)}</div>'


def _deadline(a: Analysis) -> pd.Timestamp | None:
    results = a.league.club_results
    if results is None:
        return None
    todo = results[results["statut"] == "a_venir"]
    return None if todo.empty else todo["date"].min().tz_convert(LOCAL_TZ)


def _deadline_alert(a: Analysis) -> str | None:
    deadline = _deadline(a)
    if deadline is None:
        return None
    return alert(
        "⏱",
        f"Compo à valider avant <b>{DAYS[deadline.weekday()]} {deadline:%d/%m à %H:%M}</b>",
        "Coup d'envoi du premier match de Premier League de la journée.",
        "good",
    )


def _squad_alerts(a: Analysis, team_id: int) -> list[str]:
    squad = a.league.players[a.league.players["team_id"] == team_id]
    absent = squad[squad["statut_performance"].isin(STATUS)].sort_values("enchere", ascending=False)
    news: dict[str, str] = {}
    if a.league.fpl_players is not None:
        news = a.league.fpl_players.dropna(subset=["news"]).set_index("player_key")["news"].to_dict()
    return [
        alert(
            "!",
            f"<b>{escape(p.joueur)}</b> est {STATUS[p.statut_performance]}",
            f"{p.poste}, {p.club}, acheté {p.enchere:.0f} M€"
            + (f" · Selon la FPL : {news[p.player_key]}" if p.player_key in news else ""),
            STATUS_TONES[p.statut_performance],
        )
        for p in absent.itertuples()
    ]


def _opponent_alert(a: Analysis, opp_id: int) -> str | None:
    remaining = a.bonus_remaining
    if remaining is None:
        return None
    left = remaining[(remaining["team_id"] == opp_id) & (remaining["restants"] > 0)]
    if left.empty:
        return None
    listing = ", ".join(f"{r.bonus} ×{r.restants}" if r.restants > 1 else r.bonus for r in left.itertuples())
    count = int(left["restants"].sum())
    return alert(
        "→", f"<b>{escape(a.league.team_names[opp_id])}</b> a encore {_plural(count, 'bonus')}", listing, "mid"
    )


def _bonus_chips(a: Analysis, team_id: int) -> str | None:
    remaining = a.bonus_remaining
    if remaining is None:
        return None
    mine = remaining[remaining["team_id"] == team_id]
    if mine.empty:
        return None
    items = [
        {
            "text": f"{r.bonus} {max(r.restants, 0)}" + ("" if r.hors_dotation else f"/{r.dotation}"),
            "off": r.restants <= 0,
        }
        for r in mine.itertuples()
    ]
    return f"<div>{chips(items)}</div>"


def _weekend(a: Analysis, team_id: int) -> pd.DataFrame | None:
    results = a.league.club_results
    if results is None:
        return None
    squad = a.player_value[a.player_value["team_id"] == team_id].dropna(subset=["note_retrecie"])
    form = club_form(results)
    form["quand"] = form["prochain_date"].dt.tz_convert(LOCAL_TZ)
    cols = ["club", "prochain_adversaire_short", "prochain_domicile", "quand"]
    out = squad.merge(form[cols], on="club", how="left")
    best = out.sort_values("note_retrecie", ascending=False).head(TOP_PLAYERS)
    return best.sort_values(["quand", "note_retrecie"], ascending=[True, False])


def _weekend_rows(players: pd.DataFrame) -> str:
    rows = []
    for p in players.itertuples():
        if pd.isna(p.quand):
            match = "pas de match à venir"
        else:
            place = "dom." if p.prochain_domicile else "ext."
            when = f"{DAYS[p.quand.weekday()][:3]}. {p.quand:%H:%M}"
            match = f"contre {p.prochain_adversaire_short} ({place}) · {when}"
        rows.append(_row(str(p.poste), p.joueur, f"{p.club} {match}", "", f"{p.note_retrecie:.1f}", small=True))
    return _ranks(rows)


def _left_column(a: Analysis, team_id: int, opp_id: int) -> None:
    items = [_deadline_alert(a)]
    squad_alerts = _squad_alerts(a, team_id)
    items += squad_alerts
    items.append(_opponent_alert(a, opp_id))
    if not squad_alerts:
        items.append(alert("✓", "Aucun de tes joueurs n'est blessé, suspendu ou incertain", tone="good"))
    section("À savoir avant de valider ta compo")
    st.html(alerts([i for i in items if i]))

    chips_html = _bonus_chips(a, team_id)
    if chips_html is not None:
        mine = a.bonus_remaining[a.bonus_remaining["team_id"] == team_id]
        stock = int(mine["restants"].clip(lower=0).sum())
        left = a.league.n_gw - a.league.last_gw
        section("Mes bonus", f"{_plural(stock, 'bonus')} pour {_plural(left, 'journée')} à jouer.")
        st.html(chips_html)

    weekend = _weekend(a, team_id)
    if weekend is not None and not weekend.empty:
        section(
            "Mes joueurs ce week-end",
            f"Les {len(weekend)} mieux notés de ton effectif et leur match de Premier League, "
            "dans l'ordre des coups d'envoi.",
        )
        st.html(_weekend_rows(weekend))


def _my_match_card(mp: pd.Series, home: bool, n_models: int) -> str:
    p_win, p_loss = (mp["p_dom"], mp["p_ext"]) if home else (mp["p_ext"], mp["p_dom"])
    source = "d'après les modèles de l'app" if n_models < 2 else f"d'après les {n_models} modèles de l'app"
    detail = (
        f"Nul <b>{fmt_pct(mp['p_nul'])}</b>, défaite <b>{fmt_pct(p_loss)}</b>. "
        f"Score le plus probable : <b>{escape(_score(mp['score_probable']))}</b>."
    )
    bar = prob_bar(mp["p_dom"], mp["p_nul"], mp["p_ext"], (mp["home_team"], "Nul", mp["away_team"]))
    return next_match(f"Ton match, {source}", fmt_pct(p_win), "de chances de gagner", detail, bar)


def _kpis(me: pd.Series, rank: int, pts: int, likely: tuple[int, float]) -> list[dict]:
    return [
        {"label": "Classement", "value": _rank(rank), "sub": _plural(pts, "point"), "me": True},
        {"label": "Chances de titre", "value": fmt_pct(me["p_titre"]), "sub": f"podium {fmt_pct(me['p_podium'])}"},
        {
            "label": "Points en fin de saison",
            "value": f"{me['pts_moy']:.0f}",
            "sub": f"entre {me['pts_p05']:.0f} et {me['pts_p95']:.0f} dans 9 cas sur 10",
        },
        {
            "label": "Fin de saison la plus probable",
            "value": _rank(likely[0]),
            "sub": f"dans {fmt_pct(likely[1])} des cas",
        },
    ]


def _other_matches(probs: pd.DataFrame, fixture: pd.Series) -> str:
    same_day = probs[probs["gw"] == fixture["gw"]]
    mine = (same_day["home_team_id"] == fixture["home_team_id"]) & (same_day["away_team_id"] == fixture["away_team_id"])
    rows = [
        _row(
            "",
            f"{m.home_team} – {m.away_team}",
            f"Domicile {fmt_pct(m.p_dom)} · nul {fmt_pct(m.p_nul)} · extérieur {fmt_pct(m.p_ext)}",
            "score probable",
            _score(m.score_probable),
        )
        for m in same_day[~mine].itertuples()
    ]
    return _ranks(rows)


def _season_over(a: Analysis, team_id: int, coaches: dict[int, str]) -> None:
    mine = a.standings.set_index("team_id").loc[team_id]
    names = a.league.team_names
    hero(
        f"Saison {a.meta['saison']}", f"{names[team_id]} termine {_rank(int(mine['rang']))}", "La saison est terminée."
    )
    section("Classement final")
    st.html(rank_list(a.standings, team_id, coaches))


def render(a: Analysis, team_id: int) -> None:
    if not a.meta["saison_en_cours"]:
        empty_state(
            "Cette page ne concerne que la saison en cours",
            "Pour une saison passée, la Ligue montre le classement final et les matchs.",
        )
        page_link("ligue", "Ouvrir la Ligue", icon=":material/leaderboard:")
        return

    coaches = coach_by_team(a.league)
    fixture = _my_fixture(a, team_id)
    if fixture is None:
        _season_over(a, team_id, coaches)
        return

    names = a.league.team_names
    mine = a.standings.set_index("team_id").loc[team_id]
    rank, pts = int(mine["rang"]), int(mine["pts"])
    gap = int(a.standings.iloc[0]["pts"] - pts)
    home = int(fixture["home_team_id"]) == team_id
    opp_id = int(fixture["away_team_id"] if home else fixture["home_team_id"])
    if gap == 0:
        lead = "en tête" if rank == 1 else "à égalité de points avec le leader"
        subtitle = f"Tu es {lead} avec {_plural(pts, 'point')}."
    else:
        subtitle = f"Tu es {_rank(rank)} avec {_plural(pts, 'point')}, à {_plural(gap, 'point')} du leader."
    hero(
        f"Journée {int(fixture['gw'])} sur {a.league.n_gw} · {_when(fixture['date'], fixture.get('heure'))}",
        f"{names[team_id]} {'reçoit' if home else 'se déplace chez'} {names[opp_id]}",
        subtitle,
    )

    next_slot = st.container()
    kpi_slot = st.container()
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        _left_column(a, team_id, opp_id)
    with right:
        section("Classement")
        st.html(rank_list(a.standings, team_id, coaches))
        others_slot = st.container()

    with next_slot:
        forecast = get_forecast_light()
    draws, baseline = forecast["draws"], forecast["baseline"]
    if baseline is None:
        return
    probs = baseline.match_probs
    row = probs[(probs["home_team_id"] == fixture["home_team_id"]) & (probs["away_team_id"] == fixture["away_team_id"])]
    n_models = sum(w > 0 for w in draws.weights.values()) if draws.weights else len(draws.by_model)
    if not row.empty:
        with next_slot:
            st.html(_my_match_card(row.iloc[0], home, n_models))
    with kpi_slot:
        kpi_row(
            _kpis(
                baseline.summary.set_index("team_id").loc[team_id],
                rank,
                pts,
                likely_rank(baseline.rank_probs, team_id),
            )
        )
    with others_slot:
        section(f"Les autres matchs de la journée {int(fixture['gw'])}")
        st.html(_other_matches(probs, fixture))
