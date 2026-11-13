"""Page privée du coach : compo conseillée pour le prochain match MPG (lancée par `coach_app.py`, en local)."""

import json
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from app.components import callout, hero, kpi_row, prob_bar, section, table_height
from app.state import data_signature, get_analysis
from app.theme import BORDER, DISPLAY, LINE_COLORS, MUTED, SURFACE, SURFACE_2, TEXT, TEXT_2
from mpg import fpl
from mpg.analysis import Analysis
from mpg.coach.projection import OVERRIDE_LEVELS
from mpg.coach.recommend import Recommendation, naive_lineup, recommend
from mpg.coach.rules import Lineup, slots_of
from mpg.forecast.bonus import F424, MCDO, MIROIR, TONTON

STATE_DIR = Path(__file__).resolve().parents[2] / ".coach"
SETTINGS = "settings.json"
OVERRIDES = "overrides.json"
FPL_OVERRIDES = "fpl_overrides.csv"
AUTO = "auto"
DRAW_CHOICES = (2000, 4000, 8000)
LINE_ORDER = ("A", "M", "D", "G")

CSS = f"""
<style>
.pitch {{ background: linear-gradient(180deg, rgba(25,158,112,0.10), rgba(25,158,112,0.04)); border: 1px solid {BORDER};
    border-radius: 14px; padding: 14px 12px; display: flex; flex-direction: column; gap: 12px; }}
.pitch .line {{ display: flex; justify-content: center; gap: 10px; flex-wrap: wrap; }}
.pp {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; padding: 8px 10px 7px; width: 132px;
    min-width: 0; border-top: 3px solid var(--tone); position: relative; }}
.pp .nm {{ color: {TEXT}; font-weight: 600; font-size: .86rem; line-height: 1.2; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; }}
.pp .mt {{ color: {MUTED}; font-size: .72rem; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.pp .nb {{ display: flex; justify-content: space-between; align-items: baseline; margin-top: 3px; }}
.pp .nt {{ font-family: {DISPLAY}; font-size: 1.25rem; font-weight: 600; color: {TEXT}; font-variant-numeric: tabular-nums; }}
.pp .pj {{ font-size: .74rem; font-weight: 600; color: var(--tone); }}
.pp .badge {{ position: absolute; top: -9px; right: 8px; font-size: .68rem; font-weight: 700; border-radius: 999px;
    padding: 1px 7px; background: {TEXT}; color: #0B1120; }}
.pp .badge.mcdo {{ background: #FAB219; right: auto; left: 8px; }}
.bench {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; padding: 6px 16px; }}
.bench .b {{ display: grid; grid-template-columns: 22px 30px minmax(0, 1fr) auto auto; gap: 10px; align-items: center;
    padding: 8px 0; border-top: 1px solid {BORDER}; font-size: .86rem; color: {TEXT}; }}
.bench .b:first-child {{ border-top: none; }}
.bench .ix {{ color: {MUTED}; font-variant-numeric: tabular-nums; }}
.bench .ln {{ font-size: .7rem; font-weight: 700; border-radius: 5px; text-align: center; padding: 1px 0; color: #0B1120; }}
.bench .sub {{ color: {MUTED}; font-size: .74rem; }}
.bench .v {{ font-variant-numeric: tabular-nums; color: {TEXT_2}; font-size: .8rem; }}
.tac {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 12px; margin-top: 8px;
    font-size: .85rem; color: {TEXT}; }}
.tac b {{ font-family: {DISPLAY}; font-size: 1rem; }}
@media (max-width: 640px) {{ .pp {{ width: 104px; padding: 7px 8px 6px; }} .pp .nt {{ font-size: 1.1rem; }} }}
</style>
"""


def _read_json(name: str, default):
    try:
        return json.loads((STATE_DIR / name).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _write_json(name: str, data) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return path


def _fpl_overrides() -> dict[str, int]:
    path = STATE_DIR / FPL_OVERRIDES
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["player_key"], df["element_id"].astype(int)))


@st.cache_resource(show_spinner="Téléchargement des données FPL (environ 200 joueurs la première fois)…", max_entries=2)
def _load_fpl(signature: tuple, token: int) -> dict:
    league = get_analysis().league
    client = fpl.FplClient(refresh=token > 0)
    try:
        els = fpl.elements(client.bootstrap())
        mapping = fpl.match_players(league.players, els, _fpl_overrides())
        players = mapping[["player_key", "element_id"]].merge(els, on="element_id", how="left")
        history = {int(e): fpl.history(client.element_summary(int(e))) for e in players["element_id"].dropna()}
    except fpl.FplError as exc:
        return {"players": None, "history": {}, "mapping": None, "error": str(exc), "fetched_at": None}
    return {
        "players": players,
        "history": history,
        "mapping": mapping,
        "error": None,
        "fetched_at": client.fetched_at(),
    }


@st.cache_resource(show_spinner="Optimisation de la compo et du plan de bonus…", max_entries=6)
def _recommend(signature: tuple, team_id: int, overrides: str, token: int, n_draws: int, _fpl: dict) -> Recommendation:
    return recommend(get_analysis(), team_id, _fpl["players"], _fpl["history"], json.loads(overrides), n_draws=n_draws)


def _fmt(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f}"


def _tone(p: float) -> str:
    return "#22C55E" if p >= 0.85 else "#FAB219" if p >= 0.5 else "#E66767"


def _short(name: str) -> str:
    parts = name.split()
    return name if len(name) <= 16 or len(parts) == 1 else f"{parts[0][0]}. {' '.join(parts[1:])}"


def _card(rec: Recommendation, r: int, lu: Lineup) -> str:
    row = rec.proj.loc[r]
    badges = ""
    if r == lu.captain:
        badges += '<span class="badge">C</span>'
    if lu.bonus == MCDO and r == lu.mcdo_target:
        badges += '<span class="badge mcdo">+1</span>'
    vs = (
        f"{row['club']} · {row['adversaire_pl']}"
        if isinstance(row["adversaire_pl"], str)
        else f"{row['club']} · sans match"
    )
    return (
        f'<div class="pp" style="--tone:{_tone(row["p_joue"])}" title="{escape(str(row["joueur"]))}">{badges}'
        f'<div class="nm">{escape(_short(str(row["joueur"])))}</div><div class="mt">{escape(vs)}</div>'
        f'<div class="nb"><span class="nt">{_fmt(row["note_attendue"], 1)}</span>'
        f'<span class="pj">{row["p_joue"]:.0%}</span></div></div>'
    )


def _pitch(rec: Recommendation, lu: Lineup) -> str:
    slots = slots_of(lu.formation)
    lines = []
    for line in LINE_ORDER:
        cards = "".join(_card(rec, r, lu) for r, s in zip(lu.starters, slots) if s == line)
        lines.append(f'<div class="line">{cards}</div>')
    return f'<div class="pitch">{"".join(lines)}</div>'


def _bench(rec: Recommendation, lu: Lineup) -> str:
    rows = []
    for i, r in enumerate(lu.bench, start=1):
        p = rec.proj.loc[r]
        line = p["poste_groupe"]
        rows.append(
            f'<div class="b"><span class="ix">{i}</span>'
            f'<span class="ln" style="background:{LINE_COLORS[line]}">{line}</span>'
            f'<span>{escape(str(p["joueur"]))}<div class="sub">{escape(str(p["club"]))}</div></span>'
            f'<span class="v">{_fmt(p["note_attendue"], 1)}</span>'
            f'<span class="v" style="color:{_tone(p["p_joue"])}">{p["p_joue"]:.0%}</span></div>'
        )
    return f'<div class="bench">{"".join(rows)}</div>'


def _tactics(rec: Recommendation, lu: Lineup) -> str:
    if not lu.tactics:
        return '<div class="tac">Aucun remplacement tactique ne rapporte de points sur ce match.</div>'
    items = [
        f'<div class="tac">Si <b>{escape(rec.name(t.out))}</b> a moins de <b>{_fmt(t.threshold, 1)}</b> '
        f"(ou ne joue pas), <b>{escape(rec.name(t.inp))}</b> entre.</div>"
        for t in lu.tactics
    ]
    return "".join(items)


def _changes(rec: Recommendation, lu: Lineup, ref: Lineup) -> str:
    out_ = [rec.name(r) for r in ref.starters if r not in lu.starters]
    in_ = [rec.name(r) for r in lu.starters if r not in ref.starters]
    if not out_ and not in_:
        return "même 11"
    return f"+ {', '.join(in_)} / − {', '.join(out_)}"


def _bonus_label(rec: Recommendation, key: str | None) -> str:
    return "Aucun" if key is None else rec.bonus_names.get(key, key)


def _team_selector(a: Analysis) -> int:
    names = a.league.team_names
    order = sorted(names, key=lambda t: names[t].lower())
    saved = _read_json(SETTINGS, {}).get("team_id")
    default = order.index(saved) if saved in order else 0
    team_id = st.selectbox("Mon équipe", options=order, index=default, format_func=lambda t: names[t])
    if team_id != saved:
        _write_json(SETTINGS, {**_read_json(SETTINGS, {}), "team_id": int(team_id)})
    return int(team_id)


def _player_editor(rec: Recommendation, team_id: int, overrides: dict[str, float], key: str) -> dict[str, float]:
    p = rec.proj[rec.proj["team_id"] == team_id]
    level_of = {v: k for k, v in OVERRIDE_LEVELS.items()}
    df = pd.DataFrame(
        {
            "player_key": p["player_key"],
            "Joueur": p["joueur"],
            "Poste": p["poste_groupe"],
            "Match PL": [
                f"{c} – {o}" if isinstance(o, str) else f"{c} (pas de match)"
                for c, o in zip(p["club"], p["adversaire_pl"])
            ],
            "P(joue) auto": p["p_joue_auto"],
            "Surcharge": [level_of.get(overrides.get(k), AUTO) for k in p["player_key"]],
            "P(joue)": p["p_joue"],
            "Note attendue": p["note_attendue"],
            "Buts attendus": p["lambda_buts"] * p["p_joue"],
            "Source": p["source"],
            "News FPL": p.get("news", pd.Series("", index=p.index)).fillna(""),
        }
    ).sort_values(["Poste", "Note attendue"], key=lambda s: s.map("GDMA".index) if s.name == "Poste" else -s)
    edited = st.data_editor(
        df,
        key=key,
        hide_index=True,
        width="stretch",
        height=table_height(len(df)),
        disabled=[c for c in df.columns if c != "Surcharge"],
        column_order=[c for c in df.columns if c != "player_key"],
        column_config={
            "Surcharge": st.column_config.SelectboxColumn(options=[AUTO, *OVERRIDE_LEVELS], required=True),
            "P(joue) auto": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            "P(joue)": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            "Note attendue": st.column_config.NumberColumn(format="%.2f"),
            "Buts attendus": st.column_config.NumberColumn(format="%.2f", help="Buts réels attendus, P(joue) incluse."),
            "News FPL": st.column_config.TextColumn(width="large"),
        },
    )
    new = {k: v for k, v in overrides.items() if k not in set(p["player_key"])}
    for k, level in zip(edited["player_key"], edited["Surcharge"]):
        if level != AUTO:
            new[k] = OVERRIDE_LEVELS[level]
    return new


def _freeze(rec: Recommendation, a: Analysis) -> Path:
    lu = rec.best
    s = rec.summary(lu)
    payload = {
        "gele_le": datetime.now().isoformat(timespec="seconds"),
        "journee": rec.gw,
        "equipe": a.league.team_names[rec.team_id],
        "adversaire": a.league.team_names[rec.opp_id],
        "formation": lu.formation,
        "titulaires": [rec.name(r) for r in lu.starters],
        "banc": [rec.name(r) for r in lu.bench],
        "tactiques": rec.tactics_table(lu).to_dict(orient="records"),
        "capitaine": rec.name(lu.captain) if lu.captain is not None else None,
        "bonus": _bonus_label(rec, lu.bonus),
        "cible_mcdo": rec.name(lu.mcdo_target) if lu.mcdo_target is not None else None,
        "points_esperes": round(s["e_pts"], 3),
        "p_victoire": round(float(s["p_v"]), 3),
        "p_nul": round(float(s["p_n"]), 3),
        "p_defaite": round(float(s["p_d"]), 3),
    }
    return _write_json(f"reco_J{rec.gw:02d}.json", payload)


def render(a: Analysis) -> None:
    st.html(CSS)
    names = a.league.team_names
    with st.sidebar:
        team_id = _team_selector(a)
        n_draws = st.select_slider("Tirages Monte Carlo", options=DRAW_CHOICES, value=4000)
        if "fpl_token" not in st.session_state:
            st.session_state["fpl_token"] = 0
        if st.button("Rafraîchir les données FPL", icon=":material/refresh:", width="stretch"):
            st.session_state["fpl_token"] += 1
        st.caption(f"Données MPG jusqu'à la J{a.league.last_gw}.")

    token = st.session_state["fpl_token"]
    signature = data_signature()
    fpl_data = _load_fpl(signature, token)
    with st.sidebar:
        if fpl_data["error"]:
            st.warning(f"FPL indisponible, projection sur les seules données MPG. {fpl_data['error']}")
        elif fpl_data["fetched_at"] is not None:
            st.caption(f"FPL mis à jour le {fpl_data['fetched_at'].astimezone():%d/%m à %H:%M}.")

    overrides = {k: float(v) for k, v in _read_json(OVERRIDES, {}).items()}
    try:
        rec = _recommend(signature, team_id, json.dumps(overrides, sort_keys=True), token, n_draws, fpl_data)
    except ValueError as exc:
        st.info(str(exc))
        return
    lu = rec.best
    s = rec.summary(lu)
    base = rec.summary(rec.lineups[0])
    naive = rec.summary(naive_lineup(rec))
    opp_name = names[rec.opp_id]
    where = "à domicile" if rec.home else "à l'extérieur"

    hero(
        f"Coach · J{rec.gw}",
        f"{names[team_id]} contre {opp_name}",
        f"Match {where}. Les remplacements tactiques sont figés au coup d'envoi du premier match de la journée "
        f"{rec.pl_gw} de Premier League, le {rec.deadline:%d/%m à %H:%M}.",
    )
    kpi_row(
        [
            {
                "label": "Points espérés",
                "value": _fmt(s["e_pts"]),
                "sub": f"± {_fmt(1.96 * s['se'])} · {_fmt(s['e_pts_bonus_adverses'])} si l'adversaire pose ses bonus "
                "au rythme attendu",
                "me": True,
            },
            {
                "label": "Bonus conseillé",
                "value": _bonus_label(rec, rec.bonus),
                "small": True,
                "sub": f"+{_fmt(s['e_pts'] - base['e_pts'])} pt espéré" if rec.bonus else "Mieux vaut le garder",
            },
            {
                "label": "Gain de l'optimisation",
                "value": f"+{_fmt(base['e_pts'] - naive['e_pts'])}",
                "sub": "pt espéré contre le 11 des meilleures notes, sans tactiques",
            },
            {"label": "Formation", "value": lu.formation, "sub": f"Capitaine : {rec.name(lu.captain)}"},
        ]
    )
    st.html(prob_bar(s["p_v"], s["p_n"], s["p_d"]) if rec.home else prob_bar(s["p_d"], s["p_n"], s["p_v"]))

    section("Feuille de match", "Note attendue si le joueur joue · probabilité qu'il joue (au moins une minute en PL).")
    left, right = st.columns([3, 2], gap="medium")
    with left:
        st.html(_pitch(rec, lu))
    with right:
        st.markdown("**Banc, dans l'ordre d'entrée**")
        st.html(_bench(rec, lu))
        st.markdown("**Remplacements tactiques**")
        st.html(_tactics(rec, lu))
        if lu.bonus == MCDO:
            st.caption(f"McDo+ sur {rec.name(lu.mcdo_target)}.")
        if lu.bonus == F424:
            st.caption("Le 424 impose le 4-2-4 : la feuille ci-contre est la meilleure compo dans ce dispositif.")

    section(
        "Bonus",
        "Gain en points espérés de chaque bonus sur chaque match restant. Le plan affecte au plus un bonus par match et "
        "pose chacun là où il rapporte le plus : poser un bonus maintenant coûte l'occasion qu'il aurait eue plus tard.",
    )
    plan = rec.plan.copy()
    plan["Adversaire"] = plan["adversaire_id"].map(names)
    plan["Bonus prévu"] = [_bonus_label(rec, k) for k in plan["bonus"]]
    gain_cols = [k for k in rec.stock if k in plan.columns]
    view = plan[["gw", "Adversaire", "Bonus prévu", "gain", *gain_cols]].rename(
        columns={"gw": "J", "gain": "Gain prévu", **{k: _bonus_label(rec, k) for k in gain_cols}}
    )
    st.dataframe(
        view,
        hide_index=True,
        width="stretch",
        height=table_height(len(view)),
        column_config={
            "Bonus prévu": st.column_config.TextColumn(width="medium"),
            **{c: st.column_config.NumberColumn(format="%.2f") for c in view.columns[3:]},
        },
    )
    if TONTON in rec.stock:
        st.caption(
            "Tonton Pat ne vaut que ce que rapportent les remplacements tactiques adverses : la compo adverse projetée "
            "n'en prévoit qu'au prochain match, son gain est donc nul ou presque sur les suivants."
        )
    if MIROIR in rec.stock and rec.opp_probs:
        probs = ", ".join(
            f"{_bonus_label(rec, k)} {p:.0%}" for k, p in sorted(rec.opp_probs.items(), key=lambda x: -x[1])
        )
        st.caption(f"Bonus possibles de {opp_name} à ce match (stock restant / matchs restants) : {probs}.")

    section("Autres compos", "Recalculées sur des tirages indépendants de ceux de l'optimisation.")
    ref = rec.lineups[0]
    alt = pd.DataFrame(
        [
            {
                "Formation": x.formation,
                "Points espérés": (sx := rec.summary(x))["e_pts"],
                "Écart": sx["e_pts"] - base["e_pts"],
                "P(victoire)": sx["p_v"],
                "Tactiques": len(x.tactics),
                "Changements dans le 11": _changes(rec, x, ref),
            }
            for x in rec.lineups
        ]
    )
    st.dataframe(
        alt,
        hide_index=True,
        width="stretch",
        column_config={
            "Points espérés": st.column_config.NumberColumn(format="%.3f"),
            "Écart": st.column_config.NumberColumn(format="%+.3f"),
            "P(victoire)": st.column_config.NumberColumn(format="percent"),
            "Changements dans le 11": st.column_config.TextColumn(width="large"),
        },
    )

    section(f"Compo probable de {opp_name}", "Supposée optimale contre ma compo de référence, sans bonus.")
    st.html(_pitch(rec, rec.opponent))

    section(
        "Joueurs", "La surcharge remplace la probabilité de jouer calculée (sûr 100 %, probable 80 %, incertain 50 %)."
    )
    tab_me, tab_opp = st.tabs([names[team_id], opp_name])
    with tab_me:
        new_me = _player_editor(rec, team_id, overrides, key=f"edit_{team_id}")
    with tab_opp:
        new = _player_editor(rec, rec.opp_id, new_me, key=f"edit_{rec.opp_id}")
    if new != overrides:
        _write_json(OVERRIDES, new)
        st.rerun()
    if fpl_data["mapping"] is not None:
        unmatched = fpl_data["mapping"][fpl_data["mapping"]["methode"] == "non_apparie"]
        if not unmatched.empty:
            callout(
                "Joueurs sans correspondance FPL (projection sur les données MPG seules) : "
                + escape(", ".join(unmatched["joueur"]))
                + f". Pour forcer un appariement : <code>.coach/{FPL_OVERRIDES}</code> (player_key,element_id).",
                warn=True,
            )

    col_a, col_b = st.columns([1, 3])
    with col_a:
        if st.button("Geler la recommandation", icon=":material/lock:", width="stretch"):
            path = _freeze(rec, a)
            st.toast(f"Recommandation enregistrée : {path.name}")
    with col_b:
        frozen = sorted(STATE_DIR.glob("reco_J*.json")) if STATE_DIR.exists() else []
        if frozen:
            st.caption("Gelées : " + ", ".join(p.stem.replace("reco_", "") for p in frozen))

    with st.expander("Comment c'est calculé"):
        m, pm = rec.model, rec.play_model
        play = (
            f"un logit estimé sur {pm.n_obs} journées FPL des joueurs de la ligue (Brier {pm.brier:.3f})"
            if pm is not None
            else "la part des 5 dernières journées jouées, rétrécie vers le taux de la saison"
        )
        notes = (
            "S'il est titulaire en PL (selon sa part de titularisations), il reçoit sa note estimée de titulaire, tirée "
            "vers celle des titulaires de son poste ; s'il entre en cours de match, la note des remplaçants de son "
            "poste, plus basse et plus resserrée. Le choc de club et le bruit sont estimés sur les titularisations de PL."
            if "p_titulaire_si_joue" in rec.proj
            else f"Note si le joueur joue : note rétrécie (k = {m.k_shrink:.1f})."
        )
        st.markdown(
            f"""
**Moteur de match.** Chaque compo est jouée selon les règles MPG : remplacements tactiques puis automatiques
(même poste, sinon poste inférieur avec −1 par poste sauté, sinon Rotaldo à 2,5), bonus défensif, capitaine,
bonus, buts réels, arrêt du gardien noté 8 ou plus, buts MPG (lignes franchies, −1 puis −0,5, égalité au
domicile), CSC et Rotaldos. Rejoué sur les notes réelles, il retrouve le score exact de tous les matchs déjà joués.

**Joueurs.** P(joue) = disponibilité FPL × {play}. MPG note tout joueur entré en jeu, même une minute. {notes}
Effet du match attendu du club (par but réel pour : A {m.beta_for.get("A", 0):+.2f},
M {m.beta_for.get("M", 0):+.2f}, D {m.beta_for.get("D", 0):+.2f} ; contre : D {m.beta_against.get("D", 0):+.2f},
G {m.beta_against.get("G", 0):+.2f}), multiplié par {m.adj_scale:.2f}, ce qu'un but attendu de plus a rapporté en
moyenne en buts réels cette saison (les prévisions de début de saison, faites sur peu de matchs, en annoncent
moins qu'elles ne promettent), choc commun au club (σ = {m.sigma_club:.2f}), bruit individuel
(σ = {m.sigma_player:.2f}), +{m.goal_bump:.2f} pour un buteur. Buts réels : xG/90 FPL rétréci × minutes attendues ×
difficulté de l'adversaire (Poisson attaque/défense sur les résultats de PL).

**Optimisation.** {rec.draws.n} tirages communs à toutes les compos ; toutes les valeurs affichées sont recalculées
sur {rec.holdout.n} autres tirages. Les remplacements tactiques qui ne rapportent rien sur ces tirages indépendants
sont retirés.

**Limite connue.** Rejoué sur J1-J5 sans information postérieure (`experiments/backtest_engine.py`), le moteur
simule 2,2 buts par équipe et par match contre 2,0 observés (2,3 avec les compos réellement posées), et prédit moins
bien l'issue des matchs que le modèle structurel de l'app principale. Les comparaisons entre compos d'un même match
restent valables (mêmes tirages, règles exactes) ; les probabilités affichées sont à lire comme des ordres de grandeur.
"""
        )
