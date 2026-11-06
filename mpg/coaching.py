import re
import unicodedata

import pandas as pd

KEYS = ["match_id", "team_id"]


def _slots(formation: str) -> dict[str, int]:
    d, m, a = (int(x) for x in formation.split("-"))
    return {"G": 1, "D": d, "M": m, "A": a}


def optimal_lineups(lu: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    """Compare le 11 sur le terrain au meilleur 11 possible parmi la feuille de match (titulaires + banc).

    Le meilleur 11 respecte la formation choisie par le coach et se calcule sur les notes brutes
    (bonus retirés). Les postes impossibles à pourvoir valent la note moyenne d'un Rotaldo.
    MPG autorise parfois un remplacement à un autre poste : l'optimum est donc borné par le 11 réel.
    """
    rotaldo_note = lu.loc[lu["statut"] == "rotaldo", "note_brute"].mean()
    if pd.isna(rotaldo_note):
        rotaldo_note = 2.0
    formations = tm.set_index(KEYS)["formation"]
    rows = []
    for (match_id, team_id), sheet in lu.groupby(KEYS):
        actual = sheet.loc[sheet["sur_terrain"], "note_brute"].sum()
        pool = sheet[sheet["a_joue_irl"] & sheet["poste_groupe"].notna()]
        formation = formations.get((match_id, team_id))
        optimal = 0.0
        swaps = []
        for g, n in _slots(formation).items():
            ranked = pool[pool["poste_groupe"] == g].sort_values("note_brute", ascending=False)
            chosen = ranked.head(n)
            optimal += chosen["note_brute"].sum() + max(0, n - len(chosen)) * rotaldo_note
            swaps += chosen.loc[~chosen["sur_terrain"], "joueur_affiche"].tolist()
        optimal = max(optimal, actual)
        rows.append(
            {
                "match_id": match_id,
                "team_id": team_id,
                "somme_notes_11": actual,
                "somme_notes_optimal": optimal,
                "regret": optimal - actual,
                "oublies_sur_banc": ", ".join(swaps),
            }
        )
    return pd.DataFrame(rows)


def captain_report(lu: pd.DataFrame, bonus: pd.DataFrame) -> pd.DataFrame:
    caps = bonus[bonus["bonus"] == "Capitaine"][KEYS + ["cible_affiche", "effet_pts"]]
    pitch = lu[lu["sur_terrain"] & (lu["statut"] != "rotaldo")]
    best = (
        pitch.sort_values("note_brute", ascending=False)
        .groupby(KEYS)
        .head(1)[KEYS + ["joueur_affiche", "note_brute"]]
        .rename(columns={"joueur_affiche": "meilleur_choix", "note_brute": "note_meilleur_choix"})
    )
    team_mean = pitch.groupby(KEYS)["note_brute"].mean().rename("note_moy_equipe").reset_index()
    cap_notes = pitch[KEYS + ["joueur_affiche", "note_brute"]].rename(
        columns={"joueur_affiche": "cible_affiche", "note_brute": "note_capitaine"}
    )
    out = caps.merge(cap_notes, on=KEYS + ["cible_affiche"], how="left")
    out = out.merge(best, on=KEYS, how="left").merge(team_mean, on=KEYS, how="left")
    out["capitaine_a_joue"] = out["note_capitaine"].notna()
    out["ecart_vs_equipe"] = out["note_capitaine"] - out["note_moy_equipe"]
    out["ecart_vs_meilleur"] = out["note_capitaine"] - out["note_meilleur_choix"]
    return out


def bonus_usage(bonus: pd.DataFrame, tm: pd.DataFrame) -> pd.DataFrame:
    used = bonus[(bonus["bonus"] != "Capitaine") & bonus["effet_pts"].notna()]
    flagged = tm[KEYS + ["gw", "pts", "resultat", "opp_name"]].merge(
        used[KEYS + ["bonus", "effet", "cible_affiche"]], on=KEYS, how="inner"
    )
    return flagged.sort_values(["team_id", "gw"])


def bonus_effect(tm: pd.DataFrame) -> pd.DataFrame:
    """Points moyens avec et sans bonus (hors capitaine). Purement descriptif : la décision n'est pas aléatoire."""
    t = tm.assign(avec_bonus=tm["n_bonus_hors_capitaine"] > 0)
    return (
        t.groupby("avec_bonus")
        .agg(matchs=("pts", "size"), pts_moy=("pts", "mean"), note_moy=("note_moy", "mean"))
        .reset_index()
    )


def substitution_report(subs: pd.DataFrame) -> pd.DataFrame:
    s = subs.copy()
    s["gain_note"] = s["note_remplacant"] - s["note_titulaire"]
    return s


def formation_report(tm: pd.DataFrame) -> pd.DataFrame:
    return (
        tm.groupby("formation")
        .agg(
            matchs=("pts", "size"),
            pts_moy=("pts", "mean"),
            bp_moy=("bp", "mean"),
            bc_moy=("bc", "mean"),
            note_moy=("note_moy", "mean"),
        )
        .reset_index()
        .sort_values("matchs", ascending=False)
    )


def coaching_table(lu: pd.DataFrame, tm: pd.DataFrame, bonus: pd.DataFrame, subs: pd.DataFrame) -> pd.DataFrame:
    opt = optimal_lineups(lu, tm)
    cap = captain_report(lu, bonus)
    sub = substitution_report(subs)
    tactical = sub[sub["type"] == "remplacement_tactique"]

    out = (
        tm.groupby("team_id")
        .agg(
            team_name=("team_name", "first"),
            matchs=("match_id", "size"),
            absents_total=("n_absents", "sum"),
            absents_attendus=("absents_attendus", "sum"),
            rotaldos=("n_rotaldos", "sum"),
            capitaines_manques=("capitaine_manque", "sum"),
            bonus_utilises=("n_bonus_hors_capitaine", "sum"),
            formations=("formation", lambda s: ", ".join(f"{k} ×{v}" for k, v in s.value_counts().items())),
        )
        .reset_index()
    )
    out["pct_absents"] = out["absents_total"] / (11 * out["matchs"]) * 100
    out["absents_vs_attendus"] = out["absents_total"] - out["absents_attendus"]
    out = out.merge(
        opt.groupby("team_id")
        .agg(regret_moy=("regret", "mean"), regret_total=("regret", "sum"), regret_max=("regret", "max"))
        .reset_index(),
        on="team_id",
    )
    out["regret_note_moy"] = out["regret_moy"] / 11
    out = out.merge(
        cap.groupby("team_id")
        .agg(cap_ecart_vs_equipe=("ecart_vs_equipe", "mean"), cap_ecart_vs_meilleur=("ecart_vs_meilleur", "mean"))
        .reset_index(),
        on="team_id",
        how="left",
    )
    out = out.merge(
        tactical.groupby("team_id")
        .agg(remplacements_tactiques=("gain_note", "size"), gain_tactique_total=("gain_note", "sum"))
        .reset_index(),
        on="team_id",
        how="left",
    )
    out[["remplacements_tactiques", "gain_tactique_total"]] = out[
        ["remplacements_tactiques", "gain_tactique_total"]
    ].fillna(0)
    return out.sort_values("regret_moy").reset_index(drop=True)


NOT_STOCKED = {"capitaine", "4 defenseurs", "5 defenseurs"}


def bonus_key(name: str) -> str:
    """Nom de bonus normalisé : sans accents, minuscules, sans article initial (« La valise » = « Valise »)."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().strip()
    s = re.sub(r"^(la|le|les|l')\s*", "", s)
    return re.sub(r"\s+", " ", s)


def remaining_bonuses(bonus: pd.DataFrame, stock: pd.DataFrame, team_ids: list[int]) -> pd.DataFrame:
    """Bonus restants par équipe : dotation − bonus posés (un bonus posé est consommé, même sans effet).

    Les bonus posés absents de la dotation sont conservés avec une dotation nulle pour que l'écart soit visible.
    """
    used = bonus.assign(cle=bonus["bonus"].map(bonus_key))
    used = used[~used["cle"].isin(NOT_STOCKED)]
    st_ = stock.assign(cle=stock["bonus"].map(bonus_key))
    names = dict(zip(st_["cle"], st_["bonus"]))
    for cle, nom in zip(used["cle"], used["bonus"]):
        names.setdefault(cle, nom)
    dotation = dict(zip(st_["cle"], st_["quantite"]))

    rows = []
    for t in team_ids:
        mine = used[used["team_id"] == t]
        for cle, nom in names.items():
            u = mine[mine["cle"] == cle].sort_values("gw")
            rows.append(
                {
                    "team_id": t,
                    "bonus": nom,
                    "dotation": int(dotation.get(cle, 0)),
                    "utilises": len(u),
                    "journees": ", ".join(f"J{g}" for g in u["gw"]),
                    "cibles": ", ".join(str(c) for c in u["cible_affiche"].fillna("—")),
                }
            )
    out = pd.DataFrame(rows)
    out["restants"] = out["dotation"] - out["utilises"]
    out["hors_dotation"] = out["dotation"] == 0
    order = {cle: i for i, cle in enumerate(st_["cle"])}
    out["_o"] = out["bonus"].map(lambda b: order.get(bonus_key(b), len(order)))
    return out.sort_values(["team_id", "_o"]).drop(columns="_o").reset_index(drop=True)
