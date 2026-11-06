import pandas as pd

SORT_KEYS = ["pts", "diff", "bp"]


def table(tm: pd.DataFrame, upto_gw: int | None = None) -> pd.DataFrame:
    """Classement recalculé depuis team_match (départage : points, différence de buts, buts marqués)."""
    df = tm if upto_gw is None else tm[tm["gw"] <= upto_gw]
    out = (
        df.groupby(["team_id", "team_name"])
        .agg(
            j=("match_id", "size"),
            g=("resultat", lambda s: int((s == "V").sum())),
            n=("resultat", lambda s: int((s == "N").sum())),
            p=("resultat", lambda s: int((s == "D").sum())),
            bp=("bp", "sum"),
            bc=("bc", "sum"),
            pts=("pts", "sum"),
            note_moy=("note_moy", "mean"),
        )
        .reset_index()
    )
    out["diff"] = out["bp"] - out["bc"]
    out = out.sort_values(SORT_KEYS, ascending=False).reset_index(drop=True)
    out["rang"] = out.index + 1
    return out


def form(tm: pd.DataFrame, last: int = 5) -> pd.Series:
    return tm.sort_values("gw").groupby("team_id")["resultat"].apply(lambda s: "".join(s.tail(last)))


def standings_by_gw(tm: pd.DataFrame) -> pd.DataFrame:
    """Points cumulés et rang à l'issue de chaque journée."""
    frames = [table(tm, gw).assign(gw=gw) for gw in sorted(tm["gw"].unique())]
    return pd.concat(frames, ignore_index=True)[["gw", "team_id", "team_name", "pts", "diff", "bp", "rang"]]


def current_streak(results: str) -> str:
    """Série en cours à partir d'une chaîne de résultats chronologique, ex. 'VDVV' -> '2V'."""
    if not results:
        return ""
    last = results[-1]
    n = len(results) - len(results.rstrip(last))
    return f"{n}{last}"


def standings_full(tm: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """Classement avec coach, buts réels/MPG, Rotaldos, forme et série en cours."""
    base = table(tm)
    extra = (
        tm.groupby("team_id")
        .agg(
            bp_reel=("bp_reel", "sum"),
            bp_mpg=("bp_mpg", "sum"),
            bp_csc=("bp_csc", "sum"),
            bc_mpg=("bc_mpg", "sum"),
            rotaldos=("n_rotaldos", "sum"),
            note_moy_brute=("note_moy_brute", "mean"),
        )
        .reset_index()
    )
    results = tm.sort_values("gw").groupby("team_id")["resultat"].apply("".join)
    out = base.merge(extra, on="team_id").merge(teams[["team_id", "coach", "abrev"]], on="team_id")
    out["forme"] = out["team_id"].map(results.str[-5:])
    out["serie"] = out["team_id"].map(results.map(current_streak))
    return out


def next_fixtures(fixtures: pd.DataFrame, tbl: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    """Affiches de la prochaine journée avec rang et points des deux équipes."""
    todo = fixtures[fixtures["statut"] != "joue"]
    if todo.empty:
        return todo.iloc[0:0]
    gw = todo["gw"].min()
    nxt = todo[todo["gw"] == gw][["gw", "date", "heure", "home_team_id", "away_team_id"]].copy()
    info = tbl.set_index("team_id")[[c for c in ("rang", "pts", "forme", "serie") if c in tbl]]
    names = teams.set_index("team_id")["team_name"]
    for side in ("home", "away"):
        ids = nxt[f"{side}_team_id"]
        nxt[f"{side}_team"] = ids.map(names)
        for col in info.columns:
            nxt[f"{side}_{col}"] = ids.map(info[col])
    nxt["ecart_rang"] = (nxt["home_rang"] - nxt["away_rang"]).abs()
    return nxt.sort_values("ecart_rang").reset_index(drop=True)
