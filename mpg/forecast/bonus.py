"""Valeur des bonus MPG et leur effet sur les prévisions.

Chaque bonus est converti en déplacement de la variable latente du logit ordonné (x, en faveur de l'équipe qui
le pose). Les bonus qui jouent sur les notes passent par la pente note → résultat estimée sur la ligue ; La valise
à Nanard, qui annule un but, passe par la loi des scores du modèle de Poisson. Le Miroir est résolu match par match.
"""

import numpy as np
import pandas as pd

from mpg.coaching import bonus_key

MCDO, VALISE, SUAREZ, CHEAT, ZAHIA, MIROIR, F424, TONTON = (
    bonus_key(b)
    for b in ("McDo+", "La valise à Nanard", "Suarez", "Cheat Code 18-26", "Zahia", "Miroir", "424", "Tonton Pat")
)
KNOWN = (MCDO, VALISE, SUAREZ, CHEAT, ZAHIA, MIROIR, F424, TONTON)
TACTICAL_PRIOR_MATCHES = 4.0


def defence_bonus_note(formation: str) -> float:
    """Bonus défensif automatique de la formation, en note moyenne d'équipe (4 déf. : +0,5 chacun ; 5 déf. : +1)."""
    n_def = int(str(formation).split("-")[0]) if isinstance(formation, str) and "-" in formation else 3
    return {4: 4 * 0.5, 5: 5 * 1.0}.get(n_def, 0.0) / 11


def note_value(key: str, formation: str, opp_tactical_gain: float, start_share: float) -> float:
    """Avantage de note moyenne (sur 11) apporté par un bonus à l'équipe qui le pose. 0 si non chiffrable en note.

    - McDo+ : +1 sur un titulaire de champ → +1/11.
    - Suarez : −1 sur le gardien adverse → +1/11 d'écart.
    - Cheat Code : −0,5 sur les 10 joueurs de champ adverses → +5/11 d'écart.
    - Zahia : +0,5 sur chaque titulaire choisi qui joue vraiment (part `start_share`).
    - 424 : passage en 4-2-4, qui donne le bonus de 4 défenseurs ; gain nul ou négatif pour une équipe qui
      l'a déjà ou joue à 5 (on suppose alors qu'elle le pose quand il ne coûte rien → borné à 0).
      L'effet offensif de 4 attaquants n'est pas modélisé.
    - Tonton Pat : l'adversaire perd le gain moyen de ses remplacements tactiques.
    """
    if key == MCDO or key == SUAREZ:
        return 1 / 11
    if key == CHEAT:
        return 5 / 11
    if key == ZAHIA:
        return 0.5 * start_share
    if key == F424:
        return max(0.0, 2 / 11 - defence_bonus_note(formation))
    if key == TONTON:
        return max(0.0, opp_tactical_gain) / 11
    return 0.0


def valise_shift(score_matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Déplacement latent obtenu en annulant un but adverse, pour le domicile et pour l'extérieur.

    Approximation : on retire un but au score de l'adversaire (Y → max(Y − 1, 0)), sans distinguer les CSC.
    """

    def latent(m: np.ndarray) -> np.ndarray:
        g = m.shape[1]
        hg, ag = np.indices((g, g))
        ph = (m * (hg > ag)).sum(axis=(1, 2))
        pa = (m * (hg < ag)).sum(axis=(1, 2))
        ph, pa = np.clip(ph, 1e-9, 1 - 1e-9), np.clip(pa, 1e-9, 1 - 1e-9)
        return (np.log(ph / (1 - ph)) - np.log(pa / (1 - pa))) / 2

    base = latent(score_matrix)
    away_minus = np.concatenate(
        [
            score_matrix[:, :, :1] + score_matrix[:, :, 1:2],
            score_matrix[:, :, 2:],
            np.zeros_like(score_matrix[:, :, :1]),
        ],
        axis=2,
    )
    home_minus = np.concatenate(
        [
            score_matrix[:, :1, :] + score_matrix[:, 1:2, :],
            score_matrix[:, 2:, :],
            np.zeros_like(score_matrix[:, :1, :]),
        ],
        axis=1,
    )
    return latent(away_minus) - base, base - latent(home_minus)


def apply_shift(probs: np.ndarray, shift: np.ndarray) -> np.ndarray:
    """Décale la variable latente du logit ordonné en conservant le seuil de nul de chaque match."""
    ph = np.clip(probs[..., 0], 1e-9, 1 - 1e-9)
    pa = np.clip(probs[..., 2], 1e-9, 1 - 1e-9)
    lh, la = np.log(ph / (1 - ph)), np.log(pa / (1 - pa))
    x, c = (lh - la) / 2, np.maximum(-(lh + la) / 2, 0.0)
    x = x + shift
    new_h = 1 / (1 + np.exp(-(x - c)))
    new_a = 1 / (1 + np.exp(-(-x - c)))
    return np.stack([new_h, 1 - new_h - new_a, new_a], axis=-1)


def _value_table(keys: list[str], fixtures: pd.DataFrame, score_matrix: np.ndarray, ctx) -> np.ndarray:
    """val[k, j, côté] : avantage latent du bonus k posé par le domicile (côté 0) ou l'extérieur (côté 1)."""
    n = len(fixtures)
    val = np.zeros((len(keys) + 1, n, 2))
    v_home, v_away = valise_shift(score_matrix)
    home, away = fixtures["home_team_id"].to_numpy(), fixtures["away_team_id"].to_numpy()
    for k, key in enumerate(keys):
        if key == VALISE:
            val[k, :, 0], val[k, :, 1] = v_home, v_away
            continue
        for j in range(n):
            for side, (me, opp) in enumerate(((home[j], away[j]), (away[j], home[j]))):
                dn = note_value(key, ctx.formations.get(me, "3-4-3"), ctx.tactical_gain.get(opp, 0.0), ctx.start_share)
                val[k, j, side] = ctx.note_slope * dn
    return val


def bonus_shifts(
    ctx, fixtures: pd.DataFrame, score_matrix: np.ndarray, n_sims: int, rng: np.random.Generator
) -> np.ndarray | None:
    """Déplacement latent (n_sims, n_matchs) dû aux bonus restants, en faveur du domicile.

    Dans chaque saison simulée, les bonus restants d'une équipe sont répartis au hasard sur ses matchs restants,
    au plus un par match. Un Miroir renvoie le bonus adverse au profit de celui qui l'a posé ; sans bonus adverse,
    il est perdu.
    """
    stock = ctx.bonus_remaining
    if stock is None or fixtures.empty:
        return None
    stock = stock[stock["restants"] > 0].assign(cle=lambda d: d["bonus"].map(bonus_key))
    if stock.empty:
        return np.zeros((n_sims, len(fixtures)))
    keys = sorted(stock["cle"].unique())
    k_idx = {k: i for i, k in enumerate(keys)}
    none = len(keys)
    mirror = k_idx.get(MIROIR, -2)
    val = _value_table(keys, fixtures, score_matrix, ctx)

    n = len(fixtures)
    posted = np.full((n_sims, n, 2), none)
    rows = np.arange(n_sims)[:, None]
    home, away = fixtures["home_team_id"].to_numpy(), fixtures["away_team_id"].to_numpy()
    for team, grp in stock.groupby("team_id"):
        items = np.repeat([k_idx[c] for c in grp["cle"]], grp["restants"].to_numpy())
        matches = np.flatnonzero((home == team) | (away == team))
        if len(matches) == 0 or len(items) == 0:
            continue
        sides = np.where(home[matches] == team, 0, 1)
        k = min(len(items), len(matches))
        slots = np.argsort(rng.random((n_sims, len(matches))), axis=1)[:, :k]
        chosen = rng.permuted(np.tile(items, (n_sims, 1)), axis=1)[:, :k]
        posted[rows, matches[slots], sides[slots]] = chosen

    cols = np.arange(n)[None, :]
    b_home, b_away = posted[:, :, 0], posted[:, :, 1]
    adv_home = val[b_home, cols, 0]
    adv_away = val[b_away, cols, 1]
    home_mirror, away_mirror = b_home == mirror, b_away == mirror
    real_away = (b_away != none) & ~away_mirror
    real_home = (b_home != none) & ~home_mirror
    adv_home = np.where(home_mirror, np.where(real_away, val[b_away, cols, 0], 0.0), adv_home)
    adv_away = np.where(away_mirror, np.where(real_home, val[b_home, cols, 1], 0.0), adv_away)
    adv_home = np.where(away_mirror & real_home, 0.0, adv_home)
    adv_away = np.where(home_mirror & real_away, 0.0, adv_away)
    return adv_home - adv_away


def past_bonus_effects(
    bonus: pd.DataFrame, tm: pd.DataFrame, formations: dict, tactical_gain: dict, start_share: float
) -> pd.DataFrame:
    """Avantage de note net des bonus de stock déjà posés, par équipe et par match, et buts annulés par une Valise.

    Sert à ne pas créditer Elo et Poisson d'une force qui venait d'un bonus consommé. Un bonus posé sans effet
    (effet vide dans bonus.csv) ne compte pas.
    """
    keys = ["match_id", "team_id"]
    b = bonus.assign(cle=bonus["bonus"].map(bonus_key))
    b = b[b["cle"].isin(KNOWN) & b["effet_pts"].notna() | b["cle"].isin((VALISE, MIROIR, F424, TONTON))]
    out = tm[keys + ["opp_id"]].copy()
    out["d_note"] = 0.0
    out["buts_annules"] = 0
    if b.empty:
        return out
    opp = tm.set_index(keys)["opp_id"]
    posted = b.groupby(keys)["cle"].first()
    for (match_id, team_id), key in posted.items():
        if (match_id, team_id) not in opp.index:
            continue
        rival = int(opp.loc[(match_id, team_id)])
        rival_key = posted.get((match_id, rival))
        beneficiary, applied = team_id, key
        if key == MIROIR:
            if rival_key is None or rival_key == MIROIR:
                continue
            applied = rival_key
        elif rival_key == MIROIR:
            beneficiary, applied = rival, key
        target = rival if beneficiary == team_id else team_id
        if applied == VALISE:
            out.loc[(out["match_id"] == match_id) & (out["team_id"] == target), "buts_annules"] += 1
            continue
        dn = note_value(applied, formations.get(beneficiary, "3-4-3"), tactical_gain.get(target, 0.0), start_share)
        out.loc[(out["match_id"] == match_id) & (out["team_id"] == beneficiary), "d_note"] += dn
        out.loc[(out["match_id"] == match_id) & (out["team_id"] == target), "d_note"] -= dn
    return out


def fit_goal_note_slope(tm: pd.DataFrame, default: float = 0.5) -> float:
    """Pente γ de log(buts) sur l'écart de note brute avec l'adversaire (régression de Poisson, a priori N(0.5, 0.5²))."""
    d = tm.dropna(subset=["note_moy_brute", "note_moy_brute_adv"])
    if len(d) < 6:
        return default
    x = np.column_stack([np.ones(len(d)), (d["note_moy_brute"] - d["note_moy_brute_adv"]).to_numpy()])
    y = d["bp"].to_numpy(float)
    prior_mean, prior_prec = np.array([np.log(max(y.mean(), 0.5)), default]), np.array([1e-4, 4.0])
    theta = prior_mean.copy()
    for _ in range(50):
        lam = np.exp(x @ theta)
        grad = x.T @ (y - lam) - prior_prec * (theta - prior_mean)
        hess = x.T @ (x * lam[:, None]) + np.diag(prior_prec)
        step = np.linalg.solve(hess, grad)
        theta += step
        if np.abs(step).max() < 1e-10:
            break
    return float(theta[1])


def tactical_gains(subs: pd.DataFrame, tm: pd.DataFrame) -> dict[int, float]:
    """Gain de note moyen des remplacements tactiques par match, rétréci vers la moyenne de la ligue."""
    tac = subs[subs["type"] == "remplacement_tactique"]
    gain = (tac["note_remplacant"] - tac["note_titulaire"]).groupby(tac["team_id"]).sum()
    played = tm.groupby("team_id").size()
    if played.empty:
        return {}
    league = float(gain.sum() / played.sum())
    k = TACTICAL_PRIOR_MATCHES
    return {int(t): float((gain.get(t, 0.0) + k * league) / (n + k)) for t, n in played.items()}
