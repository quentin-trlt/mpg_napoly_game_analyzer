import csv
import json
import logging
import re
import unicodedata
from pathlib import Path

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "csv"
BUDGET = 500
SEASON_MONTHS = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}
POS_GROUP = {"Gardiens": "G", "Défenseurs": "D", "Milieux": "M", "Attaquants": "A"}
FILL_TYPE = {"#F5F6F6": "reel", "#A2E4A2": "mpg"}
FORM_COLOR = {"#349734": "V", "#696D77": "N", "#D4332D": "D"}

log = logging.getLogger(__name__)


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", strip_accents(s).lower()).strip()


def num(s: str) -> float | None:
    s = s.strip().replace(",", ".").replace("M€", "").replace("M", "").replace("%", "").strip()
    if s in {"", "-"}:
        return None
    return float(s)


def write(name: str, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"no rows for {name}")
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / name).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    log.info("%s: %d rows", name, len(rows))


def split_sections(text: str) -> dict[str, list[str]]:
    parts = re.split(r"\s*#([RSM]) ", " " + text.strip())
    return {parts[i]: [t.strip() for t in parts[i + 1].split("¦")] for i in range(1, len(parts), 2)}


def after(tokens: list[str], label: str, offset: int = 1) -> str:
    return tokens[tokens.index(label) + offset]


def ordinal(s: str) -> int:
    return int(re.match(r"\d+", s).group())


def parse_team_files() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    teams, squads, typical, calendar = [], [], [], []
    paths = sorted(p for p in (RAW / "teams").glob("team_*.txt") if re.fullmatch(r"team_\d+", p.stem))
    for path in [*paths, RAW / "teams/team_2_resume.txt"]:
        team_id = int(re.search(r"team_(\d+)", path.stem).group(1))
        if team_id == 2:
            text = ("#R " + (RAW / "teams/team_2_resume.txt").read_text().split("Napoly Game¦", 1)[1]
                    + " #S " + (RAW / "teams/team_2_squad.txt").read_text().split("Effectif¦", 1)[1]
                    + " #M " + (RAW / "teams/team_2_matches.txt").read_text())
        else:
            text = path.read_text()
        sec = split_sections(text)
        r = sec["R"]
        name = r[0].strip()
        team = {
            "team_id": team_id,
            "mpg_team_id": f"mpg_team_UNRUAZCC_1_1_{team_id}",
            "team_name": name,
            "coach": after(r, "Entraineur"),
            "president": after(r, "Président"),
            "stade": after(r, "Stade"),
            "valeur_effectif_meur": num(after(r, "Valeur effectif")),
            "moy_11type_gen": num(after(r, "Moy. Gen")),
            "moy_11type_def": num(after(r, "Déf")),
            "moy_11type_mil": num(after(r, "Mil")),
            "moy_11type_att": num(after(r, "Att")),
        }
        ci = r.index("Classements de l'équipe")
        for label, col in [("Moyenne d'équipe", "rang_moyenne"), ("Attaque", "rang_attaque"),
                           ("Défense", "rang_defense"), ("Pire sélectionneur", "rang_pire_selectionneur"),
                           ("Rateaux", "rang_rateaux"), ("Précieux", "rang_precieux")]:
            team[col] = ordinal(r[r.index(label, ci) + 1])
        teams.append(team)

        si = r.index("Son 11 type") + 1
        slot = 0
        while r[si] in {"G", "DC", "DL", "MD", "MO", "A"}:
            slot += 1
            typical.append({"team_id": team_id, "slot": slot, "poste": r[si], "note_moy": num(r[si + 1]),
                            "joueur_affiche": r[si + 2], "prochain_adversaire_club": r[si + 3]})
            si += 4

        s = sec["S"]
        group, injured = None, False
        i = 0
        while i < len(s):
            t = s[i]
            if t in POS_GROUP:
                group = POS_GROUP[t]
                i += 5
                continue
            if t == "?":
                injured = True
                i += 1
                continue
            if t and i + 3 < len(s) and re.fullmatch(r"\d+ M", s[i + 2]) and re.fullmatch(r"\d+ M", s[i + 3]):
                squads.append({"team_id": team_id, "joueur": t, "club": s[i + 1], "poste_groupe": group,
                               "cote": num(s[i + 2]), "enchere": num(s[i + 3]), "flag_point_interrogation": int(injured)})
                injured = False
                i += 4
                continue
            i += 1

        m = sec.get("M", [])
        for j, t in enumerate(m):
            if re.fullmatch(r"J\.\d+", t) and m[j + 1] == "-":
                gw = int(t[2:])
                _, day, month = m[j + 2].split()[:3]
                month_n = SEASON_MONTHS[month.lower()]
                year = 2026 if month_n >= 8 else 2027
                home, mid, away = m[j + 3], m[j + 4], m[j + 5]
                calendar.append({"gw": gw, "date": f"{year}-{month_n:02d}-{int(day):02d}",
                                 "home": home.strip(), "away": away.strip(), "mid": mid})
    return teams, squads, typical, calendar


def parse_ranking(teams_by_name: dict[str, dict]) -> None:
    for line in (RAW / "ranking.txt").read_text().splitlines():
        cells, colors = line.split(" || ")
        c = cells.split("|")
        rank = int(c[0])
        vals = [x for x in c[1:] if x != ""]
        name, nums = vals[0], vals[1:]
        colors = colors.split(",")
        if len(nums) == 6:
            delta = int(nums[0]) * (1 if colors[0] == "#349734" else -1)
            nums, form_colors = nums[1:], colors[1:]
        else:
            delta, form_colors = 0, colors
        t = teams_by_name[name.strip()]
        t.update({"classement": rank, "variation_rang": delta, "g": int(nums[0]), "n": int(nums[1]),
                  "p": int(nums[2]), "diff_buts": int(nums[3]), "pts": int(nums[4]),
                  "forme": "".join(FORM_COLOR[x] for x in form_colors)})


def parse_equipes(teams_by_name: dict[str, dict]) -> None:
    tok = [t.strip() for t in (RAW / "equipes.txt").read_text().strip().split("¦")]

    def block(title: str, ncols: int, start_after: str) -> list[list[str]]:
        i = tok.index(start_after, tok.index(title)) + 1
        rows = []
        while i + ncols < len(tok) and tok[i].isdigit() and int(tok[i]) == len(rows) + 1:
            rows.append(tok[i + 1:i + 1 + ncols])
            i += 1 + ncols
        return rows

    for name, moy, moyb in block("Meilleure moyenne d'équipe", 3, "+B."):
        teams_by_name[name].update({"moy_equipe": num(moy), "moy_equipe_avec_bonus": num(moyb)})
    for name, r, m, b in block("Meilleure attaque", 4, "Buts"):
        teams_by_name[name].update({"buts_pour_reels": int(r), "buts_pour_mpg": int(m), "buts_pour_total": int(b)})
    for name, r, m, b in block("Meilleure défense", 4, "Buts"):
        teams_by_name[name].update({"buts_contre_reels": int(r), "buts_contre_mpg": int(m), "buts_contre_total": int(b)})
    for name, n in block("Pire sélectionneur", 2, "Rotaldos"):
        teams_by_name[name]["rotaldos_alignes"] = int(n)
    for name, n in block("Les rateaux", 2, "Contre"):
        teams_by_name[name]["bonus_subis"] = int(n)
    for name, occ, matchs in block("Mon précieux", 3, "Matchs"):
        teams_by_name[name].update({"precieux_occasions": int(occ), "precieux_matchs": int(matchs)})


def parse_leaderboards() -> tuple[list[dict], list[dict]]:
    tok = [t.strip() for t in (RAW / "buteurs.txt").read_text().strip().split("¦")]
    i = tok.index("Buts", tok.index("Meilleurs Buteurs")) + 1
    scorers = []
    while i + 6 < len(tok):
        club, pos = tok[i + 2].rsplit(" - ", 1)
        scorers.append({"rang": int(tok[i]), "joueur": tok[i + 1], "club": club, "poste": pos, "equipe_abrev": tok[i + 3],
                        "buts_reels": int(tok[i + 4]), "buts_mpg": int(tok[i + 5]), "buts_total": int(tok[i + 6])})
        i += 7

    tok = [t.strip() for t in (RAW / "joueurs.txt").read_text().strip().split("¦")]
    boards = []
    titles = [("Petro-green dollar", "ratio_achat_par_but", 5), ("Les meilleurs gardiens", "meilleurs_gardiens", 4),
              ("Les meilleurs défenseurs", "meilleurs_defenseurs", 4), ("Les meilleurs milieux", "meilleurs_milieux", 4),
              ("Les meilleurs attaquants", "meilleurs_attaquants", 4)]
    for title, cat, width in titles:
        i = tok.index(title)
        i = tok.index("#", i) + (6 if width == 5 else 5)
        rank = 1
        while i < len(tok) and tok[i] == str(rank):
            club, pos = tok[i + 2].rsplit(" - ", 1)
            row = {"categorie": cat, "rang": rank, "joueur": tok[i + 1], "club": club, "poste": pos,
                   "equipe_abrev": tok[i + 3], "achat": num(tok[i + 4])}
            if width == 5:
                row.update({"buts": int(tok[i + 5]), "valeur": num(tok[i + 6])})
            else:
                row["valeur"] = num(tok[i + 5])
            boards.append(row)
            i += 2 + width
            rank += 1
    return scorers, boards


def parse_data_tab() -> list[dict]:
    s = "".join((RAW / "data_chunks.txt").read_text().split("\n"))
    rows = []
    for r in s.split(";"):
        if not r:
            continue
        name, club, cote, note, buts, pos, titu, r1, r2, nxt = r.split("|")
        rows.append({"nom_data": name, "club": club, "cote": num(cote), "note_moy_reelle": num(note),
                     "buts_reels_saison": int(buts), "poste": pos, "pct_titularisations": num(titu),
                     "club_resultat_j8": r1, "club_resultat_j9": r2, "club_prochain_match": nxt})
    return rows


def parse_matches() -> dict[str, dict]:
    lines = [l.rstrip("\n") for l in (RAW / "match_chunks.txt").open(encoding="utf-8")]
    text = "".join(lines).replace("\\n", "\n")
    matches = {}
    for line in text.split("\n"):
        mid, header, scorers, bonus, best, forms, pitch, bench = line.split("~")
        rows = lambda s: [r.split("^") for r in s.split(";")] if s else []
        matches[f"mpg_division_match_UNRUAZCC_1_1{mid}"] = {
            "header": header,
            "scorers": [(int(a), b, c) for a, b, c in rows(scorers)],
            "bonus": [(int(a), int(b), c, d) for a, b, c, d in rows(bonus)],
            "best": best.split(";") if best else [],
            "formations": forms.split(",") if forms else [],
            "pitch": [(int(a), int(b), int(c), d, e, int(f)) for a, b, c, d, e, f in rows(pitch)],
            "bench": [(int(a), None, int(b), e, f, g, int(c), int(d)) for a, b, c, d, e, f, g in rows(bench)],
        }
    return matches


def match_name(short: str, full: str) -> bool:
    a, b = norm(short), norm(full)
    if a == b:
        return True
    m = re.fullmatch(r"(\w)\.\s+(.+)", short.strip())
    if m:
        initial, rest = norm(m.group(1)), norm(m.group(2))
        return b.startswith(initial) and (b.endswith(" " + rest) or b.split(" ", 1)[-1] == rest)
    return b.endswith(" " + a)


def resolve(short: str, candidates: list[dict], club: str | None = None) -> dict | None:
    pool = [c for c in candidates if club is None or c["club"] == club]
    hits = [c for c in pool if match_name(short, c["joueur"])]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        log.warning("ambiguous %s -> %s", short, [h["joueur"] for h in hits])
    return None


def player_key(full: str, club: str) -> str:
    return f"{norm(full).replace(' ', '_')}__{norm(club).replace(' ', '_')}"


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    OUT.mkdir(exist_ok=True)
    teams, squads, typical, calendar = parse_team_files()
    by_name = {t["team_name"]: t for t in teams}
    parse_ranking(by_name)
    parse_equipes(by_name)

    for p in squads:
        p["player_key"] = player_key(p["joueur"], p["club"])
    data = parse_data_tab()
    unmatched = []
    for d in data:
        hit = resolve(d["nom_data"], squads, d["club"])
        if hit is None:
            unmatched.append(d["nom_data"])
            continue
        hit.update({k: v for k, v in d.items() if k not in {"club", "cote"}})
        if hit["cote"] != d["cote"]:
            log.warning("cote mismatch %s: %s vs %s", hit["joueur"], hit["cote"], d["cote"])
    if unmatched:
        log.warning("data rows unmatched: %s", unmatched)

    assists = "".join((RAW / "assists_chunks.txt").read_text(encoding="utf-8").split("\n"))
    by_full = {(p["team_id"], p["joueur"], p["club"]): p for p in squads}
    for r in assists.split(";"):
        name, club, team_id, ast, goals = r.split("|")
        p = by_full.get((int(team_id), name, club))
        if p is None:
            raise ValueError(f"assists row not matched: {r}")
        if goals and int(goals) != p["buts_reels_saison"]:
            raise ValueError(f"goals mismatch for {name}: {goals} vs {p['buts_reels_saison']}")
        p["passes_decisives_saison"] = int(ast) if ast else (0 if goals else None)
    if any("passes_decisives_saison" not in p for p in squads):
        raise ValueError("some players have no assists row")

    status_labels = {1: "incertain", 2: "blesse", 3: "suspendu"}
    extra = "".join((RAW / "extra_stats_chunks.txt").read_text(encoding="utf-8").split("\n"))
    opt = lambda x: int(x) if x else None
    seen = set()
    for r in extra.split(";"):
        name, club, team_id, yellow, red, club_m, played, started, avg_pts, perf, goals = r.split("|")
        p = by_full.get((int(team_id), name, club))
        if p is None:
            raise ValueError(f"extra stats row not matched: {r}")
        if goals and int(goals) != p["buts_reels_saison"]:
            raise ValueError(f"goals mismatch for {name}: {goals} vs {p['buts_reels_saison']}")
        p.update({"cartons_jaunes": opt(yellow), "cartons_rouges": opt(red), "matchs_club": opt(club_m),
                  "matchs_joues": opt(played), "matchs_titulaire": opt(started),
                  "points_mpg_moy": float(avg_pts) if avg_pts else None,
                  "statut_performance": status_labels.get(opt(perf), "ok")})
        seen.add(p["player_key"])
    if len(seen) != len(squads):
        raise ValueError(f"extra stats cover {len(seen)} players out of {len(squads)}")

    by_team = {}
    for p in squads:
        by_team.setdefault(p["team_id"], []).append(p)
    for t in teams:
        roster = by_team[t["team_id"]]
        t["nb_joueurs"] = len(roster)
        for grp in "GDMA":
            t[f"nb_{grp}"] = sum(p["poste_groupe"] == grp for p in roster)
        t["total_enchere"] = sum(p["enchere"] for p in roster)
        t["total_cote"] = sum(p["cote"] for p in roster)
        t["budget_restant"] = BUDGET - t["total_enchere"]
        notes = [p["note_moy_reelle"] for p in roster if p.get("note_moy_reelle") is not None]
        t["note_moy_reelle_effectif"] = round(sum(notes) / len(notes), 3) if notes else None

    scorers, boards = parse_leaderboards()
    matches = parse_matches()

    abbrev = {}
    for m in matches.values():
        h = m["header"].split("¦")
        abbrev[h[7].strip()] = h[4]
        abbrev[h[12].strip()] = h[9]
    for t in teams:
        t["abrev"] = abbrev.get(t["team_name"])
    abbrev_to_id = {t["abrev"]: t["team_id"] for t in teams if t["abrev"]}
    for row in scorers + boards:
        row["team_id"] = abbrev_to_id.get(row["equipe_abrev"])
        hit = resolve(row["joueur"], by_team.get(row["team_id"], []), row["club"])
        row["player_key"] = hit["player_key"] if hit else None

    id_by_name = {t["team_name"]: t["team_id"] for t in teams}
    fixtures = {}
    for c in calendar:
        key = (c["gw"], id_by_name[c["home"]], id_by_name[c["away"]])
        score = re.fullmatch(r"(\d+) - (\d+)", c["mid"])
        fixtures[key] = {"gw": c["gw"], "date": c["date"], "home_team_id": key[1], "away_team_id": key[2],
                         "home_goals": int(score.group(1)) if score else None,
                         "away_goals": int(score.group(2)) if score else None,
                         "heure": None if score else c["mid"].replace(" ", ""),
                         "statut": "joue" if score else "a_venir"}

    lineups, goals, bonuses, best, subs = [], [], [], [], []
    for mid, m in matches.items():
        gw, _, hid, aid = map(int, re.search(r"_1_1_(\d+)_(\d+)_(\d+)_(\d+)$", mid).groups())
        h = m["header"].split("¦")
        hg, ag = map(int, h[8].split(" - "))
        f = fixtures.setdefault((gw, hid, aid), {"gw": gw, "home_team_id": hid, "away_team_id": aid})
        if f.get("home_goals") not in (None, hg) or f.get("away_goals") not in (None, ag):
            log.warning("score mismatch %s: calendar %s-%s vs page %s-%s", mid, f.get("home_goals"), f.get("away_goals"), hg, ag)
        f.update({"match_id": mid, "home_goals": hg, "away_goals": ag, "statut": "joue",
                  "home_formation": m["formations"][0] if m["formations"] else None,
                  "away_formation": m["formations"][1] if len(m["formations"]) > 1 else None})
        side_team = {0: hid, 1: aid}

        sub_in = {}
        for side, team, grp, name, pos, note, k, size in m["bench"]:
            if size == 2:
                partner = next(b for b in m["bench"] if b[0] == side and b[2] == grp and b[6] != k)
                if k == 1:
                    sub_in[(side, name)] = partner[3]
                    subs.append({"match_id": mid, "gw": gw, "team_id": side_team[side], "titulaire_sortant": partner[3],
                                 "type": "absence" if num(partner[5]) is None else "remplacement_tactique",
                                 "note_titulaire": num(partner[5]), "remplacant_entre": name, "note_remplacant": num(note)})
        for side, team, grp, name, pos, note, k, size in m["bench"]:
            if size == 2 and k == 1:
                continue
            hit = resolve(name, by_team[side_team[side]])
            lineups.append({"match_id": mid, "gw": gw, "team_id": side_team[side], "side": "dom" if side == 0 else "ext",
                            "joueur_affiche": name, "player_key": hit["player_key"] if hit else None,
                            "poste": pos,
                            "statut": ("remplacant_non_entre" if size == 1
                                       else "titulaire_absent" if num(note) is None else "titulaire_remplace_tactique"),
                            "note_avec_bonus": num(note), "capitaine": 0, "ligne_terrain": None, "position_ligne": None})
        for side, line, slot, name, note, cap in m["pitch"]:
            hit = resolve(name, by_team[side_team[side]])
            lineups.append({"match_id": mid, "gw": gw, "team_id": side_team[side], "side": "dom" if side == 0 else "ext",
                            "joueur_affiche": name, "player_key": hit["player_key"] if hit else None,
                            "poste": hit.get("poste") if hit else None,
                            "statut": ("rotaldo" if name == "Rotaldo"
                                       else "remplacant_entre" if (side, name) in sub_in else "titulaire"),
                            "note_avec_bonus": num(note), "capitaine": cap, "ligne_terrain": line, "position_ligne": slot})

        multi = json.loads((RAW / "goal_icons_multi.json").read_text())
        for side, label, fill in m["scorers"]:
            team_roster = by_team[side_team[side]]
            fills = multi.get(f"{mid.removeprefix('mpg_division_match_UNRUAZCC_1_1')}|{side}|{label}", [fill])
            if "Rotaldo" in label:
                kind, who = "rotaldo_csc", "Rotaldo"
            elif "(CSC)" in label:
                kind, who = "csc", label.replace("(CSC)", "").strip()
            else:
                kind, who = FILL_TYPE.get(fill, fill), label
            opp = by_team[side_team[1 - side]]
            hit = resolve(who, opp if kind == "csc" else team_roster) if who != "Rotaldo" else None
            for f in fills:
                goals.append({"match_id": mid, "gw": gw, "team_id": side_team[side], "side": "dom" if side == 0 else "ext",
                              "buteur_affiche": label, "type_but": kind if kind in {"csc", "rotaldo_csc"} else FILL_TYPE[f],
                              "player_key": hit["player_key"] if hit else None})

        for row, col, txt, icon in m["bonus"]:
            if not txt:
                continue
            parts = txt.split("|")
            bonuses.append({"match_id": mid, "gw": gw, "team_id": side_team[col], "side": "dom" if col == 0 else "ext",
                            "bonus": parts[0], "effet": parts[1] if len(parts) > 2 else None,
                            "cible_affiche": parts[-1] if len(parts) > 1 else None, "icone": icon})
        for rank, txt in enumerate(m["best"], 1):
            parts = txt.split("|")
            note, rest = parts[0], parts[1:]
            stats, name_parts = [], []
            i = 0
            while i < len(rest):
                if re.fullmatch(r"\d+", rest[i]) and i + 1 < len(rest) and not re.fullmatch(r"\d+", rest[i + 1]) and len(stats) < 3:
                    stats.append((rest[i + 1], int(rest[i])))
                    i += 2
                else:
                    name_parts.append(rest[i])
                    i += 1
            row = {"match_id": mid, "gw": gw, "rang": rank, "joueur": " ".join(name_parts), "note": num(note)}
            for j, (lab, val) in enumerate(stats, 1):
                row[f"stat{j}_libelle"], row[f"stat{j}_valeur"] = lab, val
            best.append(row)

    fixture_rows = sorted(fixtures.values(), key=lambda f: (f["gw"], f["home_team_id"]))
    for f in fixture_rows:
        f["home_team"] = next(t["team_name"] for t in teams if t["team_id"] == f["home_team_id"])
        f["away_team"] = next(t["team_name"] for t in teams if t["team_id"] == f["away_team_id"])
        if f["statut"] == "joue":
            f["resultat_dom"] = "V" if f["home_goals"] > f["away_goals"] else "N" if f["home_goals"] == f["away_goals"] else "D"

    for t in typical:
        hit = resolve(t["joueur_affiche"], by_team[t["team_id"]])
        t["player_key"] = hit["player_key"] if hit else None

    unresolved = [r for r in lineups + goals
                  if r["player_key"] is None and r.get("type_but") != "rotaldo_csc" and r.get("joueur_affiche") != "Rotaldo"]
    if unresolved:
        log.warning("unresolved player names: %s", sorted({(r.get("joueur_affiche") or r.get("buteur_affiche")) for r in unresolved}))

    write("teams.csv", teams)
    write("players.csv", squads)
    write("typical_xi.csv", typical)
    write("fixtures.csv", fixture_rows)
    write("mpg_scorers_ranking.csv", scorers)
    write("player_leaderboards.csv", boards)
    if matches:
        write("lineups.csv", lineups)
        write("substitutions.csv", subs)
        write("goals.csv", goals)
        write("bonus.csv", bonuses)
        write("best_players.csv", best)


if __name__ == "__main__":
    main()
