"""Catalogue des saisons (passées et en cours), identité des coachs d'une saison à l'autre et données disponibles.

Ce module ne charge aucune saison : il liste des dossiers et lit des `meta.json`. Les pseudos de coach passent tous
par `coach_key`, seul endroit où l'on dit que deux pseudos désignent la même personne.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from mpg.forecast.evaluation import season_dirs
from mpg.loader import DEFAULT_DATA_DIR, League

COACH_ALIASES = {"vincentprono92": "vincentmouly"}
CURRENT_FALLBACK_KEY = "Saison en cours"
_YEARS = re.compile(r"^(\d{4})-(\d{4})$")


@dataclass(frozen=True)
class Season:
    """Une saison : sa clé (« 2025-2026 »), son dossier de données, et le `meta.json` des saisons passées."""

    key: str
    path: Path
    current: bool
    meta: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def label(self) -> str:
        return self.key

    @property
    def short(self) -> str:
        """« 25-26 » pour « 2025-2026 » ; la clé telle quelle si elle n'a pas ce format."""
        m = _YEARS.match(self.key)
        return f"{m.group(1)[2:]}-{m.group(2)[2:]}" if m else self.key


def _read_meta(path: Path) -> dict:
    try:
        return json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"meta.json illisible dans {path} : {exc}") from exc


def list_seasons(current: Path = DEFAULT_DATA_DIR) -> list[Season]:
    """Saisons passées de la plus ancienne à la plus récente, puis la saison en cours (sans rien charger)."""
    dirs = season_dirs(current)
    past = []
    for name, path in dirs.items():
        if path == current:
            continue
        meta = _read_meta(path)
        past.append(Season(key=meta.get("saison") or name.split("_")[0], path=path, current=False, meta=meta))
    last_years = _YEARS.match(past[-1].key) if past else None
    key = f"{int(last_years.group(2))}-{int(last_years.group(2)) + 1}" if last_years else CURRENT_FALLBACK_KEY
    return [*past, Season(key=key, path=current, current=True)]


def season_by_key(key: str, seasons: list[Season] | None = None) -> Season:
    """La saison de clé `key` ; `KeyError` si elle n'existe pas."""
    seasons = list_seasons() if seasons is None else seasons
    for season in seasons:
        if season.key == key:
            return season
    raise KeyError(f"Saison inconnue : {key!r} (saisons disponibles : {', '.join(s.key for s in seasons)})")


def coach_key(pseudo: str) -> str:
    """Pseudo canonique d'un coach : une même personne a pu changer de pseudo entre deux saisons."""
    return COACH_ALIASES.get(pseudo, pseudo)


def coach_by_team(league: League) -> dict[int, str]:
    """Pseudo canonique du coach de chaque équipe, par `team_id`."""
    return {int(t): coach_key(str(c)) for t, c in zip(league.teams["team_id"], league.teams["coach"])}


def team_of(league: League, coach: str) -> int | None:
    """`team_id` de l'équipe d'un coach dans cette saison (pseudo quelconque ou canonique), `None` s'il n'y joue pas."""
    wanted = coach_key(coach)
    return next((t for t, c in coach_by_team(league).items() if c == wanted), None)


@dataclass(frozen=True)
class Capabilities:
    """Ce que les données d'une saison permettent d'afficher."""

    cote: bool
    stats_pl: bool
    fpl: bool
    matchs_a_venir: bool
    calendrier_pl: bool
    meilleurs_joueurs: bool
    forme_site: bool
    president_stade: bool
    effectif_fin_saison: bool

    @property
    def terminee(self) -> bool:
        return not self.matchs_a_venir


def capabilities(league: League, meta: dict | None = None) -> Capabilities:
    """Capacités d'une saison, lues dans ses données (et dans son `meta.json` pour l'effectif de fin de saison)."""
    club_results = league.club_results
    return Capabilities(
        cote=bool(league.players["cote"].notna().any()),
        stats_pl=bool(league.players["buts_reels_saison"].notna().any()),
        fpl=league.fpl_players is not None,
        matchs_a_venir=bool((league.fixtures["statut"] == "a_venir").any()),
        calendrier_pl=club_results is not None and bool((club_results["statut"] != "joue").any()),
        meilleurs_joueurs=not league.best_players.empty,
        forme_site=bool(league.teams["forme"].notna().any()),
        president_stade=bool(league.teams["president"].notna().any()),
        effectif_fin_saison="fin de saison" in str((meta or {}).get("players_csv", "")),
    )


def limits(caps: Capabilities) -> list[str]:
    """Une phrase courte par limite des données, pour le bandeau « Saison passée, données partielles »."""
    messages = [
        (not caps.cote, "Pas de cote MPG : la force des effectifs se calcule sur les prix d'enchère."),
        (
            not caps.stats_pl,
            "Pas de statistiques de Premier League sur la saison (note réelle, buts, titularisations).",
        ),
        (not caps.fpl, "Pas de données FPL (probabilité de jouer, forme des joueurs)."),
        (not caps.calendrier_pl, "Pas de calendrier à venir de Premier League."),
        (
            caps.effectif_fin_saison,
            "Effectifs de fin de saison : les joueurs partis en cours de route n'y figurent plus.",
        ),
        (not caps.meilleurs_joueurs, "Pas de meilleurs joueurs par match."),
    ]
    return [text for active, text in messages if active]
