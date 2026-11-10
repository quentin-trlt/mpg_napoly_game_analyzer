# Ligue MPG « Napoly Game »

Premier League, 10 équipes, 18 journées. L'export courant s'arrête après la J5 : 5 journées jouées, soit 25 matchs. Côté Premier League, 10 des 38 journées sont jouées.

Les fichiers par match grossissent à chaque journée et contiennent toujours tout l'historique. Le code ne fige aucun nombre de journées : la dernière journée MPG jouée est `fixtures.loc[fixtures.statut == "joue", "gw"].max()` (`League.last_gw`), la dernière journée PL jouée `club_results.loc[club_results.statut == "joue", "pl_gw"].max()` (`League.pl_last_gw`).

## Clés de jointure

- `team_id` (0 à 9) : identifiant MPG de l'équipe (`mpg_team_UNRUAZCC_1_1_<team_id>`). On le retrouve dans tous les fichiers.
- `player_key` : `prenom_nom__club` normalisé (sans accents). Clé unique de `players.csv`. Elle est présente dans `lineups`, `goals`, `typical_xi`, `mpg_scorers_ranking` et `player_leaderboards`. Elle reste vide uniquement pour Rotaldo, le joueur fictif aligné quand un poste n'est pas pourvu.
- `match_id` : identifiant MPG du match (`..._<journée>_<n°>_<équipe dom>_<équipe ext>`). Clé de `fixtures` pour les matchs joués.
- `pl_match_id` : identifiant MPG d'un match de Premier League (`mpg_championship_match_…`), clé de `club_results` et `pl_goals`.
- `players.mpg_player_id` (`mpg_championship_player_…`) = `pl_goals.buteur_mpg_id` / `passeur_mpg_id`.
- `players.club` = `club_results.home_club` / `away_club` = `pl_goals.club`.
- `abrev` (teams) = `equipe_abrev` (classements de joueurs).

```
teams ─┬─< players ─┬─< lineups >── fixtures
       │            ├─< goals    >── fixtures
       │            └─< typical_xi
       └─< fixtures (home_team_id / away_team_id) ─┬─< bonus
                                                    ├─< substitutions
                                                    └─< best_players
players.club ──< club_results (home_club / away_club) ──< pl_goals (pl_match_id)
```

## Fichiers

| Fichier | Grain | Contenu |
|---|---|---|
| `teams.csv` | 1 ligne par équipe | Coach, président, stade, classement (G/N/P, diff, pts, variation de rang, forme), valeur de l'effectif, moyennes du 11 type, rangs internes (attaque, défense, pire sélectionneur, rateaux, précieux), buts pour/contre (réels/MPG), Rotaldos alignés, bonus subis, effectif par poste, total des enchères et des cotes, budget restant |
| `players.csv` | 1 ligne par joueur acheté (196) | Équipe MPG, club, poste, cote, prix d'enchère, `mpg_player_id`, puis les colonnes de l'onglet Data : note moyenne réelle, buts et passes décisives réels sur la saison, cartons, matchs du club, joués et titulaire, % de titularisations, points MPG moyens, statut (ok, blessé, suspendu) |
| `fixtures.csv` | 1 ligne par rencontre (90) | Calendrier complet J1 à J18 (`statut` : `joue` / `a_venir`) : date, heure, domicile/extérieur, score et formations des matchs joués |
| `lineups.csv` | 1 ligne par joueur et par match | Note (bonus inclus), capitaine, position sur le terrain, statut : titulaire, remplaçant entré, titulaire absent, remplacé tactiquement, remplaçant non entré, Rotaldo |
| `substitutions.csv` | 1 ligne par remplacement | Titulaire sortant, remplaçant entré, type (absence ou remplacement tactique), notes |
| `goals.csv` | 1 ligne par but | Buteur, type : `reel`, `mpg` (but accordé par MPG sur la note), `csc`, `rotaldo_csc`, `bloque` (affiché par MPG mais annulé, hors score) |
| `bonus.csv` | 1 ligne par bonus posé | Équipe qui l'a posé, bonus (Capitaine, Suarez, McDo+, Zahia, 4/5 défenseurs…), effet, cible |
| `best_players.csv` | 3 par match | Meilleurs joueurs du match avec leurs 3 stats mises en avant |
| `typical_xi.csv` | 11 par équipe | 11 type affiché par MPG, note moyenne de chaque joueur, prochain adversaire de son club |
| `mpg_scorers_ranking.csv` | 52 lignes | Classement des buteurs de la ligue (buts réels, buts MPG) |
| `player_leaderboards.csv` | 43 lignes | Classements de l'onglet Joueurs : meilleur ratio prix/but, meilleurs G/D/M/A |
| `bonus_stock.csv` | 1 ligne par bonus | Dotation de bonus de début de saison, identique pour toutes les équipes |
| `club_results.csv` | 1 ligne par match de PL (380) | Calendrier complet des 38 journées : date (ISO 8601 UTC), clubs et codes courts, score si joué, `statut` (`joue`, `a_venir`, `en_cours` pendant un match) |
| `pl_goals.csv` | 1 ligne par but de PL | Match, journée, club bénéficiaire, côté (`dom`/`ext`), type (`but`, `penalty`, `csc`, `annule_var`), minute, buteur et passeur (id MPG, nom, `player_key` vide si le joueur n'est dans aucune équipe de la ligue) |

## Points d'attention

- **Deux notes différentes.** `note_avec_bonus` (lineups) est la note du match MPG, bonus inclus : sa moyenne par équipe retombe exactement sur la colonne « +B. » du site. `note_moy_reelle` (players) est la moyenne sur la saison réelle de Premier League.
- **Valeur de l'effectif.** `valeur_effectif_meur` = somme des cotes + budget non dépensé. Seuls USPionvillePusitanos (5 M) et Tractou'pelle (25 M) n'ont pas dépensé tout leur budget. L'hypothèse d'un budget de 500 M vient des données, pas d'une règle lue sur le site.
- **Rang dans `teams.csv`.** `forme` donne les 5 derniers résultats (V/N/D, ordre chronologique), probablement plafonnés par MPG. Pour une autre fenêtre, la recalculer depuis `fixtures.csv` (`mpg.standings`). `variation_rang` est la variation de place affichée sur le classement.
- **Buts bloqués.** Un but `bloque` est affiché par MPG mais ne compte pas. Tout comptage passe par `League.scored_goals`, qui l'exclut ; la page Matchs l'affiche avec la mention « bloqué ».
- **Buts de Premier League.** Un `csc` est rangé du côté du club qui en profite, son buteur est le joueur adverse. `annule_var` ne compte pas. Les buts d'un joueur sont les lignes `but` et `penalty` avec son `buteur_player_key`, ses passes décisives les mêmes lignes avec son `passeur_player_key` (`mpg.premier_league.player_totals`).
- **Résultats et prochain match d'un club.** Ils se lisent dans `club_results.csv` (`mpg.premier_league.last_results`, `next_match`, `club_form`), plus dans `players.csv`.
- **Cheat Code 18-26.** Le malus de −0,5 porte sur les joueurs de champ adverses présents sur le terrain (remplaçants entrés compris, gardien et Rotaldos exclus). La note brute le retire.
- `flag_point_interrogation` = 1 pour les joueurs marqués d'un « ? » dans l'effectif (probablement incertains ou blessés).

## Vérifications effectuées

Ces contrôles passent tous. Ceux qui portent sur les données recalculables sont rejoués par `tests/test_consistency.py` et `tests/test_premier_league.py` :

- Scores = buts listés, hors buts bloqués.
- Scores de Premier League = buts de `pl_goals` hors `annule_var`.
- Buts et passes PL recalculés depuis `pl_goals` = `buts_reels_saison` et `passes_decisives_saison` pour les 196 joueurs.
- Classement G/N/P/pts/diff recalculé depuis les matchs = classement du site.
- Buts réels/MPG par équipe = onglet Équipes.
- Classement des buteurs = somme des buts des matchs.
- Moyennes « +B. » recalculées depuis les compositions.
- 11 joueurs alignés par équipe et par match.
- Rotaldos alignés.
- Cotes identiques entre fiches équipe et onglet Data.
- Prix d'achat identiques avec les classements de joueurs.
- Copie des matchs et de l'onglet Data contrôlée par somme de contrôle avec le navigateur.
