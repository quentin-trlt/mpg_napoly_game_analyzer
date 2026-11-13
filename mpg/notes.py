"""Loi de la note MPG d'un joueur quand il joue, estimée sur ses notes de PL (player_match_notes.csv).

Un remplaçant entré en jeu reçoit une note basse et resserrée (4,7 à 5,2 selon le poste, écart-type 0,5 à 0,7), un
titulaire une note plus haute et plus dispersée (5,2 à 5,7, écart-type 1,0 à 1,2). La note d'un match est donc un
mélange : titulaire avec la probabilité p_i, note ~ N(μ_i, σ_t²), où μ_i est la moyenne du joueur comme titulaire
rétrécie vers celle des titulaires de son poste (k = σ_t² / τ², τ² variance entre joueurs) ; sinon note ~ N(m_r, σ_r²),
commune au poste. p_i est sa part de titularisations rétrécie vers celle du poste.

Rejoué sur les journées de PL 3 à 10 (1 207 notes, chaque journée prédite avec les précédentes), ce mélange améliore
le log score des notes de +0,026 par note [IC 90 % +0,020 ; +0,032] face à une moyenne unique rétrécie vers le poste.
Une dispersion propre à chaque joueur ou un poids plus fort aux matchs récents n'apportent rien.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mpg.loader import GROUPES

START_PRIOR = 3.0
MIN_TAU2 = 0.01
DEFAULT = {"m": 5.3, "s2": 1.2, "tau2": 0.1, "ms": 4.9, "vs": 0.4, "q": 0.8}
SUB_GAP = 0.5
MIN_SUB_NOTES = 4


@dataclass(frozen=True)
class PosteNotes:
    m_titulaire: float
    s2_titulaire: float
    tau2: float
    m_remplacant: float
    s2_remplacant: float
    p_titulaire: float

    @property
    def k(self) -> float:
        return self.s2_titulaire / self.tau2

    @property
    def note_esperee(self) -> float:
        """Note attendue d'un joueur du poste dont on ne sait rien, quand il joue."""
        return self.p_titulaire * self.m_titulaire + (1 - self.p_titulaire) * self.m_remplacant


def _pooled_within(stats: pd.DataFrame) -> float:
    multi = stats[stats["size"] >= 2]
    dof = (multi["size"] - 1).sum()
    return float((multi["var"] * (multi["size"] - 1)).sum() / dof) if dof > 0 else np.nan


def fit_postes(notes: pd.DataFrame) -> dict[str, PosteNotes]:
    """Paramètres par poste (G, D, M, A). `notes` : lignes jouées avec `poste_groupe`, `note`, `titulaire`."""
    out = {}
    for g in GROUPES:
        d = notes[notes["poste_groupe"] == g]
        starts = d[d["titulaire"] == 1]
        stats = starts.groupby("player_key")["note"].agg(["mean", "var", "size"])
        m = float(starts["note"].mean()) if len(starts) else DEFAULT["m"]
        s2 = _pooled_within(stats)
        s2 = DEFAULT["s2"] if np.isnan(s2) else s2
        tau2 = float(stats["mean"].var(ddof=1) - s2 / stats["size"].mean()) if len(stats) > 2 else DEFAULT["tau2"]
        subs = d.loc[d["titulaire"] == 0, "note"]
        enough = len(subs) >= MIN_SUB_NOTES
        out[g] = PosteNotes(
            m_titulaire=m,
            s2_titulaire=s2,
            tau2=max(tau2, MIN_TAU2),
            m_remplacant=float(subs.mean()) if enough else m - SUB_GAP,
            s2_remplacant=float(subs.var(ddof=1)) if enough else DEFAULT["vs"],
            p_titulaire=float(d["titulaire"].mean()) if len(d) else DEFAULT["q"],
        )
    return out


def player_notes(notes: pd.DataFrame, players: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par joueur de `players` (indexée par player_key) : loi de sa note quand il joue.

    `notes` : lignes de player_match_notes (toutes, jouées ou non). Un joueur sans note reçoit l'a priori du poste,
    `note_poste`. Les paramètres par poste sont dans `attrs["postes"]`.
    """
    poste = players.set_index("player_key")["poste_groupe"]
    played = notes[notes["note"].notna()].assign(poste_groupe=lambda d: d["player_key"].map(poste))
    played = played[played["poste_groupe"].notna()]
    params = fit_postes(played)

    starts = played[played["titulaire"] == 1].groupby("player_key")["note"].agg(["mean", "size"])
    usage = played.groupby("player_key")["titulaire"].agg(["sum", "size"])
    out = pd.DataFrame(index=poste.index)
    par = {
        name: poste.map({g: getattr(p, attr) for g, p in params.items()})
        for name, attr in (
            ("m", "m_titulaire"),
            ("s2", "s2_titulaire"),
            ("tau2", "tau2"),
            ("ms", "m_remplacant"),
            ("vs", "s2_remplacant"),
            ("q", "p_titulaire"),
        )
    }
    n_t = starts["size"].reindex(out.index).fillna(0)
    xbar = starts["mean"].reindex(out.index).fillna(0)
    k = par["s2"] / par["tau2"]
    out["n_notes_pl"] = usage["size"].reindex(out.index).fillna(0).astype(int)
    out["n_titulaire_pl"] = n_t.astype(int)
    out["note_titulaire"] = (n_t * xbar + k * par["m"]) / (n_t + k)
    out["note_titulaire_sd"] = np.sqrt(1 / (n_t / par["s2"] + 1 / par["tau2"]))
    out["sigma_titulaire"] = np.sqrt(par["s2"])
    out["note_remplacant"] = par["ms"]
    out["sigma_remplacant"] = np.sqrt(par["vs"])
    n_sum = usage["sum"].reindex(out.index).fillna(0)
    out["p_titulaire_si_joue"] = (n_sum + START_PRIOR * par["q"]) / (out["n_notes_pl"] + START_PRIOR)
    q = out["p_titulaire_si_joue"]
    out["note_esperee"] = q * out["note_titulaire"] + (1 - q) * out["note_remplacant"]
    out["note_poste"] = poste.map({g: p.note_esperee for g, p in params.items()})
    out = out.rename_axis("player_key")
    out.attrs["postes"] = params
    return out
