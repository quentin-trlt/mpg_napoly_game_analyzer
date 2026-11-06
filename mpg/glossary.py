GLOSSARY: dict[str, str] = {
    "petit_echantillon": (
        "Après {derniere_journee} journées, chaque équipe n'a joué que {derniere_journee} matchs. Un écart de 2 ou 3 "
        "points peut venir d'un seul penalty. Les intervalles affichés donnent l'ordre de grandeur de cette "
        "incertitude : quand ils contiennent 0, l'écart n'est pas distinguable du hasard."
    ),
    "indice_force": (
        "**Indice de force a priori.** Il résume la qualité de l'effectif sans regarder les résultats. "
        "Chaque caractéristique est convertie en z-score robuste, (x − médiane) / (1,4826 × MAD), puis pondérée : "
        "cote du meilleur 11 possible (45 %), note réelle moyenne de ce 11 en Premier League (30 %), cote du banc (15 %), "
        "taille de l'effectif (10 %).\n\n"
        "Le meilleur 11 possible est calculé en testant toutes les formations MPG (3-4-3 à 5-4-1) et en gardant "
        "celle qui maximise la somme des cotes. La médiane et la MAD remplacent la moyenne et l'écart-type pour "
        "qu'une équipe atypique ne déforme pas l'échelle des autres.\n\n"
        "**Limite.** La note réelle est une moyenne de saison PL : elle contient de l'information postérieure au mercato."
    ),
    "scenarios_force": (
        "**Scénarios de pondération.** Qui était favori dépend de ce qu'on regarde : la valeur totale, le 11 titulaire, "
        "la profondeur ou le niveau réel des joueurs. Chaque scénario recalcule l'indice avec d'autres poids, et la plage "
        "de rangs attendus montre à quel point le statut de favori dépend de l'hypothèse. Vous pouvez aussi composer "
        "votre propre pondération à partir de n'importe quelle caractéristique.\n\n"
        "La corrélation de chaque scénario avec les points réels est affichée à titre indicatif. Avec 10 équipes, "
        "retenir le scénario le mieux corrélé serait du sur-ajustement : il gagnerait en partie par hasard."
    ),
    "ecart_rang": (
        "**Écart de rang** = rang attendu − rang réel. Positif : l'équipe est mieux classée que ne le laisse prévoir "
        "son effectif (surperformance). Négatif : sous-performance."
    ),
    "cote_11_aligne": (
        "**Cote du 11 aligné.** Somme des cotes des 11 joueurs choisis comme titulaires par le coach, absents compris. "
        "Le taux d'utilisation la rapporte à la cote du meilleur 11 possible : un taux bas signifie que le coach "
        "laisse ses joueurs les plus chers de côté, par choix ou à cause des absences."
    ),
    "spearman": (
        "**Corrélation de Spearman (ρ).** Corrélation entre les rangs plutôt qu'entre les valeurs, donc insensible "
        "aux valeurs extrêmes et aux relations non linéaires. ρ = 1 : même ordre ; ρ = 0 : aucun lien monotone. "
        "Avec 10 équipes, il faut |ρ| > 0,64 environ pour atteindre p < 0,05."
    ),
    "force_ligne": (
        "**Force par ligne.** Note brute moyenne (bonus retirés) des joueurs alignés à chaque ligne sur tous les matchs "
        "joués. La colonne globale inclut les Rotaldos, pas les colonnes par ligne. Le nombre de notes (n) est affiché : "
        "la ligne G repose sur une note par match, donc sur très peu de valeurs."
    ),
    "points_vs_niveau": (
        "**Points contre niveau de jeu.** En abscisse, la note moyenne de l'équipe ; en ordonnée, ses points. "
        "La diagonale de référence est donnée par les xPts all-play : une équipe au-dessus a pris plus de points que "
        "son niveau ne le justifie."
    ),
    "note_brute": (
        "**Note brute.** Les notes affichées par MPG incluent les bonus (capitaine +0,5, défense à 4 ou 5, McDo+, "
        "Zahia, Suarez subi…). On les retire pour comparer les joueurs entre eux, et notamment titulaires et "
        "remplaçants. Contrôle : la moyenne des notes brutes retombe exactement sur la colonne « moyenne sans bonus » "
        "du site pour les équipes n'ayant aligné aucun Rotaldo. Les bonus à cible imprécise (Cheat Code) ne sont pas retirés."
    ),
    "all_play": (
        "**Classement « contre tout le monde » (all-play).** Chaque journée, on compare la note moyenne de l'équipe "
        "à celle des 9 autres, pas seulement à celle de son adversaire. Victoire si l'écart dépasse {bande_nul:.2f} "
        "point, nul sinon. Ce seuil est calibré pour reproduire le taux de nuls observé dans la ligue. "
        "Les points attendus (xPts) sont la moyenne des points de ces 9 matchs fictifs.\n\n"
        "La règle « à la note » prédit le bon résultat dans {concordance_regle_note:.0%} des matchs réels. MPG décide "
        "en réalité ligne par ligne (attaque contre défense, gardien), d'où l'écart."
    ),
    "chance_decomposition": (
        "**Décomposition de la chance.**\n\n"
        "- *Chance totale* = points réels − xPts all-play.\n"
        "- *Chance de calendrier* = points selon la règle de note contre les vrais adversaires − xPts all-play. "
        "Elle mesure le fait d'avoir croisé les adversaires au bon moment (un jour où ils étaient faibles).\n"
        "- *Chance de conversion* = points réels − points selon la règle de note. Elle mesure ce que la mécanique "
        "MPG (buts MPG, arrêts, Rotaldos) a donné ou repris à notes égales.\n\n"
        "Les deux composantes s'additionnent exactement en chance totale."
    ),
    "calendrier_permute": (
        "**Calendriers permutés.** On garde les notes de chaque équipe à chaque journée et on tire {n_sim:,} calendriers "
        "au hasard (appariements uniformes). Le percentile indique la part des calendriers qui auraient rapporté moins "
        "de points : 90 % veut dire que seuls 10 % des tirages faisaient mieux. La moyenne des tirages égale "
        "mathématiquement les xPts all-play, la simulation ajoute la dispersion."
    ),
    "pythagore": (
        "**xPts pythagoriciens (Poisson).** On estime le nombre moyen de buts marqués et encaissés par match, puis on "
        "suppose que les buts suivent deux lois de Poisson indépendantes. La différence suit une loi de Skellam, qui "
        "donne P(victoire) et P(nul). xPts = matchs × (3 P(V) + P(N)). Les taux sont rétrécis vers la moyenne de la "
        "ligue avec 1 match fictif, pour qu'une équipe muette en attaque n'ait pas un taux strictement nul.\n\n"
        "Une équipe au-dessus de ses xPts pythagoriciens a gagné ses matchs serrés et perdu les déroutes."
    ),
    "sur_regime_adv": (
        "**Sur-régime adverse.** Note de l'adversaire face à l'équipe, moins sa note moyenne sur ses autres matchs "
        "(leave-one-out). Positif : les adversaires ont joué au-dessus de leur niveau habituel contre elle."
    ),
    "indice_chance": (
        "**Indice de chance.** Moyenne de trois z-scores robustes : chance totale, chance pythagoricienne, et l'opposé "
        "du sur-régime adverse. Positif = chanceux. Les intervalles bootstrap à 90 % sur la chance totale "
        "rééchantillonnent les journées : avec {derniere_journee} journées, ils restent larges."
    ),
    "regret": (
        "**Points laissés sur le banc.** Pour chaque match, on construit le meilleur 11 possible parmi les joueurs de la "
        "feuille de match (titulaires et remplaçants ayant joué en vrai), dans la formation choisie, sur les notes brutes. "
        "Regret = somme des notes de ce 11 optimal − somme des notes du 11 sur le terrain. Diviser par 11 donne "
        "l'écart de note moyenne.\n\n"
        "**Limite.** C'est un regret a posteriori : le coach ne connaissait pas les notes au moment de composer. Il mesure "
        "à la fois la qualité des choix et la malchance."
    ),
    "capitaine": (
        "**Capitaine.** Le bonus de +0,5 n'est appliqué que si le capitaine joue. On compte les matchs sans capitaine "
        "effectif (non désigné ou absent), et on compare la note brute du capitaine à la moyenne de l'équipe et au meilleur "
        "joueur du match."
    ),
    "remplacements": (
        "**Remplacements.** Un remplacement *d'absence* fait entrer un remplaçant à la place d'un titulaire qui n'a pas "
        "joué en vrai ; sans remplaçant disponible au poste, MPG aligne un Rotaldo. Un remplacement *tactique* remplace un "
        "titulaire mal noté. Le gain tactique est la note du remplaçant moins celle du titulaire sorti."
    ),
    "absents": (
        "**Titulaires absents.** Part des titulaires choisis par le coach qui n'ont pas joué en vrai (blessure, banc en PL…). "
        "C'est la principale source de Rotaldos."
    ),
    "surpaiement": (
        "**Surpaiement.** Rapport enchère / cote, analysé en logarithme : log(enchère / cote). Le log rend l'échelle "
        "symétrique (payer 2 fois la cote ou la moitié donne +0,69 et −0,69) et réduit le poids des gros transferts. "
        "Au niveau équipe on prend la médiane, donc un achat à 127 M n'influence pas plus le résultat qu'un achat à 30 M. "
        "Le surpaiement global (somme des enchères / somme des cotes) est affiché pour comparaison : lui est dominé par "
        "les plus gros achats."
    ),
    "shrinkage": (
        "**Note rétrécie.** Après quelques matchs, une note moyenne MPG est très bruitée. On la combine avec une note "
        "a priori, la moyenne de saison du joueur en Premier League (à défaut, la médiane de son poste) :\n\n"
        "note rétrécie = (n × moyenne MPG + k × a priori) / (n + k)\n\n"
        "k = {k_shrinkage:.1f} est estimé sur les données : c'est le rapport entre la variance d'un match à l'autre pour "
        "un même joueur et la variance entre joueurs (modèle à effets aléatoires). Un k élevé signifie que quelques "
        "matchs MPG apportent peu d'information de plus que la moyenne de saison."
    ),
    "residu_valeur": (
        "**Rendement par rapport au prix.** Dans chaque poste, on ajuste par régression de Theil–Sen (médiane des pentes, "
        "robuste aux valeurs extrêmes) la note rétrécie sur log(enchère). Le résidu est la note du joueur moins la note "
        "attendue pour son prix. Positif : il rend plus que ce que son prix laissait espérer."
    ),
    "concentration": (
        "**Concentration du budget.** L'indice de Gini des enchères vaut 0 si tous les joueurs ont coûté pareil, et "
        "tend vers 1 si un joueur a absorbé tout le budget. Le HHI est la somme des parts au carré (1/n pour un budget "
        "parfaitement réparti). Une forte concentration rend l'équipe dépendante de la forme et de la santé d'une star."
    ),
    "equilibre": (
        "**Équilibre par ligne.** Part du budget consacrée à chaque ligne (G, D, M, A), comparée à la médiane de la ligue. "
        "L'écart est la somme des écarts absolus : 0 = répartition identique à la médiane."
    ),
    "score_mercato": (
        "**Score mercato.** Six composantes, toutes converties en z-score robuste entre les 10 équipes (signe choisi pour "
        "que plus haut = mieux) : rendement vs prix (moyenne tronquée à 10 % des résidus, 30 %), prix payé vs cote "
        "(surpaiement médian, 20 %), fiabilité (temps de jeu PL pondéré par le prix, 15 %), profondeur de banc "
        "(cote hors meilleur 11, 15 %), diversification (Gini, 10 %), équilibre par ligne (10 %).\n\n"
        "**Sensibilité.** Le classement est recalculé avec cinq jeux de poids et en retirant le joueur le plus cher de "
        "chaque équipe. La plage de rangs indique la robustesse : une équipe classée entre 2e et 10e selon les hypothèses "
        "n'a pas un mercato objectivement classable."
    ),
    "fiabilite": (
        "**Fiabilité du mercato.** Taux de jeu PL (matchs joués / matchs du club) moyen des joueurs, pondéré par leur "
        "enchère : Σ enchère × taux de jeu / Σ enchère. Acheter cher un joueur qui ne joue pas en vrai coûte des points "
        "en MPG (titulaire absent, Rotaldo). Le lien est mesurable dans la ligue : {corr_fiabilite_absents}.\n\n"
        "**Limite.** Le taux de jeu couvre toute la saison PL, y compris les journées antérieures au mercato."
    ),
    "absents_attendus": (
        "**Absences attendues.** Pour chaque titulaire choisi par le coach, la probabilité qu'il ne joue pas est estimée "
        "par 1 − son taux de jeu PL sur la saison. La somme sur les 11 titulaires et sur les matchs donne le nombre "
        "d'absences attendu. Plus d'absences que prévu : malchance (blessure, rotation imprévue). Un nombre attendu élevé "
        "signifie que le coach aligne des joueurs qui jouent peu, ce qui est un choix risqué. Validation : "
        "{corr_absents_attendus}."
    ),
    "production_pl": (
        "**Production PL.** Buts et passes décisives en Premier League sur la saison (G+A), rapportés au nombre de "
        "matchs joués. Le coût par G+A divise l'enchère par ce total. Il n'est calculé que pour les joueurs ayant au "
        "moins une contribution. Au niveau équipe on prend la médiane, pour qu'un seul gros achat très rentable "
        "ne décide pas du classement."
    ),
    "points_mpg": (
        "**Points MPG moyens et note réelle.** Les deux sont des moyennes de saison. Pour l'a priori de la note rétrécie, "
        "on a retenu la note réelle parce qu'elle prédit mieux les notes observées dans la ligue (RMSE {rmse_note_reelle:.2f} "
        "contre {rmse_points_mpg:.2f} pour les points MPG)."
    ),
    "discipline": (
        "**Discipline.** Cartons jaunes et rouges reçus en Premier League par les joueurs de l'effectif. Un rouge entraîne "
        "une suspension, donc une absence probable en MPG."
    ),
    "bootstrap": (
        "**Intervalle bootstrap à 90 %.** On rééchantillonne avec remise les unités observées (ici les journées) 5 000 fois et on "
        "recalcule l'indicateur. L'intervalle contient 90 % des valeurs obtenues."
    ),
    "simulation_saison": (
        "**Simulation de fin de saison.** Chaque match restant est tiré au sort selon les probabilités de l'ensemble, "
        "puis un score cohérent avec l'issue est tiré dans la loi du modèle de Poisson (pour départager à la "
        "différence de buts). On répète la saison {n_saisons:,} fois. P(titre) est la part des saisons simulées que "
        "l'équipe termine en tête ; l'intervalle de points couvre 90 % des saisons.\n\n"
        "Les tirages incluent l'incertitude sur la force des équipes, pas seulement le hasard des matchs : une équipe "
        "dont on connaît mal le niveau a une distribution de points plus large."
    ),
    "ensemble": (
        "**Ensemble.** Moyenne à poids égaux des probabilités des trois modèles (Elo, Poisson, structurel). Avec "
        "{matchs_backtest} matchs pour évaluer, on ne peut pas choisir le meilleur modèle de façon fiable ; la moyenne "
        "est plus robuste que n'importe quel modèle seul quand ceux-ci se trompent différemment."
    ),
    "modele_elo": (
        "**Elo.** Chaque équipe part de 1 500 + 100 × son indice de force a priori. Après chaque match, la note bouge "
        "selon l'écart entre le résultat et ce qui était attendu, amplifié pour les larges victoires. L'écart de notes "
        "est transformé en probabilités V/N/D par un logit ordonné ajusté sur les matchs joués (avec avantage du terrain)."
    ),
    "modele_poisson": (
        "**Poisson bayésien.** Les buts de chaque équipe suivent une loi de Poisson dont le taux dépend de son attaque, "
        "de la défense adverse et de l'avantage du terrain. L'attaque et la défense de chaque équipe sont tirées vers ce "
        "que prédit l'indice de force a priori : au début, l'effectif décide ; au fil des journées, les buts prennent "
        "le dessus. La force de ce rappel (τ = {tau:.2f}) est choisie par les données (vraisemblance marginale)."
    ),
    "modele_structurel": (
        "**Modèle structurel.** On simule chaque match au niveau des joueurs : le 11 probable dans la formation habituelle "
        "et un banc de 7, la probabilité que chacun joue (taux de jeu PL, 0 pendant 2 journées pour un blessé, 1 pour un "
        "suspendu), un Rotaldo à {rotaldo:.1f} si un poste reste vide, puis la note de chaque joueur (sa note rétrécie "
        "plus un aléa de match d'écart-type {sigma:.2f}). L'écart de note moyenne entre les deux équipes donne les "
        "probabilités V/N/D via un logit ordonné ajusté sur les matchs joués. C'est le seul modèle qui voit les blessures "
        "et le temps de jeu."
    ),
    "scores_prevision": (
        "**Mesurer une prévision probabiliste.**\n\n"
        "- *RPS* (ranked probability score) : écart entre les probabilités cumulées prédites et observées dans l'ordre "
        "victoire > nul > défaite. Prédire 60 % de victoire pour un nul est moins grave que pour une défaite. 0 = parfait.\n"
        "- *Log-loss* : −log de la probabilité donnée au résultat réel. Punit fort les certitudes démenties.\n"
        "- *Brier* : écart quadratique entre probabilités et résultat (0 = parfait, 2 = pire).\n\n"
        "Plus bas = meilleur pour les trois. La référence prédit les fréquences observées domicile / nul / extérieur "
        "pour tous les matchs : un modèle qui ne la bat pas n'apporte rien."
    ),
    "fuite_backtest": (
        "**Rejeu du passé et ses limites.** Chaque journée est prédite avec un modèle ajusté uniquement sur les "
        "journées précédentes. Mais les données joueurs (taux de jeu, moyennes PL, statut) sont celles d'aujourd'hui : "
        "le modèle structurel « connaît » un peu le futur et son score est optimiste. La seule évaluation sans biais "
        "est celle des pronostics figés avant chaque journée, plus bas."
    ),
    "et_si": (
        "**Mode « et si ».** Fixez l'issue de matchs à venir : ils sont imposés dans toutes les saisons simulées, les "
        "autres restent tirés au sort. L'écart avec la simulation de référence mesure l'enjeu de chaque match. "
        "Les forces des équipes ne sont pas réajustées après un résultat imposé, ce qui sous-estime légèrement l'effet "
        "d'une série de victoires."
    ),
    "pronostics_figes": (
        "**Pronostics figés.** Avant chaque journée, `python -m mpg.forecast` enregistre dans `content/pronostics/` "
        "les probabilités de chaque modèle pour la journée suivante (`J05.csv`) et un instantané de la fin de saison "
        "simulée (`saison_J05.csv`). Ces fichiers ne sont jamais réécrits. Une fois les matchs joués, l'app les note "
        "automatiquement : c'est la seule mesure de qualité sans biais, puisque le modèle ne pouvait pas connaître "
        "le résultat. Pensez à commiter le dossier : Streamlit Cloud ne conserve pas les fichiers écrits par l'app."
    ),
    "bonus_restants": (
        "**Bonus restants.** Dotation de début de saison (fichier `data/bonus_stock.csv`, identique pour toutes les "
        "équipes) moins les bonus déjà posés, d'après `bonus.csv`. Un bonus posé compte comme utilisé même s'il n'a "
        "eu aucun effet (joueur ciblé absent, par exemple). Le capitaine et les bonus à 4 ou 5 défenseurs ne sont pas "
        "comptés : le premier se choisit à chaque match, les seconds dépendent de la formation."
    ),
    "calibration": (
        "**Calibration.** On regroupe toutes les probabilités annoncées (3 par match) par tranche et on compare à la "
        "fréquence à laquelle l'issue s'est réellement produite. Un modèle bien calibré a ses points sur la diagonale : "
        "quand il annonce 60 %, l'issue arrive environ 6 fois sur 10. Au-dessus de la diagonale, il est trop prudent ; "
        "en dessous, trop sûr de lui. La taille du point indique le nombre de cas."
    ),
}


def explain(key: str, **context: object) -> str:
    text = GLOSSARY[key]
    try:
        return text.format(**context)
    except (KeyError, ValueError):
        return text
