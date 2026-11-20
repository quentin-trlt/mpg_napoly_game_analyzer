# Ligue MPG « Napoly Game »

## L'app Streamlit

```
uv run streamlit run streamlit_app.py
```

L'app lit les CSV de `data/` et de `data/history/`. Le coach, `coach_app.py`, est une app séparée, à lancer en local avec `uv run streamlit run coach_app.py`. Il conseille la compo du prochain match MPG, garde ses réglages dans `.coach/` (listé dans `.gitignore`, mais `.coach/settings.json` est déjà suivi par git) et lit le même instantané FPL que l'app (`fpl_players.csv`, `fpl_history.csv`) : il ne télécharge plus rien lui-même. Son bouton « Rafraîchir les données FPL » relance `build_fpl.py`, ce qui met à jour les CSV pour les deux apps. Ce script écrit encore dans `data/fpl_cache/` (fichiers suivis par git : `git restore data/fpl_cache/bootstrap-static.json` annule la réécriture si tu ne veux pas la commiter).

### Navigation

Chaque page a sa propre adresse. Quand une page a plusieurs volets, le volet choisi s'ajoute à l'adresse (`/ligue?volet=matchs`) ; le premier volet n'y figure pas.

| Page | Adresse | Volets (`?volet=`) | Ce qu'elle répond |
|---|---|---|---|
| Ma journée | `/` (saison en cours) | aucun | Ton prochain match et où tu en es. Saison en cours seulement |
| Mon équipe | `/mon-equipe` | `profil`, `effectif`, `bonus` | Où en est mon équipe, que me reste-t-il ? Le volet Effectif montre le calendrier PL de tes joueurs |
| Ligue | `/ligue`, ou `/` sur une saison passée | `classement`, `matchs` (Matchs et calendrier) | Qui est où, qui a fait quoi ? Le volet Matchs propose un récap de la journée à copier pour le groupe |
| Pronostics | `/pronostics` | `journee`, `fin-de-saison`, `et-si`, `fiabilite` | Qui va gagner, et avait-on vu juste ? Sur une saison passée, un seul volet (`fin-de-saison`), qui montre le film de la saison |
| Pourquoi ce classement ? | `/pourquoi` | `favoris` (Favoris vs réalité), `chance`, `coaching` | Mérite, chance ou coaching ? Le volet Coaching rejoue chaque match avec ton meilleur 11 |
| Joueurs et mercato | `/joueurs-mercato` | `joueurs`, `mercato`, `analyse-mercato` (Classement des mercatos) | Qui sont les bons joueurs, qui a bien acheté ? |
| Palmarès | `/palmares` | aucun | Qui domine la ligue depuis le début, saisons et coachs confondus |

La page par défaut est servie à la racine `/` et non à son adresse propre : Ma journée sur la saison en cours, Ligue sur une saison passée (Ma journée n'y existe pas).

L'adresse porte aussi deux autres paramètres : `saison` (par exemple `?saison=2025-2026`) et `coach` (le pseudo retenu dans « Mon équipe »). Un favori du navigateur rouvre donc l'app sur la bonne saison et la bonne équipe.

### Saisons

Une saison est un dossier au format de `data/` (`mpg/seasons.py`). La saison en cours est `data/`. Les saisons passées sont dans `data/history/<saison>_<code_ligue>/` et ont un `meta.json`. `list_seasons` les range de la plus ancienne à la plus récente. La clé de la saison en cours se déduit de la dernière saison passée (2025-2026 donne 2026-2027). Le sélecteur de la barre latérale les propose de la plus récente à la plus ancienne. Sur une saison passée, la page d'ouverture est Ligue et Ma journée disparaît.

Le sélecteur « Mon équipe » liste les coachs de toutes les saisons. Un coach qui n'a pas joué la saison affichée ne fait pas planter la page : l'app montre le leader (le champion pour une saison passée) et le dit dans la barre latérale.

Les pseudos peuvent changer d'une saison à l'autre. `COACH_ALIASES` (`mpg/seasons.py`) dit quels pseudos désignent la même personne (aujourd'hui `vincentprono92` est `vincentmouly`), et `coach_key` est le seul endroit où on les rapproche. Le palmarès et la carrière d'un coach en dépendent.

Les données d'une saison n'ont pas toutes le même contenu. `capabilities(league, meta)` le lit dans les fichiers : cote, statistiques PL de la saison, FPL, matchs à venir, calendrier PL à venir, meilleurs joueurs par match, forme affichée par le site, président et stade, effectif de fin de saison. L'app masque ce qui manque et `limits` écrit une phrase par manque dans le bandeau « Saison passée, données partielles ». Aujourd'hui, les deux saisons passées n'ont ni cote, ni statistiques PL de la saison, ni FPL, ni calendrier PL à venir, ni meilleurs joueurs par match, et leurs effectifs sont ceux de fin de saison. 2024-2025 n'a en plus ni président ni stade.

Pour ajouter une saison, pose son dossier dans `data/history/<saison>_<code_ligue>/` avec ses CSV et un `meta.json` (au moins `saison`, comme `"2025-2026"`, car la clé de la saison en vient ; `"players_csv": "effectif de fin de saison"` si l'effectif est celui de fin de saison). Le test `tests/test_history.py::test_seasons_cover_the_three_folders` liste les saisons attendues : mets-le à jour. `tests/test_seasons.py` et `tests/test_analysis_seasons.py` passent ensuite sur la nouvelle saison sans autre changement.

### Tests

```
uv run pytest
uv run ruff check .
```

Les tests qui portent sur plusieurs saisons sont paramétrés sur `season_dirs()`, une saison par cas.

## Les données

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

Les deux fichiers FPL sont la source commune de l'app et du coach. Ils se régénèrent après chaque export MPG avec `uv run python build_fpl.py`, ou avec le bouton de rafraîchissement du coach, qui relance le même script (appariement forcé par `.coach/fpl_overrides.csv` s'il existe). Le script archive aussi `fpl_players.csv` dans `fpl_snapshots/fpl_players_PL<journée>.csv` : `chance_next` n'est plus consultable une fois la journée passée, et ces copies permettront de mesurer ce qu'elle apporte.

## Saisons passées

`data/history/<saison>_<code_ligue>/` contient d'autres saisons au même format que `data/` (et un `meta.json` qui décrit leur couverture et leurs écarts), chargeables avec `load_league` et `mpg.analysis.run`. Aujourd'hui : 2024-2025 (8 équipes, 14 journées, PL J8-J21) et 2025-2026 (10 équipes, 18 journées, PL J1-J18) de la ligue SRMEG7VW, où jouaient 7 des 10 coachs actuels. Le moteur de règles y retrouve les 146 scores (`tests/test_coach_rules.py`). Pas de cote MPG (l'indice de force se calcule alors sur les enchères, `strength.price_column`), pas d'instantané FPL, effectifs de fin de saison.

`uv run python -m experiments.backtest_seasons` rejoue chaque journée de chaque saison sans information postérieure (171 matchs) et compare les modèles par bootstrap apparié par saison. Le modèle structurel est le meilleur des journées 1 à 3 (RPS 0,247 contre 0,260 pour Poisson) mais le moins bon ensuite (0,253 contre 0,233) : il ne voit les équipes qu'à travers leurs joueurs. Son effet d'équipe (écart persistant de note dû à la gestion du coach, rétréci avec 8 matchs fictifs) le fait passer de 0,256 à 0,251 au total. L'ensemble n'utilise donc que le structurel pour prédire les journées 1 à 3, puis les trois modèles à poids égaux, ajustés des bonus restants (`ensemble_weights`) : 0,243 → 0,240 au total, 0,258 → 0,247 sur les journées 1 à 3. Choisi sur deux saisons et évalué sur la troisième, ce choix gagne 0,003 [IC 90 % −0,007 ; +0,001] ; des poids qui décroissent continûment, plus souples, font moins bien que les poids égaux hors échantillon.

## Points d'attention

- **Probabilité de jouer.** Le modèle structurel des prédictions ne prend plus le taux de jeu de la saison mais un logit de P(minutes > 0) estimé sur `fpl_history.csv` (`mpg.playing_time`), recalculé à chaque journée avec les seules journées PL antérieures. Rejoué sur J1-J5 sans information postérieure, il réduit le RPS du modèle structurel (0,209 → 0,199) ; `experiments/backtest_engine.py` refait la comparaison. Sans les fichiers FPL, le taux de la saison reste utilisé.
- **Rejeu sans information postérieure.** Pour une journée passée, `build_context` reconstruit les joueurs tels qu'ils étaient avant elle depuis `player_match_notes.csv` (`mpg.point_in_time`) : note moyenne, matchs joués, titularisations, buts et passes sur les seuls matchs de PL commencés avant la journée, statut « ok », et l'indice de force qui en découle. Restent du jour la cote MPG et `points_mpg_moy`. Sans ce fichier, le rejeu garde les données du jour et ses scores sont optimistes (RPS du modèle structurel 0,191 avec fuite, 0,212 sans, avant le modèle de notes ci-dessous).
- **Loi des notes.** Un remplaçant entré en jeu en PL reçoit une note basse et resserrée (4,7 à 5,2 selon le poste), un titulaire une note plus haute et plus dispersée (écart-type ≈ 1,1). `mpg.notes` estime donc, sur `player_match_notes.csv`, la moyenne de chaque joueur comme titulaire (rétrécie vers celle des titulaires de son poste), sa probabilité d'être titulaire quand il joue, et la note des remplaçants de chaque poste. Les écarts de niveau entre joueurs sont faibles devant l'aléa d'un match (écart-type entre joueurs 0,2 à 0,6 selon le poste) : le rappel vers le poste est fort, surtout pour les gardiens. Sur les notes des journées PL 3 à 10, ce mélange améliore le log score de +0,026 par note [IC 90 % +0,020 ; +0,032] ; le modèle structurel l'utilise et passe de 0,212 à 0,199 de RPS. Avec ce fichier, `note_retrecie` (pages Joueurs et mercato, Mon équipe) est cette note estimée, la note attendue quand le joueur joue, et `n_notes`, `note_moy`, `note_ecart_type` portent sur toutes ses notes de PL (`n_notes_ligue` garde le nombre de notes dans les compos MPG) ; sans lui, `note_retrecie` reste la moyenne des compos MPG rétrécie vers la moyenne PL. Le moteur du coach (`mpg.coach.projection`) tire lui aussi titulaire ou remplaçant, et estime choc de club et décalage des buteurs sur les titularisations de PL ; son bruit individuel est calé pour que le bruit total d'un titulaire (choc de club et lien aux buts compris) égale l'écart-type par poste de `mpg.notes`, avec un plancher de 0,3 ; rejoué sur J3-J5, sa note prédite passe d'un RMSE de 1,12 à 1,06 et il surestime moins les buts (2,2 par équipe et par match contre 2,3 avant, 2,0 observés).
- **Ajustement à l'adversaire du coach.** Les coefficients qui relient la note aux buts du club sont estimés sur les buts réellement marqués et encaissés, mais appliqués aux buts attendus de `ClubStrength`. Deux corrections : la pénalisation du modèle de clubs (`STRENGTH_RIDGE`) passe de 2 à 8, valeur qui maximise la vraisemblance des buts de la journée suivante (+0,031 par but [IC 90 % −0,002 ; +0,064], journées PL 2 à 10 prédites avec les précédentes) ; avec 2, les buts attendus étaient deux fois trop dispersés (pente des buts réels sur les buts attendus 0,46 sur les journées 6 à 10, 0,86 avec 8). Ensuite, l'effet est multiplié par cette pente calculée sur la saison (`forecast_calibration`, 0,30 aujourd'hui), faible en début de saison. Rejoué sur J1-J5, le moteur passe d'un RPS de 0,235 à 0,227 avec les compos optimisées et de 0,245 à 0,235 avec les vraies compos ; l'ajustement n'a plus d'effet mesurable, ni positif ni négatif, sur la note prédite des titulaires.

- **Deux notes différentes.** `note_avec_bonus` (lineups) est la note du match MPG, bonus inclus : sa moyenne par équipe retombe exactement sur la colonne « +B. » du site. `note_moy_reelle` (players) est la moyenne sur la saison réelle de Premier League.
- **Valeur de l'effectif.** `valeur_effectif_meur` = somme des cotes + budget non dépensé. Seuls USPionvillePusitanos (5 M) et Tractou'pelle (25 M) n'ont pas dépensé tout leur budget. L'hypothèse d'un budget de 500 M vient des données, pas d'une règle lue sur le site.
- **Rang dans `teams.csv`.** `forme` donne les 5 derniers résultats (V/N/D, ordre chronologique), probablement plafonnés par MPG. Pour une autre fenêtre, la recalculer depuis `fixtures.csv` (`mpg.standings`). `variation_rang` est la variation de place affichée sur le classement.
- **Buts bloqués.** Un but `bloque` est affiché par MPG mais ne compte pas. Tout comptage passe par `League.scored_goals`, qui l'exclut ; le volet Matchs et calendrier de la page Ligue l'affiche avec la mention « bloqué ».
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
