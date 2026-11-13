"""Modèles de prédiction de match. Convention : issue 0 = victoire domicile, 1 = nul, 2 = victoire extérieur.

Chaque modèle expose `fit(ctx)` puis `sample_probs(fixtures, n_draws, rng)`, qui renvoie un tableau
(n_draws, n_matchs, 3) de probabilités. Les tirages propagent l'incertitude sur les paramètres : la moyenne sur
les tirages donne la probabilité prédictive, la dispersion entre tirages corrèle les matchs d'une même équipe.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import optimize, special
from scipy import stats as sps

from mpg.loader import GROUPES

OUTCOMES = ("H", "D", "A")
ELO_PER_LATENT = 400 / np.log(10)
RESULT_TO_IDX = {"V": 0, "N": 1, "D": 2}


@dataclass
class Context:
    """Données disponibles au moment de la prédiction : matchs joués jusqu'à `upto_gw` inclus."""

    tm: pd.DataFrame
    strength: pd.Series
    players: pd.DataFrame
    lineups: pd.DataFrame
    team_ids: list[int]
    upto_gw: int
    bonus_remaining: pd.DataFrame | None = None
    past_bonus: pd.DataFrame | None = None
    formations: dict = field(default_factory=dict)
    tactical_gain: dict = field(default_factory=dict)
    start_share: float = 0.82
    note_slope: float = 2.0
    goal_note_slope: float = 0.5

    def bonus_note(self, rows: pd.DataFrame) -> np.ndarray:
        """Avantage de note net des bonus posés lors des matchs de `rows` (vue de team_id), 0 si inconnu."""
        if self.past_bonus is None or rows.empty:
            return np.zeros(len(rows))
        m = rows[["match_id", "team_id"]].merge(self.past_bonus, on=["match_id", "team_id"], how="left")
        return m["d_note"].fillna(0.0).to_numpy()

    def cancelled_goals(self, rows: pd.DataFrame) -> np.ndarray:
        if self.past_bonus is None or rows.empty:
            return np.zeros(len(rows))
        m = rows[["match_id", "team_id"]].merge(self.past_bonus, on=["match_id", "team_id"], how="left")
        return m["buts_annules"].fillna(0).to_numpy(float)

    @property
    def home_rows(self) -> pd.DataFrame:
        return self.tm[self.tm["domicile"]]


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def ordered_probs(x: np.ndarray, c: float) -> np.ndarray:
    """Logit ordonné symétrique : P(H) = σ(x − c), P(A) = σ(−x − c), P(N) = reste (c ≥ 0)."""
    ph = _sigmoid(x - c)
    pa = _sigmoid(-x - c)
    return np.stack([ph, 1.0 - ph - pa, pa], axis=-1)


@dataclass
class OrderedLogit:
    """Lien entre un écart de force et le résultat : x = b·Δ + h (avantage du terrain), seuil de nul c.

    Ajusté au maximum a posteriori avec des a priori faibles (b ~ N(b0, 2²), h ~ N(0, 0.5²)).
    """

    b0: float = 1.0
    b: float = 1.0
    h: float = 0.3
    c: float = 0.4

    def fit(self, delta: np.ndarray, outcome: np.ndarray) -> "OrderedLogit":
        if len(delta) == 0:
            self.b = self.b0
            return self

        def nll(theta: np.ndarray) -> float:
            b, h, log_c = theta
            p = ordered_probs(b * delta + h, np.exp(log_c))
            ll = np.log(np.clip(p[np.arange(len(outcome)), outcome], 1e-12, None)).sum()
            prior = ((b - self.b0) / 2.0) ** 2 / 2 + (h / 0.5) ** 2 / 2 + ((log_c - np.log(0.4)) / 1.0) ** 2 / 2
            return -ll + prior

        res = optimize.minimize(
            nll,
            x0=np.array([self.b0, 0.3, np.log(0.4)]),
            method="Nelder-Mead",
            options={"xatol": 1e-5, "fatol": 1e-7, "maxiter": 4000},
        )
        self.b, self.h, self.c = float(res.x[0]), float(res.x[1]), float(np.exp(res.x[2]))
        return self

    def probs(self, delta: np.ndarray) -> np.ndarray:
        return ordered_probs(self.b * delta + self.h, self.c)


def _outcomes(home_rows: pd.DataFrame) -> np.ndarray:
    return home_rows["resultat"].map(RESULT_TO_IDX).to_numpy()


@dataclass
class BaselineModel:
    """Référence : fréquences observées domicile / nul / extérieur, lissées par une loi de Dirichlet(1, 1, 1)."""

    name: str = "Référence (fréquences)"
    p: np.ndarray = field(default_factory=lambda: np.full(3, 1 / 3))

    def fit(self, ctx: Context) -> "BaselineModel":
        counts = np.bincount(_outcomes(ctx.home_rows), minlength=3) if len(ctx.home_rows) else np.zeros(3)
        self.p = (counts + 1) / (counts.sum() + 3)
        return self

    def sample_probs(self, fixtures: pd.DataFrame, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        return np.broadcast_to(self.p, (n_draws, len(fixtures), 3)).copy()


@dataclass
class EloModel:
    """Elo à multiplicateur d'écart de buts, initialisé par l'indice de force a priori.

    r0 = 1500 + `prior_scale` × indice de force. Après chaque match : r += K × G × (résultat − attendu).
    Le lien écart d'Elo → résultat est un logit ordonné ajusté sur les écarts d'avant-match observés.
    L'incertitude est un bruit gaussien d'écart-type `sigma` points d'Elo sur chaque note.
    """

    name: str = "Elo"
    k: float = 30.0
    prior_scale: float = 100.0
    sigma: float = 50.0
    ratings: dict[int, float] = field(default_factory=dict)
    link: OrderedLogit = field(default_factory=lambda: OrderedLogit(b0=0.6))

    @staticmethod
    def _goal_mult(diff: int) -> float:
        n = abs(diff)
        return 1.0 if n <= 1 else 1.5 if n == 2 else (11 + n) / 8

    def fit(self, ctx: Context) -> "EloModel":
        r = {t: 1500.0 + self.prior_scale * float(ctx.strength.get(t, 0.0)) for t in ctx.team_ids}
        deltas, outs = [], []
        rows = ctx.home_rows.sort_values("gw")
        bonus_elo = ctx.bonus_note(rows) * ctx.note_slope * ELO_PER_LATENT
        for (_, m), bonus_d in zip(rows.iterrows(), bonus_elo):
            h, a = int(m["team_id"]), int(m["opp_id"])
            d = r[h] - r[a] + bonus_d
            deltas.append(d / 100.0)
            outs.append(RESULT_TO_IDX[m["resultat"]])
            expected = 1.0 / (1.0 + 10 ** (-d / 400))
            score = {"V": 1.0, "N": 0.5, "D": 0.0}[m["resultat"]]
            change = self.k * self._goal_mult(int(m["bp"] - m["bc"])) * (score - expected)
            r[h] += change
            r[a] -= change
        self.ratings = r
        self.link = OrderedLogit(b0=0.6).fit(np.array(deltas), np.array(outs, dtype=int))
        return self

    def sample_probs(self, fixtures: pd.DataFrame, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        teams = sorted(self.ratings)
        idx = {t: i for i, t in enumerate(teams)}
        base = np.array([self.ratings[t] for t in teams])
        draws = base[None, :] + self.sigma * rng.standard_normal((n_draws, len(teams)))
        h = fixtures["home_team_id"].map(idx).to_numpy()
        a = fixtures["away_team_id"].map(idx).to_numpy()
        delta = (draws[:, h] - draws[:, a]) / 100.0
        return self.link.probs(delta)


@dataclass
class PoissonModel:
    """Poisson bayésien hiérarchique sur les buts (CSC inclus).

    log λ_dom = μ + home + att_dom − def_ext ; log λ_ext = μ + att_ext − def_dom.
    att_i = β_a·z_i + u_i, def_i = β_d·z_i + v_i, avec z l'indice de force a priori et u, v ~ N(0, τ²).
    Ajustement au MAP par Newton-Raphson, incertitude par approximation de Laplace. τ est choisi en maximisant
    la vraisemblance marginale (approximation de Laplace) sur une grille.
    """

    name: str = "Poisson bayésien"
    tau_grid: tuple[float, ...] = (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6)
    tau: float = 0.2
    theta: np.ndarray | None = None
    cov: np.ndarray | None = None
    team_index: dict[int, int] = field(default_factory=dict)
    z: np.ndarray | None = None
    max_goals: int = 12

    def _design(self, home_idx: np.ndarray, away_idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        n_t = len(self.team_index)
        n = len(home_idx)
        p = 4 + 2 * n_t
        xh, xa = np.zeros((n, p)), np.zeros((n, p))
        rows = np.arange(n)
        xh[:, 0] = xa[:, 0] = 1.0
        xh[:, 1] = 1.0
        xh[:, 2], xh[:, 3] = self.z[home_idx], -self.z[away_idx]
        xa[:, 2], xa[:, 3] = self.z[away_idx], -self.z[home_idx]
        xh[rows, 4 + home_idx] = 1.0
        xh[rows, 4 + n_t + away_idx] = -1.0
        xa[rows, 4 + away_idx] = 1.0
        xa[rows, 4 + n_t + home_idx] = -1.0
        return xh, xa

    def _prior(self, tau: float, mu0: float) -> tuple[np.ndarray, np.ndarray]:
        n_t = len(self.team_index)
        mean = np.zeros(4 + 2 * n_t)
        mean[0] = mu0
        sd = np.concatenate([[1.0, 0.3, 0.3, 0.3], np.full(2 * n_t, tau)])
        return mean, 1.0 / sd**2

    def _map(
        self, x: np.ndarray, y: np.ndarray, tau: float, mu0: float, offset: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray, float]:
        m0, prec = self._prior(tau, mu0)
        theta = m0.copy()
        off = np.zeros(len(y)) if offset is None else offset
        for _ in range(100):
            lam = np.exp(x @ theta + off)
            grad = x.T @ (y - lam) - prec * (theta - m0)
            hess = x.T @ (x * lam[:, None]) + np.diag(prec)
            step = np.linalg.solve(hess, grad)
            theta += step
            if np.max(np.abs(step)) < 1e-9:
                break
        lam = np.exp(x @ theta + off)
        hess = x.T @ (x * lam[:, None]) + np.diag(prec)
        loglik = float((y * np.log(lam) - lam - special.gammaln(y + 1)).sum())
        logprior = float(
            -0.5 * (prec * (theta - m0) ** 2).sum() + 0.5 * np.log(prec).sum() - 0.5 * len(theta) * np.log(2 * np.pi)
        )
        _, logdet = np.linalg.slogdet(hess)
        log_marginal = loglik + logprior + 0.5 * len(theta) * np.log(2 * np.pi) - 0.5 * logdet
        return theta, hess, log_marginal

    def fit(self, ctx: Context) -> "PoissonModel":
        self.team_index = {t: i for i, t in enumerate(ctx.team_ids)}
        z = np.array([float(ctx.strength.get(t, 0.0)) for t in ctx.team_ids])
        self.z = (z - z.mean()) / (z.std() or 1.0)
        rows = ctx.home_rows
        hi = rows["team_id"].map(self.team_index).to_numpy()
        ai = rows["opp_id"].map(self.team_index).to_numpy()
        xh, xa = self._design(hi, ai)
        x = np.vstack([xh, xa])
        away_rows = rows.assign(team_id=rows["opp_id"])
        y = np.concatenate([rows["bp"].to_numpy(float), rows["bc"].to_numpy(float)])
        y = y + np.concatenate([ctx.cancelled_goals(rows), ctx.cancelled_goals(away_rows)])
        offset = ctx.goal_note_slope * np.concatenate([ctx.bonus_note(rows), ctx.bonus_note(away_rows)])
        mu0 = np.log(max(y.mean(), 0.5)) if len(y) else np.log(2.0)
        best = None
        for tau in self.tau_grid:
            theta, hess, lm = self._map(x, y, tau, mu0, offset)
            if best is None or lm > best[3]:
                best = (tau, theta, hess, lm)
        self.tau, self.theta, hess, _ = best
        self.cov = np.linalg.inv(hess)
        return self

    def rates(self, fixtures: pd.DataFrame, theta: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
        hi = fixtures["home_team_id"].map(self.team_index).to_numpy()
        ai = fixtures["away_team_id"].map(self.team_index).to_numpy()
        xh, xa = self._design(hi, ai)
        th = self.theta if theta is None else theta
        return np.exp(xh @ th.T), np.exp(xa @ th.T)

    def sample_probs(self, fixtures: pd.DataFrame, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        thetas = rng.multivariate_normal(self.theta, self.cov, size=n_draws, method="cholesky")
        lh, la = self.rates(fixtures, thetas)
        lh, la = lh.T, la.T
        ph = sps.skellam.sf(0, lh, la)
        pd_ = sps.skellam.pmf(0, lh, la)
        return np.stack([ph, pd_, 1.0 - ph - pd_], axis=-1)

    def score_matrix(self, fixtures: pd.DataFrame) -> np.ndarray:
        """Loi jointe des scores (n_matchs, max_goals+1, max_goals+1) aux paramètres MAP."""
        lh, la = self.rates(fixtures)
        g = np.arange(self.max_goals + 1)
        ph = sps.poisson.pmf(g[None, :], lh[:, None])
        pa = sps.poisson.pmf(g[None, :], la[:, None])
        m = ph[:, :, None] * pa[:, None, :]
        return m / m.sum(axis=(1, 2), keepdims=True)

    def team_parameters(self) -> pd.DataFrame:
        n_t = len(self.team_index)
        th, sd = self.theta, np.sqrt(np.diag(self.cov))
        teams = list(self.team_index)
        att = th[2] * self.z + th[4 : 4 + n_t]
        dfn = th[3] * self.z + th[4 + n_t :]
        return pd.DataFrame(
            {
                "team_id": teams,
                "attaque": att,
                "defense": dfn,
                "attaque_sd": sd[4 : 4 + n_t],
                "defense_sd": sd[4 + n_t :],
            }
        )


BENCH = {"G": 1, "D": 2, "M": 2, "A": 2}
UNAVAILABLE_GWS = {"blesse": 2, "suspendu": 1}


@dataclass
class StructuralModel:
    """Simulation au niveau des joueurs : qui joue, quelle note, puis résultat.

    Pour chaque équipe : 11 probable dans sa formation la plus utilisée (meilleures notes rétrécies) et un banc de
    7 joueurs (1 G, 2 D, 2 M, 2 A). Chaque joueur joue avec une probabilité égale à son taux de jeu PL, mise à 0
    pendant 2 journées s'il est blessé, 1 s'il est suspendu, divisée par deux à la prochaine journée s'il est
    incertain. Un poste sans joueur disponible reçoit la note moyenne d'un Rotaldo.

    Notes, avec player_match_notes.csv (`mpg.notes`) : le joueur qui joue est titulaire en PL avec sa probabilité
    `p_titulaire_si_joue` et reçoit alors sa moyenne de titulaire (tirée une fois par saison simulée selon son
    incertitude a posteriori) + un bruit de match d'écart-type σ_t du poste ; sinon la note des remplaçants de son
    poste. Le 11 probable est choisi sur la note espérée. Sans ce fichier : note rétrécie des compos MPG + bruit σ
    commun. Le lien écart de note moyenne → résultat est un logit ordonné ajusté sur les matchs joués.
    """

    name: str = "Structurel (joueurs)"
    sigma_match: float = 1.0
    rotaldo_note: float = 2.4
    k_shrink: float = 10.0
    teams: dict[int, dict] = field(default_factory=dict)
    link: OrderedLogit = field(default_factory=lambda: OrderedLogit(b0=2.0))
    next_gw: int = 1

    def fit(self, ctx: Context) -> "StructuralModel":
        lu = ctx.lineups
        rot = lu.loc[lu["statut"] == "rotaldo", "note_brute"]
        self.rotaldo_note = float(rot.mean()) if len(rot) else 2.4
        notes = lu[lu["a_joue_irl"] & lu["player_key"].notna()]
        per_player = notes.groupby("player_key")["note_brute"]
        within = per_player.var(ddof=1).dropna()
        self.sigma_match = float(np.sqrt(within.mean())) if len(within) else 1.0
        self.next_gw = ctx.upto_gw + 1

        formations = ctx.tm.groupby("team_id")["formation"].agg(lambda s: s.mode().iloc[0] if len(s) else "3-4-3")
        median_play = float(ctx.players["taux_jeu"].median()) if ctx.players["taux_jeu"].notna().any() else 0.8
        mixture = "note_titulaire" in ctx.players
        rank_by = "note_esperee" if mixture else "note_retrecie"
        self.teams = {}
        for t in ctx.team_ids:
            roster = ctx.players[ctx.players["team_id"] == t]
            d, m, a = (int(x) for x in formations.get(t, "3-4-3").split("-"))
            slots = {"G": 1, "D": d, "M": m, "A": a}
            groups = {}
            for g in GROUPES:
                cand = roster[roster["poste_groupe"] == g].sort_values(rank_by, ascending=False)
                cand = cand.head(slots[g] + BENCH[g])
                n_c = len(cand)
                grp = {
                    "k": slots[g],
                    "p": cand["taux_jeu"].fillna(median_play).clip(0, 1).to_numpy(float),
                    "statut": cand["statut_performance"].to_numpy(),
                    "names": cand["joueur"].tolist(),
                }
                if mixture:
                    grp |= {
                        "mean": cand["note_titulaire"].to_numpy(float),
                        "sd_mean": cand["note_titulaire_sd"].to_numpy(float),
                        "sigma": cand["sigma_titulaire"].to_numpy(float),
                        "q": cand["p_titulaire_si_joue"].to_numpy(float),
                        "sub_mean": cand["note_remplacant"].to_numpy(float),
                        "sub_sigma": cand["sigma_remplacant"].to_numpy(float),
                    }
                else:
                    grp |= {
                        "mean": cand["note_retrecie"].to_numpy(float),
                        "sd_mean": self.sigma_match / np.sqrt(cand["n_notes"].to_numpy(float) + self.k_shrink),
                        "sigma": np.full(n_c, self.sigma_match),
                        "q": np.ones(n_c),
                        "sub_mean": np.zeros(n_c),
                        "sub_sigma": np.zeros(n_c),
                    }
                groups[g] = grp
            self.teams[t] = groups

        home = ctx.home_rows
        delta = (home["note_moy_brute"] - home["note_moy_brute_adv"]).to_numpy(float)
        self.link = OrderedLogit(b0=2.0).fit(delta, _outcomes(home))
        return self

    def _play_prob(self, grp: dict, gw: int) -> np.ndarray:
        ahead = gw - self.next_gw + 1
        p = grp["p"].copy()
        for i, s in enumerate(grp["statut"]):
            if s in UNAVAILABLE_GWS and ahead <= UNAVAILABLE_GWS[s]:
                p[i] = 0.0
            elif s == "incertain" and ahead == 1:
                p[i] *= 0.5
        return p

    def team_notes(self, team_id: int, gws: np.ndarray, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        """Note moyenne simulée du 11 aligné : tableau (n_draws, len(gws))."""
        total = np.zeros((n_draws, len(gws)))
        for grp in self.teams[team_id].values():
            k, n_c = grp["k"], len(grp["mean"])
            if n_c == 0:
                total += k * self.rotaldo_note
                continue
            true_mean = grp["mean"][None, :] + grp["sd_mean"][None, :] * rng.standard_normal((n_draws, n_c))
            p = np.stack([self._play_prob(grp, int(g)) for g in gws])
            avail = rng.random((n_draws, len(gws), n_c)) < p[None, :, :]
            chosen = avail & (np.cumsum(avail, axis=2) <= k)
            shape = (n_draws, len(gws), n_c)
            notes = true_mean[:, None, :] + grp["sigma"] * rng.standard_normal(shape)
            if (grp["q"] < 1).any():
                starts = rng.random(shape) < grp["q"]
                notes = np.where(starts, notes, grp["sub_mean"] + grp["sub_sigma"] * rng.standard_normal(shape))
            notes = np.clip(notes, 1.0, 10.0)
            n_chosen = chosen.sum(axis=2)
            total += (notes * chosen).sum(axis=2) + (k - n_chosen) * self.rotaldo_note
        return total / 11.0

    def sample_probs(self, fixtures: pd.DataFrame, n_draws: int, rng: np.random.Generator) -> np.ndarray:
        notes = {}
        for t in set(fixtures["home_team_id"]) | set(fixtures["away_team_id"]):
            rows = fixtures.index[(fixtures["home_team_id"] == t) | (fixtures["away_team_id"] == t)]
            sim = self.team_notes(int(t), fixtures.loc[rows, "gw"].to_numpy(), n_draws, rng)
            notes[int(t)] = dict(zip(rows, sim.T))
        delta = np.stack(
            [
                notes[int(r.home_team_id)][i] - notes[int(r.away_team_id)][i]
                for i, r in zip(fixtures.index, fixtures.itertuples())
            ],
            axis=1,
        )
        return self.link.probs(delta)


def default_models() -> list:
    return [EloModel(), PoissonModel(), StructuralModel()]
