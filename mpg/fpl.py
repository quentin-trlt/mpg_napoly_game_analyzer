"""Client de l'API publique Fantasy Premier League : disponibilités, temps de jeu et xG par journée.

Les réponses sont mises en cache sur disque (`data/fpl_cache/`) avec une durée de validité. En cas d'échec réseau,
le dernier cache disponible est utilisé, même périmé.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

from mpg.loader import DEFAULT_DATA_DIR
from mpg.text import norm

BASE_URL = "https://fantasy.premierleague.com/api"
USER_AGENT = "Mozilla/5.0 (compatible; mpg-coach)"
CACHE_DIR = DEFAULT_DATA_DIR / "fpl_cache"
TTL = timedelta(hours=6)
CLUB_TO_FPL = {
    "Man. City": "Man City",
    "Man. United": "Man Utd",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham": "Spurs",
}
UNAVAILABLE_STATUS = ("i", "s", "u", "n")
MATCH_THRESHOLD = 0.6
CROSS_CLUB_THRESHOLD = 0.9

log = logging.getLogger(__name__)


class FplError(RuntimeError):
    pass


@dataclass
class FplClient:
    cache_dir: Path = CACHE_DIR
    ttl: timedelta = TTL
    refresh: bool = False
    timeout: float = 20.0

    def _cache_file(self, path: str) -> Path:
        return self.cache_dir / f"{path.strip('/').replace('/', '_')}.json"

    def get(self, path: str) -> dict:
        file = self._cache_file(path)
        if not self.refresh and file.exists():
            age = datetime.now(timezone.utc) - datetime.fromtimestamp(file.stat().st_mtime, timezone.utc)
            if age < self.ttl:
                return json.loads(file.read_text())
        request = urllib.request.Request(f"{BASE_URL}/{path.strip('/')}/", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if file.exists():
                log.warning("FPL injoignable (%s), cache périmé utilisé : %s", exc, file.name)
                return json.loads(file.read_text())
            raise FplError(f"API FPL injoignable pour {path} et aucun cache : {exc}") from exc
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(data))
        return data

    def bootstrap(self) -> dict:
        return self.get("bootstrap-static")

    def element_summary(self, element_id: int) -> dict:
        return self.get(f"element-summary/{int(element_id)}")

    def fetched_at(self) -> datetime | None:
        file = self._cache_file("bootstrap-static")
        return datetime.fromtimestamp(file.stat().st_mtime, timezone.utc) if file.exists() else None


def _float(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def elements(bootstrap: dict) -> pd.DataFrame:
    """Une ligne par joueur FPL : identité, club, statut de disponibilité et totaux de la saison."""
    clubs = {t["id"]: t["name"] for t in bootstrap["teams"]}
    rows = [
        {
            "element_id": int(e["id"]),
            "web_name": e["web_name"],
            "first_name": e["first_name"],
            "second_name": e["second_name"],
            "known_name": e.get("known_name") or "",
            "fpl_club": clubs.get(e["team"], ""),
            "element_type": int(e["element_type"]),
            "status": e["status"],
            "chance_next": _float(e["chance_of_playing_next_round"]),
            "news": e.get("news") or "",
            "minutes": int(e["minutes"]),
            "starts": int(e.get("starts") or 0),
            "goals_scored": int(e["goals_scored"]),
            "own_goals": int(e["own_goals"]),
            "xg": _float(e.get("expected_goals")),
            "xg90": _float(e.get("expected_goals_per_90")),
        }
        for e in bootstrap["elements"]
    ]
    return pd.DataFrame(rows)


def next_event(bootstrap: dict) -> int | None:
    nxt = [ev["id"] for ev in bootstrap["events"] if ev.get("is_next")]
    return int(nxt[0]) if nxt else None


def history(summary: dict) -> pd.DataFrame:
    """Historique par match FPL d'un joueur (journée, minutes, titularisation, buts, xG)."""
    cols = ["round", "minutes", "starts", "goals_scored", "own_goals", "xg", "kickoff_time"]
    rows = [
        {
            "round": int(h["round"]),
            "minutes": int(h["minutes"]),
            "starts": int(h.get("starts") or 0),
            "goals_scored": int(h["goals_scored"]),
            "own_goals": int(h["own_goals"]),
            "xg": _float(h.get("expected_goals")),
            "kickoff_time": h["kickoff_time"],
        }
        for h in summary.get("history", [])
    ]
    return pd.DataFrame(rows, columns=cols)


def _fpl_variants(e: pd.Series) -> list[str]:
    names = [f"{e.first_name} {e.second_name}", e.web_name, e.known_name, e.second_name]
    return [n for n in (norm(x) for x in names if x) if n]


def name_score(mpg_names: list[str], fpl: pd.Series) -> float:
    """Similarité entre les noms MPG (normalisés) et un joueur FPL, entre 0 et 1.

    Nom affiché FPL identique : 1. Nom affiché inclus dans le nom MPG : 0,9 + 0,1 × similarité des noms complets,
    pour départager deux joueurs d'un même club (« James Justin » et « Daniel James »). Sinon, la meilleure
    similarité de chaînes entre variantes.
    """
    variants = _fpl_variants(fpl)
    web = norm(fpl.web_name)
    tokens = set(" ".join(mpg_names).split())
    full = max(SequenceMatcher(None, a, b).ratio() for a in mpg_names for b in variants)
    if any(web == n for n in mpg_names):
        return 1.0
    if web and set(web.split()) <= tokens:
        return 0.9 + 0.1 * full
    return full


def match_players(players: pd.DataFrame, fpl: pd.DataFrame, overrides: dict[str, int] | None = None) -> pd.DataFrame:
    """Associe chaque joueur MPG (`player_key`) à un `element_id` FPL.

    Correspondance des clubs par `CLUB_TO_FPL`, puis appariement un-à-un par similarité de nom au sein du club
    (glouton par score décroissant, seuil `MATCH_THRESHOLD`). Un joueur sans candidat dans son club est cherché
    dans toute la ligue avec un seuil plus strict (transfert en cours de saison). `overrides` force l'appariement.
    """
    overrides = overrides or {}
    fpl = fpl.set_index("element_id", drop=False)
    names = {
        r.player_key: [n for n in (norm(r.joueur), norm(getattr(r, "nom_data", "") or "")) if n]
        for r in players.itertuples()
    }
    club_of = dict(zip(players["player_key"], players["club"].map(lambda c: CLUB_TO_FPL.get(c, c))))
    result: dict[str, tuple[int, float, str]] = {
        k: (int(v), 1.0, "manuel") for k, v in overrides.items() if int(v) in fpl.index
    }
    taken = {v[0] for v in result.values()}

    for club, keys in pd.Series(club_of).groupby(lambda k: club_of[k]):
        todo = [k for k in keys.index if k not in result]
        cands = fpl[fpl["fpl_club"] == club]
        scored = sorted(
            ((name_score(names[k], e), k, int(e.element_id)) for k in todo for e in cands.itertuples()),
            reverse=True,
        )
        for score, key, element_id in scored:
            if score < MATCH_THRESHOLD:
                break
            if key in result or element_id in taken:
                continue
            result[key] = (element_id, score, "club")
            taken.add(element_id)

    for key in [k for k in names if k not in result]:
        best = max(
            ((name_score(names[key], e), int(e.element_id)) for e in fpl.itertuples() if e.element_id not in taken),
            default=(0.0, -1),
        )
        if best[0] >= CROSS_CLUB_THRESHOLD:
            result[key] = (best[1], best[0], "hors_club")
            taken.add(best[1])

    out = players[["player_key", "joueur", "club"]].copy()
    out["element_id"] = out["player_key"].map(lambda k: result.get(k, (pd.NA,))[0]).astype("Int64")
    out["score_appariement"] = out["player_key"].map(lambda k: result.get(k, (None, np.nan))[1])
    out["methode"] = out["player_key"].map(lambda k: result.get(k, (None, None, "non_apparie"))[2])
    named = out.merge(fpl[["element_id", "web_name", "fpl_club"]].reset_index(drop=True), on="element_id", how="left")
    return named
