# Brief scraping : instantané FPL, notes par match, saisons passées

Trois tâches s'ajoutent à la routine d'export, par ordre de priorité. Les formats existants de `data/` ne changent pas.
Contexte : les modèles de prédiction sont calés sur 25 matchs seulement ; il faut plus de matchs et l'historique
complet des notes par joueur.

État au 2026-11-13 : tâche 2 livrée (`data/player_match_notes.csv`, PL J1 à J10, contrôles passés ; une correction
manuelle à conserver, voir plus bas). Tâches 1 et 3 à faire.

## Tâche 1 : à chaque export, instantané FPL (obligatoire)

Après la mise à jour de `data/`, et AVANT le premier coup d'envoi de la journée de Premier League :

    uv run python build_fpl.py

Le script interroge l'API publique Fantasy Premier League (sans compte) et écrit `data/fpl_players.csv`
(disponibilité, chance de jouer, news, xG), `data/fpl_history.csv` (minutes, titularisation, buts, xG par match) et
une archive `data/fpl_snapshots/fpl_players_PL<journée>.csv`. Cette archive est irremplaçable : FPL n'affiche la
chance de jouer que pour la journée à venir, donc un lancement après le coup d'envoi perd la journée.
Si le script signale des joueurs « sans correspondance FPL » : CSV `player_key,element_id` (l'element_id est dans
l'URL du joueur sur fantasy.premierleague.com), puis relancer avec `--overrides <fichier>`.
Versionner `data/fpl_snapshots/`, pas `data/fpl_cache/`.

## Tâche 2 : saison en cours, note MPG de chaque joueur à chaque journée de PL (livrée)

Fichier `data/player_match_notes.csv`, à mettre à jour à chaque export. Une ligne par joueur de la ligue et par
journée de PL depuis la J1 de PL (pas depuis le début de la ligue), y compris quand il n'a pas joué.
Source : historique des notes sur la fiche joueur MPG.

Colonnes :
- player_key, mpg_player_id : mêmes valeurs que players.csv
- pl_gw : journée de PL (numérotation de club_results.csv)
- pl_match_id : club_results.pl_match_id, vide si statut = pas_encore_au_club
- club : club du joueur à cette date (gère les transferts)
- note : note MPG du match affichée sur la fiche joueur, vide s'il n'a pas joué
- a_joue : 1 s'il est entré en jeu, 0 sinon
- titulaire (0/1), minutes
- buts, passes_decisives, csc : 0 si le joueur n'a pas joué
- carton_jaune, carton_rouge : toujours vides (MPG ne les affiche pas par match)
- statut : vide (a joué), non_entre, blesse, suspendu, non_convoque, pas_encore_au_club

Correspondance journées MPG ↔ PL : par date (fixtures.date dans la plage de dates de la journée PL). MPG J1-J5 =
PL J6-J10.

Recalcul de lineups.note_avec_bonus à partir de `note` :
- capitaine +0,5, McDo+ +1, Zahia +0,5 (titulaires seulement)
- bonus défense +0,5 avec 4 défenseurs, +1 avec 5 (défenseurs titulaires seulement)
- −1 par ligne d'écart pour un remplaçant qui remplace un titulaire d'une autre ligne
- bonus adverses : Suarez −1 sur le gardien, Cheat Code −0,5 sur les joueurs de champ

Contrôles avant livraison (signaler tout écart) :
- moyenne de `note` par joueur = players.note_moy_reelle (à l'arrondi près)
- somme de a_joue = players.matchs_joues ; somme de titulaire = players.matchs_titulaire ;
  somme de buts = players.buts_reels_saison ; somme de passes_decisives = players.passes_decisives_saison
- pour les joueurs alignés en MPG, note cohérente avec lineups.note_avec_bonus une fois les bonus retirés
- journées couvertes : de 1 à la dernière journée jouée de club_results

Correction manuelle à reporter dans l'export : `chuba_akpom__ipswich_town`, PL J9 (Hull–Ipswich, MPG J4). La fiche
joueur MPG le donne non_entre, mais il est entré en toute fin de match (1 minute selon FPL) et la feuille de match
MPG lui donne 4,5. Dans player_match_notes.csv : note = 4,5, a_joue = 1, titulaire = 0, minutes vide, statut vide.
Dans players.csv : matchs_joues = 8 (le site affiche 7). Tant que MPG n'a pas corrigé sa fiche, l'export doit
appliquer cette correction, sinon il la défait.

## Tâche 3 : saisons passées

Par préférence : 1) saisons passées de cette même ligue, 2) autres ligues MPG Premier League du compte,
3) ligues MPG Ligue 1. Les 2 ou 3 saisons les plus récentes suffisent (règles et bonus ont pu changer).

Ne JAMAIS écrire une saison passée à la racine de `data/` : l'app considère tout `data/*.csv` comme la saison en cours.
Un dossier par saison et par ligue :

    data/history/<saison>_<code_ligue>/
        meta.json, teams.csv, players.csv, fixtures.csv, lineups.csv, goals.csv, bonus.csv,
        substitutions.csv, bonus_stock.csv, club_results.csv, player_match_notes.csv

Mêmes colonnes et conventions que `data/` (team_id, player_key, match_id, statuts de lineups, types de goals,
ligne_terrain/position_ligne). Une colonne indisponible reste présente et vide. Le dossier doit se charger avec :

    uv run python -c "from mpg.loader import load_league; load_league('data/history/<dossier>')"

Priorités si tout n'est pas récupérable :
1. fixtures, lineups, goals, bonus, teams. Indispensables dans lineups : note_avec_bonus et ligne_terrain de chaque
   joueur sur le terrain (sinon le rejeu des scores est impossible).
2. substitutions, bonus_stock, players (effectif de fin de saison, à signaler dans meta.json).
3. player_match_notes, club_results.

meta.json :

    {"saison": "2025-2026", "championnat": "Premier League", "code_ligue": "…", "nom_ligue": "…",
     "nb_equipes": 10, "nb_journees": 18, "mode_remplacements": "tactique | live",
     "bonus": {"McDo+": 3, "Suarez": 2, …}, "regles_particulieres": "écarts observés avec les règles actuelles",
     "players_csv": "effectif de fin de saison", "recupere_le": "AAAA-MM-JJ", "source": "URL(s)"}

Contrôles par saison : ceux de la section « Vérifications effectuées » du README (scores = buts hors buts bloqués,
classement recalculé = classement du site, 11 joueurs sur le terrain par équipe et par match, moyennes « +B. »).
Une saison qui échoue à un contrôle est livrée quand même, avec l'écart décrit dans meta.json.

## Hors périmètre

- Pas de données FPL pour les saisons passées (l'API ne donne le détail par match que pour la saison en cours).
- Ne pas modifier build_csv.py, les modèles ou l'app.
- Requêtes espacées sur le site MPG, uniquement les données du compte.
