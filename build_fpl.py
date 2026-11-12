"""Instantané FPL des joueurs de la ligue, à lancer après chaque export MPG : `uv run python build_fpl.py`.

Écrit dans `data/` :
- `fpl_players.csv` : un joueur de la ligue par ligne, apparié à FPL (statut, chance de jouer, news, totaux) ;
- `fpl_history.csv` : une ligne par joueur de la ligue et par match FPL (minutes, titularisation, buts, xG) ;
- `fpl_snapshots/fpl_players_PL<journée>.csv` : copie de `fpl_players.csv` nommée d'après la prochaine journée de
  PL. `chance_of_playing_next_round` n'est plus consultable une fois la journée passée : ces copies sont le seul
  moyen de mesurer plus tard ce qu'elle apporte. Relancé avant la même journée, le script écrase la copie.

Toutes les requêtes sont refaites (pas de cache) : l'instantané reflète l'état de FPL au moment du lancement.
"""

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from mpg import fpl
from mpg.loader import DEFAULT_DATA_DIR, League, load_league

PLAYER_COLUMNS = [
    "player_key",
    "joueur",
    "club",
    "element_id",
    "web_name",
    "fpl_club",
    "methode",
    "score_appariement",
    "status",
    "chance_next",
    "news",
    "minutes",
    "starts",
    "goals_scored",
    "own_goals",
    "xg",
    "xg90",
    "prochaine_journee_pl",
    "recupere_le",
]
HISTORY_COLUMNS = ["player_key", "element_id", "round", "minutes", "starts", "goals_scored", "own_goals", "xg"]
HISTORY_COLUMNS += ["kickoff_time"]
SNAPSHOT_DIR = "fpl_snapshots"

log = logging.getLogger(__name__)


def read_overrides(path: Path | None) -> dict[str, int]:
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["player_key"], df["element_id"].astype(int)))


def build(league: League, client: fpl.FplClient, overrides: dict[str, int] | None = None):
    """Joueurs appariés et historique par match, prêts à écrire."""
    bootstrap = client.bootstrap()
    els = fpl.elements(bootstrap)
    mapping = fpl.match_players(league.players, els, overrides)
    unmatched = mapping[mapping["methode"] == "non_apparie"]
    if not unmatched.empty:
        log.warning("Sans correspondance FPL : %s", ", ".join(unmatched["joueur"]))
    players = mapping.drop(columns=["web_name", "fpl_club"]).merge(els, on="element_id", how="left")
    players["prochaine_journee_pl"] = fpl.next_event(bootstrap)
    players["recupere_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    frames = []
    for key, eid in zip(players["player_key"], players["element_id"]):
        if pd.isna(eid):
            continue
        h = fpl.history(client.element_summary(int(eid)))
        frames.append(h.assign(player_key=key, element_id=int(eid)))
    history = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=HISTORY_COLUMNS)
    return players[PLAYER_COLUMNS], history[HISTORY_COLUMNS]


def write(players: pd.DataFrame, history: pd.DataFrame, data_dir: Path) -> list[Path]:
    data_dir = Path(data_dir)
    paths = [data_dir / "fpl_players.csv", data_dir / "fpl_history.csv"]
    players.to_csv(paths[0], index=False)
    history.to_csv(paths[1], index=False)
    event = players["prochaine_journee_pl"].dropna()
    if not event.empty:
        snap_dir = data_dir / SNAPSHOT_DIR
        snap_dir.mkdir(exist_ok=True)
        paths.append(snap_dir / f"fpl_players_PL{int(event.iloc[0]):02d}.csv")
        players.to_csv(paths[-1], index=False)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--overrides", type=Path, default=None, help="CSV player_key,element_id pour forcer des appariements"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    league = load_league(args.data_dir)
    client = fpl.FplClient(cache_dir=args.data_dir / "fpl_cache", refresh=True)
    players, history = build(league, client, read_overrides(args.overrides))
    paths = write(players, history, args.data_dir)
    matched = players["element_id"].notna().sum()
    log.info("%d/%d joueurs appariés, %d matchs FPL", matched, len(players), len(history))
    for p in paths:
        log.info("écrit : %s", p)


if __name__ == "__main__":
    main()
