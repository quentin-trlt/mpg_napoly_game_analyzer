from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

POSTE_GROUPE = {"G": "G", "DC": "D", "DL": "D", "MD": "M", "MO": "M", "A": "A"}
GROUPES = ["G", "D", "M", "A"]

ON_PITCH = ("titulaire", "remplacant_entre", "rotaldo")
COACH_PICKS = ("titulaire", "titulaire_absent", "titulaire_remplace_tactique")

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "teams": [
        "team_id",
        "team_name",
        "abrev",
        "valeur_effectif_meur",
        "total_cote",
        "total_enchere",
        "budget_restant",
        "nb_joueurs",
        "classement",
        "pts",
        "g",
        "n",
        "p",
        "diff_buts",
        "moy_equipe",
        "moy_equipe_avec_bonus",
        "buts_pour_reels",
        "buts_pour_mpg",
        "buts_contre_reels",
        "buts_contre_mpg",
        "rotaldos_alignes",
    ],
    "players": [
        "team_id",
        "player_key",
        "joueur",
        "club",
        "poste_groupe",
        "poste",
        "cote",
        "enchere",
        "flag_point_interrogation",
        "note_moy_reelle",
        "buts_reels_saison",
        "pct_titularisations",
    ],
    "fixtures": [
        "gw",
        "date",
        "home_team_id",
        "away_team_id",
        "home_goals",
        "away_goals",
        "statut",
        "match_id",
        "home_formation",
        "away_formation",
    ],
    "lineups": [
        "match_id",
        "gw",
        "team_id",
        "side",
        "joueur_affiche",
        "player_key",
        "poste",
        "statut",
        "note_avec_bonus",
        "capitaine",
    ],
    "goals": ["match_id", "gw", "team_id", "type_but", "player_key"],
    "bonus": ["match_id", "gw", "team_id", "bonus", "effet", "cible_affiche"],
    "substitutions": [
        "match_id",
        "gw",
        "team_id",
        "titulaire_sortant",
        "type",
        "note_titulaire",
        "remplacant_entre",
        "note_remplacant",
    ],
    "best_players": ["match_id", "gw", "rang", "joueur", "note"],
    "typical_xi": ["team_id", "slot", "poste", "note_moy", "joueur_affiche", "player_key"],
    "mpg_scorers_ranking": ["rang", "joueur", "team_id", "buts_reels", "buts_mpg", "player_key"],
    "player_leaderboards": ["categorie", "rang", "joueur", "team_id", "achat", "valeur", "player_key"],
}


OPTIONAL_PLAYER_COLUMNS = [
    "passes_decisives_saison",
    "cartons_jaunes",
    "cartons_rouges",
    "matchs_club",
    "matchs_joues",
    "matchs_titulaire",
    "points_mpg_moy",
    "statut_performance",
]
UNAVAILABLE = ("blesse", "suspendu")


class DataSchemaError(ValueError):
    pass


@dataclass(frozen=True)
class League:
    teams: pd.DataFrame
    players: pd.DataFrame
    fixtures: pd.DataFrame
    lineups: pd.DataFrame
    goals: pd.DataFrame
    bonus: pd.DataFrame
    substitutions: pd.DataFrame
    best_players: pd.DataFrame
    typical_xi: pd.DataFrame
    scorers: pd.DataFrame
    leaderboards: pd.DataFrame

    @property
    def played(self) -> pd.DataFrame:
        return self.fixtures[self.fixtures["statut"] == "joue"]

    @property
    def last_gw(self) -> int:
        return int(self.played["gw"].max()) if not self.played.empty else 0

    @property
    def n_gw(self) -> int:
        return int(self.fixtures["gw"].max())

    @property
    def team_names(self) -> dict[int, str]:
        return dict(zip(self.teams["team_id"], self.teams["team_name"]))


def _read(data_dir: Path, name: str) -> pd.DataFrame:
    path = data_dir / f"{name}.csv"
    if not path.exists():
        raise DataSchemaError(f"fichier manquant : {path}")
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLUMNS[name] if c not in df.columns]
    if missing:
        raise DataSchemaError(f"{path.name} : colonnes manquantes {missing}")
    return df


def _derive_player_columns(players: pd.DataFrame) -> pd.DataFrame:
    """Colonnes de saison PL facultatives (NaN si absentes de l'export) et taux dérivés."""
    p = players.copy()
    for col in OPTIONAL_PLAYER_COLUMNS:
        if col not in p:
            p[col] = pd.NA
    p["statut_performance"] = p["statut_performance"].fillna("inconnu")
    num = [c for c in OPTIONAL_PLAYER_COLUMNS if c != "statut_performance"]
    p[num] = p[num].apply(pd.to_numeric, errors="coerce")
    not_ok = p["statut_performance"].isin(UNAVAILABLE)
    for col in ("matchs_joues", "matchs_titulaire", "passes_decisives_saison", "cartons_jaunes", "cartons_rouges"):
        p.loc[not_ok & p[col].isna(), col] = 0
    club = p["matchs_club"].where(p["matchs_club"] > 0)
    p["taux_jeu"] = p["matchs_joues"] / club
    p["taux_titu"] = p["matchs_titulaire"] / club
    p["ga_saison"] = p["buts_reels_saison"] + p["passes_decisives_saison"]
    p["ga_par_match"] = p["ga_saison"] / p["matchs_joues"].where(p["matchs_joues"] > 0)
    p["indisponible"] = not_ok
    return p


def load_league(data_dir: Path | str = DEFAULT_DATA_DIR) -> League:
    data_dir = Path(data_dir)
    raw = {name: _read(data_dir, name) for name in REQUIRED_COLUMNS}

    teams = raw["teams"].sort_values("team_id").reset_index(drop=True)
    players = raw["players"].copy()
    if players["player_key"].duplicated().any():
        dups = players.loc[players["player_key"].duplicated(), "player_key"].tolist()
        raise DataSchemaError(f"players.csv : player_key dupliqués {dups}")

    players = _derive_player_columns(players)

    fixtures = raw["fixtures"].copy()
    fixtures["date"] = pd.to_datetime(fixtures["date"])

    lineups = raw["lineups"].copy()
    lineups["player_key"] = lineups["player_key"].replace("", pd.NA)
    lineups["poste_groupe"] = lineups["poste"].map(POSTE_GROUPE)
    lineups["capitaine"] = lineups["capitaine"].fillna(0).astype(int)

    unknown = set(lineups["statut"]) - set(ON_PITCH) - set(COACH_PICKS) - {"remplacant_non_entre"}
    if unknown:
        raise DataSchemaError(f"lineups.csv : statuts inconnus {sorted(unknown)}")

    bonus = raw["bonus"].copy()
    bonus["effet_pts"] = pd.to_numeric(bonus["effet"].str.replace("pt", "", regex=False), errors="coerce")

    return League(
        teams=teams,
        players=players,
        fixtures=fixtures,
        lineups=lineups,
        goals=raw["goals"],
        bonus=bonus,
        substitutions=raw["substitutions"],
        best_players=raw["best_players"],
        typical_xi=raw["typical_xi"],
        scorers=raw["mpg_scorers_ranking"],
        leaderboards=raw["player_leaderboards"],
    )
