"""Projection de chaque joueur pour une journée de Premier League : P(joue), note attendue, buts réels attendus.

- P(joue) : disponibilité FPL (`chance_of_playing_next_round`, statut) × part des 5 dernières journées FPL avec du
  temps de jeu, rétrécie vers le taux de jeu de la saison. Sans appariement FPL : taux de jeu et statut MPG.
- Note | joue : note rétrécie du joueur + effet du match attendu de son club (buts pour et contre attendus,
  modèle de Poisson attaque/défense sur les résultats de PL), choc commun aux joueurs d'un même club, bruit
  individuel, décalage des buteurs. Arrondie à 0,5.
- Buts réels | joue : Poisson de paramètre xG/90 × minutes attendues × difficulté de l'adversaire. L'xG/90 de la
  saison est rétréci vers la médiane du poste (450 minutes fictives), puis l'xG/90 récent vers celui de la saison.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize

from mpg.analysis import Analysis
from mpg.coach.rules import Draws
from mpg.fpl import UNAVAILABLE_STATUS
from mpg.loader import League
from mpg.playing_time import PlayModel, play_features, recent
from mpg.premier_league import LOCAL_TZ, club_view, pl_gw_for

PLAY_PRIOR_WEIGHT = 2.0
XG_PRIOR_MINUTES = 450.0
DEFAULT_MINUTES = 75.0
DOUBTFUL_CHANCE = 0.5
BETA_RIDGE = 10.0
STRENGTH_RIDGE = 2.0
NOTE_BOUNDS = (0.5, 10.0)
UNAVAILABLE_GWS = {"blesse": 2, "suspendu": 1, "i": 2, "s": 1}
OVERRIDE_LEVELS = {"sûr": 1.0, "probable": 0.8, "incertain": 0.5, "absent": 0.0}


def deadline(league: League, pl_gw: int) -> pd.Timestamp:
    """Coup d'envoi du premier match de la journée : les remplacements tactiques sont figés à cette heure."""
    cr = league.club_results
    return cr.loc[cr["pl_gw"] == pl_gw, "date"].min().tz_convert(LOCAL_TZ)


def club_fixtures(league: League, pl_gw: int) -> pd.DataFrame:
    """Premier match de chaque club dans la journée de PL (club, adversaire, domicile, date)."""
    v = club_view(league.club_results)
    v = v[v["pl_gw"] == pl_gw].sort_values("date")
    return v.groupby("club").head(1)[["club", "adversaire", "domicile", "date", "bp", "bc", "statut"]]


@dataclass
class ClubStrength:
    """log λ = base + domicile + attaque(club) − défense(adversaire), estimé par Poisson pénalisé (L2)."""

    attack: dict[str, float]
    defence: dict[str, float]
    home: float
    base: float

    def expected(self, club: str, opp: str, home: bool) -> tuple[float, float]:
        h = self.home if home else 0.0
        a = self.home if not home else 0.0
        gf = np.exp(self.base + h + self.attack.get(club, 0.0) - self.defence.get(opp, 0.0))
        ga = np.exp(self.base + a + self.attack.get(opp, 0.0) - self.defence.get(club, 0.0))
        return float(gf), float(ga)

    @property
    def mean_goals(self) -> float:
        return float(np.exp(self.base + self.home / 2))

    def opponent_factor(self, opp: str, home: bool) -> float:
        """Multiplicateur des buts d'un joueur selon l'adversaire et le lieu, par rapport à un match moyen.

        L'xG d'un joueur reflète déjà l'attaque de son club : seuls comptent la défense adverse, comparée à la
        moyenne des défenses, et le lieu, comparé à une moitié de matchs à domicile.
        """
        mean_def = np.mean(np.exp(-np.array(list(self.defence.values()))))
        venue = self.home / 2 if home else -self.home / 2
        return float(np.exp(venue - self.defence.get(opp, 0.0)) / mean_def)


def fit_club_strength(results: pd.DataFrame, ridge: float = STRENGTH_RIDGE) -> ClubStrength:
    played = results[results["statut"] == "joue"].dropna(subset=["home_score", "away_score"])
    clubs = sorted(set(results["home_club"]) | set(results["away_club"]))
    idx = {c: i for i, c in enumerate(clubs)}
    n = len(clubs)
    hi = played["home_club"].map(idx).to_numpy()
    ai = played["away_club"].map(idx).to_numpy()
    hs = played["home_score"].to_numpy(float)
    as_ = played["away_score"].to_numpy(float)

    def nll(theta: np.ndarray) -> float:
        base, home, att, dfn = theta[0], theta[1], theta[2 : 2 + n], theta[2 + n :]
        lh = base + home + att[hi] - dfn[ai]
        la = base + att[ai] - dfn[hi]
        return float(np.sum(np.exp(lh) - hs * lh) + np.sum(np.exp(la) - as_ * la) + ridge * (att @ att + dfn @ dfn))

    x0 = np.zeros(2 + 2 * n)
    x0[0] = np.log(max(np.mean(np.r_[hs, as_]), 0.1)) if len(hs) else 0.3
    res = optimize.minimize(nll, x0, method="L-BFGS-B")
    th = res.x
    return ClubStrength(
        attack=dict(zip(clubs, th[2 : 2 + n])), defence=dict(zip(clubs, th[2 + n :])), home=th[1], base=th[0]
    )


@dataclass
class NoteModel:
    """Paramètres de note estimés sur les matchs joués de la ligue."""

    sigma_player: float
    sigma_club: float
    goal_bump: float
    own_goal_rate: float
    beta_for: dict[str, float]
    beta_against: dict[str, float]
    goals_mean: float
    k_shrink: float


def _appearances_with_pl(a: Analysis) -> pd.DataFrame:
    league = a.league
    lu = a.lineups
    app = lu[lu["a_joue_irl"] & lu["player_key"].notna()].copy()
    app["club"] = app["player_key"].map(league.players.set_index("player_key")["club"])
    app["pl_gw"] = app["gw"].map({g: pl_gw_for(league, g) for g in app["gw"].unique()})
    v = club_view(league.club_results).sort_values("date").groupby(["club", "pl_gw"]).head(1)
    app = app.merge(v[["club", "pl_gw", "bp", "bc"]], on=["club", "pl_gw"], how="left")
    counts = app.groupby("player_key")["note_brute"].transform("size")
    app["resid"] = app["note_brute"] - app.groupby("player_key")["note_brute"].transform("mean")
    app["resid"] *= np.sqrt(counts / (counts - 1).where(counts > 1))
    return app[counts > 1].dropna(subset=["resid"])


def _ridge(x: np.ndarray, y: np.ndarray, lam: float) -> np.ndarray:
    return np.linalg.solve(x.T @ x + lam * np.eye(x.shape[1]), x.T @ y)


def fit_note_model(a: Analysis) -> NoteModel:
    """Le décalage des buteurs est estimé d'abord, puis retiré des résidus avant la décomposition de variance
    (choc de club + bruit individuel) : sinon la variance due aux buts serait comptée deux fois au tirage."""
    league = a.league
    app = _appearances_with_pl(a)

    real = league.goals[league.goals["type_but"].isin(["reel", "bloque"])]
    scorers = set(zip(real["match_id"], real["player_key"].dropna()))
    app["marque"] = [(m, k) in scorers for m, k in zip(app["match_id"], app["player_key"])]
    field = app[app["poste_groupe"] != "G"]
    scored = field["marque"].to_numpy()
    goal_bump = float(field["resid"][scored].mean() - field["resid"][~scored].mean()) if scored.any() else 1.0
    scored_rate = app.groupby("player_key")["marque"].transform("mean")
    app["resid"] = app["resid"] - goal_bump * (app["marque"] - scored_rate)
    sigma_total = float(np.sqrt((app["resid"] ** 2).mean())) if len(app) else 1.0

    grp = app.groupby(["club", "gw"])["resid"]
    sizes = grp.size()
    multi = sizes[sizes >= 2].index
    within = grp.var(ddof=1).loc[multi].mean()
    between = grp.mean().loc[multi].var(ddof=1) - within / sizes.loc[multi].mean()
    sigma_club = float(np.sqrt(np.clip(between, 0.0, 0.5 * sigma_total**2))) if len(multi) > 2 else 0.0
    sigma_player = float(np.sqrt(sigma_total**2 - sigma_club**2))

    on_pitch = a.lineups[a.lineups["sur_terrain"] & (a.lineups["poste_groupe"] != "G")]
    own = int((league.goals["type_but"] == "csc").sum())
    own_goal_rate = own / max(len(on_pitch), 1)

    goals_mean = float(np.nanmean(np.r_[app["bp"], app["bc"]])) if app["bp"].notna().any() else 1.4
    beta_for, beta_against = {}, {}
    for line, rows in app.dropna(subset=["bp", "bc"]).groupby("poste_groupe"):
        x = np.c_[rows["bp"] - goals_mean, rows["bc"] - goals_mean]
        b = _ridge(x, rows["resid"].to_numpy(), BETA_RIDGE)
        beta_for[line], beta_against[line] = float(b[0]), float(b[1])

    return NoteModel(
        sigma_player=sigma_player,
        sigma_club=sigma_club,
        goal_bump=goal_bump,
        own_goal_rate=own_goal_rate,
        beta_for=beta_for,
        beta_against=beta_against,
        goals_mean=goals_mean,
        k_shrink=float(a.meta["k_shrinkage"]),
    )


def _availability(row: pd.Series, horizon: int) -> float:
    """Disponibilité à `horizon` journées (1 = la prochaine), d'après FPL si le joueur est apparié."""
    status = row.get("status")
    if isinstance(status, str):
        if status == "u":
            return 0.0
        if horizon == 1:
            chance = row.get("chance_next")
            if pd.notna(chance):
                return float(chance) / 100
            return 0.0 if status in UNAVAILABLE_STATUS else (DOUBTFUL_CHANCE if status == "d" else 1.0)
        return 0.0 if horizon <= UNAVAILABLE_GWS.get(status, 0) else 1.0
    statut = row.get("statut_performance")
    if horizon <= UNAVAILABLE_GWS.get(statut, 0):
        return 0.0
    return 0.5 if statut == "incertain" and horizon == 1 else 1.0


def project_players(
    a: Analysis,
    team_ids: list[int],
    pl_gw: int,
    model: NoteModel,
    strength: ClubStrength,
    fpl_players: pd.DataFrame | None = None,
    fpl_history: dict[int, pd.DataFrame] | None = None,
    overrides: dict[str, float] | None = None,
    horizon: int = 1,
    play_model: PlayModel | None = None,
    history_until: int | None = None,
) -> pd.DataFrame:
    """Une ligne par joueur des équipes `team_ids` pour la journée de PL `pl_gw`.

    `fpl_players` : `fpl.elements` joint à l'appariement (`element_id` par `player_key`). `fpl_history` : historique
    par match FPL de chaque `element_id`. `overrides` : P(joue) imposée à la main (prioritaire). `play_model` : logit
    de temps de jeu ; sans lui, part des journées récentes jouées rétrécie vers le taux de la saison.
    `history_until` : journée PL jusqu'à laquelle (exclue) l'historique est lu, `pl_gw` par défaut ; pour une
    journée lointaine, c'est la prochaine journée, la seule dont l'historique précédent est connu.
    """
    history_until = pl_gw if history_until is None else history_until
    fpl_history = fpl_history or {}
    overrides = overrides or {}
    pv = a.player_value
    cols = ["player_key", "joueur", "team_id", "club", "poste_groupe", "cote", "note_retrecie", "n_notes"]
    cols += ["taux_jeu", "statut_performance", "buts_reels_saison", "matchs_joues"]
    p = pv.loc[pv["team_id"].isin(team_ids), cols].copy()
    if fpl_players is not None:
        fcols = ["player_key", "element_id", "status", "chance_next", "news", "xg90", "minutes", "web_name"]
        p = p.merge(fpl_players[fcols].rename(columns={"minutes": "minutes_saison"}), on="player_key", how="left")
    fx = club_fixtures(a.league, pl_gw).set_index("club")
    p["adversaire_pl"] = p["club"].map(fx["adversaire"])
    p["domicile_pl"] = p["club"].map(fx["domicile"])
    base_rate = p["taux_jeu"].fillna(p["taux_jeu"].median()).clip(0, 1)
    xg_prior = {}
    if fpl_players is not None:
        regulars = fpl_players.merge(pv[["player_key", "poste_groupe"]], on="player_key")
        regulars = regulars[regulars["minutes"] >= XG_PRIOR_MINUTES]
        xg_prior = regulars.groupby("poste_groupe")["xg90"].median().to_dict()

    rows = []
    for r, rate in zip(p.itertuples(index=False), base_rate):
        row = r._asdict()
        has_match = isinstance(row["adversaire_pl"], str)
        eid = row.get("element_id")
        full_hist = fpl_history.get(int(eid)) if pd.notna(eid) else None
        hist = recent(full_hist, history_until)
        played = hist[hist["minutes"] > 0]
        features = play_features(full_hist, history_until, rate) if play_model is not None else None
        if features is not None:
            p_hist = play_model.prob(features)
        else:
            p_hist = (played.shape[0] + PLAY_PRIOR_WEIGHT * rate) / (len(hist) + PLAY_PRIOR_WEIGHT)
        p_auto = _availability(pd.Series(row), horizon) * p_hist if has_match else 0.0
        minutes = float(played["minutes"].mean()) if len(played) else DEFAULT_MINUTES

        gf, ga = (
            strength.expected(row["club"], row["adversaire_pl"], bool(row["domicile_pl"]))
            if has_match
            else (strength.mean_goals, strength.mean_goals)
        )
        opp_factor = strength.opponent_factor(row["adversaire_pl"], bool(row["domicile_pl"])) if has_match else 1.0
        line = row["poste_groupe"]
        adj = model.beta_for.get(line, 0.0) * (gf - model.goals_mean)
        adj += model.beta_against.get(line, 0.0) * (ga - model.goals_mean)

        if line == "G":
            lam = 0.0
        elif pd.notna(row.get("xg90")):
            prior90 = xg_prior.get(line, 0.1)
            season_min = float(row.get("minutes_saison") or 0.0)
            season_xg = float(row["xg90"]) * season_min / 90
            season_xg90 = (season_xg + prior90 * XG_PRIOR_MINUTES / 90) / ((season_min + XG_PRIOR_MINUTES) / 90)
            recent_xg = float(played["xg"].sum()) if len(played) else 0.0
            recent_min = float(played["minutes"].sum()) if len(played) else 0.0
            xg90 = (recent_xg + season_xg90 * XG_PRIOR_MINUTES / 90) / ((recent_min + XG_PRIOR_MINUTES) / 90)
            lam = xg90 * minutes / 90 * opp_factor
        else:
            per_match = (row["buts_reels_saison"] or 0) / max(row["matchs_joues"] or 0, 1)
            lam = float(per_match) * opp_factor

        override = overrides.get(row["player_key"])
        rows.append(
            {
                **row,
                "a_un_match": has_match,
                "p_joue_auto": p_auto,
                "p_joue": float(override) if override is not None and horizon == 1 else p_auto,
                "surcharge": override is not None and horizon == 1,
                "minutes_attendues": minutes,
                "buts_attendus_club": gf,
                "buts_encaisses_club": ga,
                "note_attendue": row["note_retrecie"] + adj,
                "ajustement_adversaire": adj,
                "note_sd_mean": model.sigma_player / np.sqrt(row["n_notes"] + model.k_shrink),
                "lambda_buts": lam,
                "source": "FPL" if pd.notna(eid) else "MPG",
            }
        )
    return pd.DataFrame(rows).reset_index(drop=True)


def sample_draws(proj: pd.DataFrame, model: NoteModel, n_draws: int = 4000, seed: int = 0) -> Draws:
    """Tirages communs (nombres aléatoires communs) pour tous les joueurs projetés."""
    rng = np.random.default_rng(seed)
    n_p = len(proj)
    p_play = proj["p_joue"].clip(0, 1).to_numpy(float)
    lam = proj["lambda_buts"].clip(lower=0).to_numpy(float)
    mu = proj["note_attendue"].to_numpy(float)
    sd = np.sqrt(proj["note_sd_mean"].to_numpy(float) ** 2 + model.sigma_player**2)
    field = (proj["poste_groupe"] != "G").to_numpy()
    club_codes, clubs = pd.factorize(proj["club"])

    plays = rng.random((n_p, n_draws)) < p_play[:, None]
    goals = rng.poisson(lam[:, None], size=(n_p, n_draws))
    p_score = 1 - np.exp(-lam)
    shock = model.sigma_club * rng.standard_normal((len(clubs), n_draws))
    raw = mu[:, None] + sd[:, None] * rng.standard_normal((n_p, n_draws)) + shock[club_codes]
    raw += model.goal_bump * ((goals > 0) - p_score[:, None])
    note = np.clip(np.round(raw * 2) / 2, *NOTE_BOUNDS)
    own = (rng.random((n_p, n_draws)) < model.own_goal_rate) & field[:, None]
    return Draws(
        keys=proj["player_key"].tolist(),
        line=proj["poste_groupe"].to_numpy(),
        plays=plays,
        note=note,
        goals=np.where(plays, goals, 0),
        own_goals=np.where(plays, own, 0).astype(int),
    )
