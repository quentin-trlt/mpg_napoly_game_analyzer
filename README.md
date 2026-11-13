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
| `fpl_players.csv` | 1 ligne par joueur de la ligue (196) | Instantané Fantasy Premier League écrit par `build_fpl.py` : `element_id` FPL apparié au `player_key`, statut (`a`, `d`, `i`, `s`, `u`), `chance_next` (chance de jouer la prochaine journée, %), news, minutes, titularisations, buts, xG et xG/90 de la saison, prochaine journée PL, date de récupération |
| `fpl_history.csv` | 1 ligne par joueur et par match FPL | Minutes, titularisation, buts, CSC et xG de chaque match de PL joué (`round` = journée PL) |
| `player_match_notes.csv` | 1 ligne par joueur de la ligue et par journée de PL jouée (196 × 10) | Fiche joueur MPG : `pl_gw`, `pl_match_id` (vide si `pas_encore_au_club`), club à cette date, note MPG du match (vide s'il n'a pas joué), `a_joue`, `titulaire`, minutes, buts, passes, csc, `statut` (vide s'il a joué, `non_entre`, `blesse`, `suspendu`, `non_convoque`, `pas_encore_au_club`). Cartons toujours vides |

Les deux fichiers FPL se régénèrent après chaque export MPG avec `uv run python build_fpl.py`. Le script archive aussi `fpl_players.csv` dans `fpl_snapshots/fpl_players_PL<journée>.csv` : `chance_next` n'est plus consultable une fois la journée passée, et ces copies permettront de mesurer ce qu'elle apporte.

## Points d'attention

- **Probabilité de jouer.** Le modèle structurel des prédictions ne prend plus le taux de jeu de la saison mais un logit de P(minutes > 0) estimé sur `fpl_history.csv` (`mpg.playing_time`), recalculé à chaque journée avec les seules journées PL antérieures. Rejoué sur J1-J5 sans information postérieure, il réduit le RPS du modèle structurel (0,209 → 0,199) ; `experiments/backtest_engine.py` refait la comparaison. Sans les fichiers FPL, le taux de la saison reste utilisé.
- **Rejeu sans information postérieure.** Pour une journée passée, `build_context` reconstruit les joueurs tels qu'ils étaient avant elle depuis `player_match_notes.csv` (`mpg.point_in_time`) : note moyenne, matchs joués, titularisations, buts et passes sur les seuls matchs de PL commencés avant la journée, statut « ok », et l'indice de force qui en découle. Restent du jour la cote MPG et `points_mpg_moy`. Sans ce fichier, le rejeu garde les données du jour et ses scores sont optimistes (RPS du modèle structurel 0,191 avec fuite, 0,212 sans, avant le modèle de notes ci-dessous).
- **Loi des notes.** Un remplaçant entré en jeu en PL reçoit une note basse et resserrée (4,7 à 5,2 selon le poste), un titulaire une note plus haute et plus dispersée (écart-type ≈ 1,1). `mpg.notes` estime donc, sur `player_match_notes.csv`, la moyenne de chaque joueur comme titulaire (rétrécie vers celle des titulaires de son poste), sa probabilité d'être titulaire quand il joue, et la note des remplaçants de chaque poste. Les écarts de niveau entre joueurs sont faibles devant l'aléa d'un match (écart-type entre joueurs 0,2 à 0,6 selon le poste) : le rappel vers le poste est fort, surtout pour les gardiens. Sur les notes des journées PL 3 à 10, ce mélange améliore le log score de +0,026 par note [IC 90 % +0,020 ; +0,032] ; le modèle structurel l'utilise et passe de 0,212 à 0,199 de RPS. Avec ce fichier, `note_retrecie` (pages Joueurs, Mercato, Équipe) est cette note estimée, la note attendue quand le joueur joue, et `n_notes`, `note_moy`, `note_ecart_type` portent sur toutes ses notes de PL (`n_notes_ligue` garde le nombre de notes dans les compos MPG) ; sans lui, `note_retrecie` reste la moyenne des compos MPG rétrécie vers la moyenne PL. Le moteur du coach (`mpg.coach.projection`) tire lui aussi titulaire ou remplaçant, et estime choc de club, bruit et décalage des buteurs sur les titularisations de PL ; rejoué sur J3-J5, sa note prédite passe d'un RMSE de 1,12 à 1,06 et il surestime moins les buts (2,2 par équipe et par match contre 2,3 avant, 2,0 observés).
- **Ajustement à l'adversaire du coach.** Les coefficients qui relient la note aux buts du club sont estimés sur les buts réellement marqués et encaissés, mais appliqués aux buts attendus de `ClubStrength`. Deux corrections : la pénalisation du modèle de clubs (`STRENGTH_RIDGE`) passe de 2 à 8, valeur qui maximise la vraisemblance des buts de la journée suivante (+0,031 par but [IC 90 % −0,002 ; +0,064], journées PL 2 à 10 prédites avec les précédentes) ; avec 2, les buts attendus étaient deux fois trop dispersés (pente des buts réels sur les buts attendus 0,46 sur les journées 6 à 10, 0,86 avec 8). Ensuite, l'effet est multiplié par cette pente calculée sur la saison (`forecast_calibration`, 0,30 aujourd'hui), faible en début de saison. Rejoué sur J1-J5, le moteur passe d'un RPS de 0,235 à 0,227 avec les compos optimisées et de 0,245 à 0,235 avec les vraies compos ; l'ajustement n'a plus d'effet mesurable, ni positif ni négatif, sur la note prédite des titulaires.

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
- Note moyenne, matchs joués, titularisations, buts et passes recalculés depuis `player_match_notes` = `players.csv` pour les 196 joueurs ; matchs du club à un match près (2 joueurs transférés).
- Note de `player_match_notes` = `note_avec_bonus` des compos MPG, à un bonus près (écart de −2 à +1 par pas de 0,5), et égale pour les remplaçants non entrés.
- 11 joueurs alignés par équipe et par match.
- Rotaldos alignés.
- Cotes identiques entre fiches équipe et onglet Data.
- Prix d'achat identiques avec les classements de joueurs.
- Copie des matchs et de l'onglet Data contrôlée par somme de contrôle avec le navigateur.
