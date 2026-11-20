# Design system

Ce document décrit l'interface telle qu'elle est dans le code. Les valeurs viennent de `app/theme.py`, les composants de `app/components.py`, les graphiques de `app/charts.py` et la navigation de `app/navigation.py`. Quand le code et ce document divergent, le code a raison : corrige le document.

## 1. Principes

Les textes s'adressent à l'utilisateur au tutoiement (« Ton match », « Impose des résultats »). Les titres de page sont des questions auxquelles la page répond, par exemple « Où en est mon équipe, que me reste-t-il ? » ou « Qui va gagner, et avait-on vu juste ? » (`app/pages.py`). On évite le jargon : un terme technique va dans le glossaire (`mpg/glossary.py`, dictionnaire `GLOSSARY`), affiché dans un dépliant par `how(...)`.

Les pourcentages sont arrondis à l'entier : `PCT_FORMAT = "%.0f %%"` pour les tableaux, `fmt_pct` pour le texte. Le code écrit une espace simple avant le `%`, pas une espace insécable. Si tu veux l'insécable, il faut changer `PCT_FORMAT`, `PCT_SIGNED_FORMAT` et `fmt_pct` ensemble.

Un tableau montre cinq colonnes au plus (`MAX_SHORT_COLUMNS = 5`). Le reste est dans un dépliant « Toutes les colonnes ». Sur téléphone, la première colonne (le nom) reste épinglée et les autres passent en largeur `small`. Une valeur manquante s'affiche « — » (`placeholder` de `short_table`).

Aucune vue ne contient de style en ligne, de balise `<style>`, de `unsafe_allow_html` ni de couleur en dur. `tests/test_design_system.py` le vérifie pour toutes les vues, et interdit aussi les couleurs en dur dans `components.py` et `charts.py`. Tout le HTML passe par `st.html` dans `components.py`, le CSS par `theme.py`.

## 2. Tokens

Toutes les couleurs sont dans `app/theme.py`. Les rapports de contraste ci-dessous sont des ratios WCAG calculés sur ces valeurs, contre `SURFACE` (`#131C2E`). Aucun test du dépôt ne les vérifie : `tests/test_design_system.py` ne contrôle que l'absence de couleur en dur.

| Nom | Valeur | Usage | Contraste sur `SURFACE` |
|---|---|---|---|
| `BG` | `#0B1120` | fond de l'application, aussi `backgroundColor` du thème Streamlit | |
| `SURFACE` | `#131C2E` | cartes, graphiques, barre latérale | |
| `SURFACE_2` | `#1B2538` | fond des infobulles de graphique | |
| `BORDER` | `rgba(255,255,255,0.08)` | filets et bordures de cartes | |
| `GRID` | `#1F2A3F` | quadrillage des graphiques | |
| `AXIS` | `#334155` | axes, points « éteints » | |
| `WHITE` | `#FFFFFF` | texte sur pastilles V et D | |
| `TEXT` | `#E2E8F0` | texte principal | 13,8 |
| `TEXT_2` | `#94A3B8` | texte secondaire, sous-titres | 6,6 |
| `MUTED` | `#8A97AC` | légendes, sous-lignes | 5,8 |
| `ACCENT` | `#22C55E` | surtitre du hero, focus clavier, `primaryColor` | 7,5 |
| `ME` | `#3987E5` | mon équipe (barres, liseré, couleur de série 1) | 4,7 |
| `ME_TINT` | `#8DB8F0` | libellé en texte de « mon équipe » | 8,3 |
| `ME_BG` | `#17253F` | fond teinté de mon équipe | |
| `GOOD` | `#17A34A` | ton `good` (alertes, pastilles, rangs 1 à 3) | 5,2 |
| `WARN` | `#FAB219` | ton `warn` | 9,3 |
| `BAD` | `#E66767` | ton `bad` | 5,3 |
| `RES_V`, `RES_N`, `RES_D` | `#15803D`, `#FAB219`, `#C53030` | pastilles Victoire, Nul, Défaite (`RESULT_COLORS`) | texte blanc sur V : 5,0 ; sur D : 5,5 |
| `P_HOME`, `P_DRAW`, `P_AWAY` | `#2563C9`, `#5A6B86`, `#B8480F` | barre de probabilité domicile, nul, extérieur | texte blanc : 5,7 ; 5,4 ; 5,3 |
| `GOLD`, `SILVER`, `BRONZE` | `#E0B341`, `#B8C4D6`, `#C58A5A` | médailles (texte `BG` dessus) | |
| `BADGE_COLORS` | huit couleurs sobres : `#2563C9`, `#B8480F`, `#0F766E`, `#7C3AED`, `#BE185D`, `#4D7C0F`, `#A16207`, `#0E7490` | fond des pastilles de coach (`coach_badge`) | texte blanc : 4,9 à 6,0 |
| `SERIES` | `#3987E5`, `#D95926`, `#199E70`, `#9085E9` | couleurs de séries dans les graphiques | |
| `HIGHLIGHT` | `ME` | mise en avant d'une équipe dans un graphique | |
| `CONTEXT`, `CONTEXT_DIM`, `CONTEXT_LIGHT` | `#59687F`, `#2A3A55`, `#8FA3BF` | les autres équipes, en gris | `CONTEXT` : 3,0 |
| `POS`, `NEG`, `NEUTRAL` | `ME`, `BAD`, `#334155` | écarts positifs, négatifs, nuls | |
| `LINE_COLORS`, `LINE_LABELS` | G `#C98500`, D `#3987E5`, M `#D95926`, A `#199E70` | lignes du terrain | |
| `SEQUENTIAL` | six bleus de `#16233A` à `#3987E5` | cartes de chaleur | |
| `DIVERGING` | `NEG`, `NEUTRAL`, `POS` | cartes de chaleur à deux sens | |

`CONTEXT` est fait pour des barres et des points, pas pour du texte. `rgba(couleur, alpha)` produit une couleur transparente à partir d'une valeur `#RRGGBB` et lève `ValueError` sinon.

Autres constantes : `SPACE = (4, 8, 12, 16, 24)` en pixels, `RADIUS_CARD = 14`, `RADIUS_TABLE = 12`, `RADIUS_PILL = 999`, `BP_PHONE = 640`, `BP_TABLET = 1100`, `FONT_FLOOR_REM = 0.75`.

`.streamlit/config.toml` reprend `primaryColor`, `backgroundColor`, `secondaryBackgroundColor` (`SURFACE`) et `textColor` en valeurs littérales, avec `base = "dark"`. Si tu changes `ACCENT`, `BG`, `SURFACE` ou `TEXT`, change aussi ce fichier à la main.

## 3. Typographie et espacements

Deux familles, servies en local depuis `static/fonts/` (`enableStaticServing = true`) et déclarées par des blocs `[[theme.fontFaces]]` dans `.streamlit/config.toml`. Aucun appel à un CDN.

`FONT` est Fira Sans (corps de texte, 12 fichiers : graisses 400, 500, 600 et 700, sous-ensembles cyrillique, latin et latin étendu). `DISPLAY` est Barlow Condensed (titres, grands chiffres, 6 fichiers : graisses 500, 600 et 700, latin et latin étendu). Les licences SIL OFL 1.1 sont dans `static/fonts/OFL-FiraSans.txt` et `static/fonts/OFL-BarlowCondensed.txt`. Garde-les en place si tu ajoutes une fonte.

Dans le CSS : `hero .title` fait 2,9 rem (2,15 rem sous 640 px), `volet-title .title` 2 rem (1,75 rem), un titre `h3` de section 1,55 rem en Barlow Condensed (1,4 rem sur téléphone), `h2` 1,35 rem. Les grands chiffres des `kpi_row` font 2,15 rem, ou 1,6 rem avec `small`. Les étiquettes courantes tournent autour de 0,8 à 0,95 rem ; `FONT_FLOOR_REM = 0.75` sert de taille minimale (le petit total des médailles). Dans les graphiques, le gabarit `napoly` impose Fira Sans 13 px, graduations à 12 px, étiquettes de fin de ligne à 11 px (10 px sur téléphone).

Les marges verticales courantes passent par des classes utilitaires : `.mt-6`, `.mt-8`, `.mt-12`, `.pt-6`. `.mt-8` et `.mt-12` lisent `SPACE`. La largeur utile est limitée à 1320 px (`.block-container`). Les cartes ont `RADIUS_CARD`, les tableaux `RADIUS_TABLE`, les pastilles `RADIUS_PILL`.

`inject_css()` injecte tout le CSS d'un coup ; il est appelé par `streamlit_app.py` et `coach_app.py`. Le gabarit Plotly `napoly` est enregistré à l'import de `app.theme` et devient le gabarit par défaut.

## 4. Composants

Tous les composants HTML sont dans `app/components.py`. Ceux qui renvoient une chaîne (`prob_bar`, `rank_list`, `next_match`, `alert`, `alerts`, `chip`, `chips`, `medal`, `grid`, `form_badges`, `stat_grid`) s'affichent avec `st.html(...)` ou s'insèrent dans une autre carte. Les autres écrivent directement dans la page. Tout texte venant des données passe par `html.escape`.

### Page

`hero(eyebrow: str, title: str, subtitle: str = "") -> None` : le grand titre d'une page, avec un surtitre vert. Une fois par page, en haut.

```python
hero(_eyebrow(a, "Mon équipe"), "Où en est mon équipe, que me reste-t-il ?")
```

`volet_title(title: str, subtitle: str = "") -> None` : le titre d'un volet, plus petit que le hero. Le sous-titre accepte du HTML, donc échappe-le toi-même s'il contient des données.

```python
volet_title(team["team_name"], f"{line}<br>{form_badges(form)}" if form else line)
```

`section(title: str, caption: str = "") -> None` : un `st.subheader` sans ancre, avec une légende.

```python
section("Classement final")
```

`limit_banner(caps: list[str], title: str = "Saison passée, données partielles") -> None` : un bandeau listant ce qui manque. Ne fait rien si la liste est vide.

```python
limit_banner(meta["limites"])
```

`empty_state(title: str, reason: str) -> None` : à la place d'un bloc qu'on ne peut pas calculer. Dis ce qui manque et pourquoi.

```python
empty_state(
    "Cette page ne concerne que la saison en cours",
    "Pour une saison passée, la Ligue montre le classement final et les matchs.",
)
```

`no_data(msg: str = "Pas encore de données pour cette section.") -> None` : un `st.info` pour un cas plus discret qu'`empty_state`.

`callout(text: str, warn: bool = False) -> None` : une phrase de lecture, ou un avertissement avec `warn=True`. `text` est du HTML non échappé.

```python
callout(f"Nouveaux cette saison, sans historique dans la ligue : {escape(', '.join(newcomers))}.")
```

`how(key: str | list[str], meta: dict, title: str = "Comment c'est calculé") -> None` : un dépliant qui affiche une ou plusieurs entrées du glossaire, formatées avec `meta`.

```python
how("score_mercato", meta)
```

`alert(icon: str, text_html: str, detail: str = "", tone: str = "warn") -> str` : une ligne d'alerte avec icône. Les tons admis sont `ALERT_TONES = ("good", "warn", "bad", "mid")`, sinon `ValueError`. `alerts(items: list[str]) -> str` les empile.

```python
alert(
    "⏱",
    f"Compo à valider avant <b>{DAYS[deadline.weekday()]} {deadline:%d/%m à %H:%M}</b>",
    "Coup d'envoi du premier match de Premier League de la journée.",
    "good",
)
```

### Contenu

`kpi_row(items: list[dict]) -> None` : une bande de chiffres clés. Chaque dictionnaire accepte `label`, `value`, `sub`, `small` (valeur en plus petit, pour du texte) et `me` (liseré bleu). La grille passe à deux colonnes sous `BP_TABLET`.

```python
kpi_row(
    [
        {"label": "Formation", "value": lu.formation, "sub": f"Capitaine : {rec.name(lu.captain)}"},
    ]
)
```

`stat_grid(cells: list[str], per_row: int = 4) -> str` : la même grille avec des cellules HTML déjà prêtes, complétée de cases vides. Utilisée pour les bonus de `equipe.py`.

```python
st.html(stat_grid([_bonus_cell(r, finished) for r in mine.itertuples()], per_row=4))
```

`chip(text: str, tone: str | None = None, off: bool = False) -> str` et `chips(items: list[str | dict]) -> str` : des pastilles. Les tons admis sont `CHIP_TONES = (None, "good", "bad")`, sinon `ValueError`. `chips` accepte des textes ou des dictionnaires d'arguments de `chip`.

```python
chip("Favori vainqueur", tone="good") if ok else chip("Surprise", tone="bad")
```

`medal(rank: float | None, n: int | None = None) -> str` : une pastille de rang, or, argent et bronze pour 1, 2 et 3. Un rang absent ou NaN donne « · ».

`form_badges(results: str) -> str` : la série de résultats, une lettre `V`, `N` ou `D` par pastille.

`coach_badge(coach: str) -> str` : une pastille ronde aux initiales du coach, à placer devant son nom. Initiales : celles des deux premiers mots (« Jean Pierre » : JP, « vincentMouly » : VM), sinon les deux premières lettres (« Emilinho_ » : EM). La couleur vient d'un hachage stable de `coach_key(coach)` dans `BADGE_COLORS` : un coach qui a changé de pseudo garde sa couleur. La pastille est `aria-hidden`, le nom doit rester écrit à côté.

```python
f"{coach_badge(row.coach)}{escape(row.coach)}"
```

`rank_list(table: pd.DataFrame, team_id: int | None, coach_by_team: dict[int, str]) -> str` : le classement en liste. La ligne de `team_id` est mise en avant ; la forme est masquée sous 640 px.

```python
st.html(rank_list(a.standings, team_id, coaches))
```

`prob_bar(p_dom, p_nul, p_ext, labels=DEFAULT_PROB_LABELS) -> str` : la barre de probabilité à trois segments. Les libellés par défaut sont `("Dom.", "Nul", "Ext.")`. Chaque segment garde au moins 4 % de largeur pour rester lisible. La barre a un `aria-label` complet.

```python
st.html(prob_bar(s["p_v"], s["p_n"], s["p_d"], labels=("Toi", "Nul", "Adversaire")))
```

`next_match(when, value, value_label, detail_html, bar_html="") -> str` : la carte « Ton match ».

```python
next_match(f"Ton match, {source}", fmt_pct(p_win), "de chances de gagner", detail, bar)
```

`fixture_grid(cards: list[str], cols: int) -> None` : une grille de cartes de matchs. `grid(cells: list[str], template: str) -> str` est la grille générique : `template` devient la variable CSS `--tpl`.

```python
fixture_grid(cards, len(cards))
```

`rank_tone(rank: int, n: int) -> str` renvoie `tone-good` pour les trois premiers, `tone-bad` pour les trois derniers, `tone-mid` sinon. `result_color(r: str) -> str` renvoie la couleur d'un résultat `V`, `N` ou `D`, et `TEXT_2` sinon.

Formats de texte : `fmt_pct(x, digits=0)` (« 42 % »), `fmt_signed(x, digits=1)` (signe avec le vrai moins « − »), `fmt_m(x)` (« 1 250 M€ »). Deux petits utilitaires complètent la liste, `names_list` (noms séparés par des virgules) et `team_rows_first` (remonte les lignes d'une équipe en tête d'un tableau).

### Tableaux

`short_table(df, columns, *, more="Toutes les colonnes", full=None, column_config=None, alt=None, **kwargs) -> None` : le tableau standard. Il affiche `columns` (cinq au plus, `ValueError` au-delà), puis, si `full` (ou toutes les colonnes) en contient davantage, un dépliant avec la version complète, dont la première colonne est épinglée. `hide_index=True` et `placeholder="—"` sont posés par défaut. Donne toujours `alt` : c'est le texte pour lecteur d'écran. Sur téléphone, voir § 5.

```python
short_table(
    as_pct(summary, ["proba_issue_reelle", "favoris_gagnants"]),
    visible,
    full=[*visible, "log_loss", "brier"],
    more="Toutes les mesures d'erreur",
    column_config={
        "modele": "Modèle",
        "rps": st.column_config.NumberColumn("Erreur de prévision ↓", format="%.3f", help="Plus bas = mieux"),
        "proba_issue_reelle": pct_column("Chances données au vrai résultat", bar=True),
        "favoris_gagnants": pct_column("Favoris vainqueurs"),
    },
    height=table_height(len(summary)),
)
```

`as_pct(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame` : renvoie une copie dont les colonnes listées sont multipliées par 100. Les colonnes absentes sont ignorées. À appeler avant d'utiliser `pct_column`, qui affiche la valeur telle quelle.

`pct_column(label: str, *, bar: bool = False, signed: bool = False, **kwargs)` : une colonne en pourcentage entier. `bar=True` ajoute une barre de progression de 0 à 100, `signed=True` affiche un signe (« +3 % »). Les deux ensemble lèvent `ValueError`. Les autres arguments (`help`, `width`) passent à Streamlit.

```python
"delta_p_titre": pct_column("Titre +/-", signed=True, help="Variation de la chance de titre"),
```

`table_height(n_rows: int) -> int` : la hauteur en pixels pour afficher `n_rows` lignes sans défilement interne (`ROW_PX = 35` par ligne, plus l'en-tête).

```python
st.dataframe(table, hide_index=True, height=table_height(len(table)))
```

### Graphiques

Dans `app/charts.py`. `CONFIG` masque la barre d'outils Plotly et désactive le zoom à la molette.

`show(fig: go.Figure, height: int | None = None) -> None` : l'unique façon d'afficher une figure. Elle l'enveloppe dans une carte, déplace le titre en HTML pour qu'il passe à la ligne, ajuste la marge haute selon la présence d'une légende et, sur téléphone, applique `_compact`.

```python
charts.show(charts.bump_chart(a.standings_by_gw, team_id, len(a.league.teams)), height=440)
```

`ranked_bars(df, value, label, team_id, title, fmt=".1f", hover=None, ascending=True, x_title="") -> go.Figure` : des barres horizontales triées, l'équipe `team_id` en `SERIES[0]` et les autres en `CONTEXT`. C'est le modèle de la règle « mon équipe en bleu, les autres en gris ».

```python
charts.show(
    charts.ranked_bars(
        co,
        "regret_moy",
        "team_name",
        team_id,
        "Points de note laissés sur le banc, par match",
        fmt=".1f",
        ascending=False,
        x_title="Somme des notes (11 optimal − 11 aligné)",
    ),
    height=440,
)
```

Il existe aussi un graphique par sujet (`bump_chart`, `diverging_bars`, `luck_scatter`, `line_heatmap`, `stacked_goals`, `dumbbell_ranks`, `rank_ranges`, `corr_bars`, `sim_distribution`, `stacked_components`, `team_boxes`, `price_note_facets`, `budget_shares`, `paired_bars`, `component_heatmap`, `gw_points`, `rank_heatmap`, `title_history`, `final_points_box`, `snapshot_lines`, `rps_evolution`, `calibration_chart`). Ils renvoient une figure ; on la passe à `show`. Ils ne sont pas détaillés ici, leurs signatures sont dans le fichier.

Helpers d'axes internes, à réutiliser dans tout nouveau graphique : `_thin` garde au plus `MAX_TICKS = 10` graduations à pas régulier et conserve toujours la dernière ; `_gw_axis` fabrique des graduations de journées courtes (« J12 ») avec un titre d'axe qui porte le préfixe commun ; `_rank_dtick` espace les graduations d'un axe de rangs au-delà de 10 équipes ; `_clip` tronque à `LABEL_MAX_CHARS = 15` caractères ; `_end_labels(fig, x, items, y_range, reverse=False, size=LABEL_SIZE)` pose des étiquettes de fin de ligne et décale à la verticale celles qui se chevauchent, puis agrandit la marge droite ; `_labelled` limite ces étiquettes à mon équipe plus les trois premières.

### Navigation

Dans `app/navigation.py`.

`volet_selector(options: dict[str, str]) -> str` : un contrôle segmenté qui choisit le volet d'une page. `options` associe une clé à un libellé ; la clé choisie est renvoyée et écrite dans l'adresse (`?volet=...`), sauf pour le premier volet. Avec un seul volet, rien n'est affiché. Sans option, `ValueError`.

```python
volet = volet_selector({"profil": "Profil", "effectif": "Effectif", "bonus": "Bonus"})
```

`page_link(key: str, label: str, icon: str | None = None, volet: str | None = None) -> None` : un lien vers une autre page, éventuellement vers un volet précis. `key` vient du registre rempli par `register(pages)`. Une clé inconnue ne fait rien.

```python
page_link("pourquoi", "Comprendre ce classement : mérite ou chance ?", icon=":material/casino:", volet="chance")
```

### Ce que le coach utilise

`coach_app.py` appelle `theme.inject_css()`, et `app/views/coach.py` importe depuis `app.components` exactement `callout`, `hero`, `kpi_row`, `prob_bar`, `section` et `table_height`. Il n'importe aucune constante de `app.theme`. Ces six composants et le CSS qui les habille (`.hero`, `.stats`, `.stat`, `.pbar`, `.plegend`, `.callout`, les styles de `h3`) ne doivent pas disparaître ni changer de signature sans revoir `coach.py`. Il en va de même pour le paramètre `labels` de `prob_bar` (« Toi », « Nul », « Adversaire ») et les clés `label`, `value`, `sub`, `small`, `me` de `kpi_row`.

## 5. Mobile

`is_mobile()` (dans `app/charts.py`, importé par `components.py`) lit l'en-tête `User-Agent` et renvoie vrai s'il contient `Mobi`. C'est la seule détection côté Python. Le reste passe par les media queries de `theme.py` : sous `BP_TABLET` (1100 px), `.stats`, `.fixtures`, `.ladder` et `.top5` passent à deux colonnes ; sous `BP_PHONE` (640 px), les marges se resserrent, les titres rétrécissent et la forme du classement (`.hide-s`) disparaît.

Pour un tableau, `short_table` appelle `_phone_config` quand `is_mobile()` est vrai : la première colonne est épinglée (`pinned`) et les autres prennent la largeur `small`, sauf si le `column_config` donne déjà une largeur. Le dépliant « Toutes les colonnes » épingle toujours la première colonne.

Pour un graphique, `show` appelle `_compact` : étiquettes de fin de ligne à 10 px et tronquées, titres d'axe trop longs coupés en deux lignes, légende et infobulles à 11 et 12 px, `dragmode=False` pour ne pas capturer le défilement. Certains graphiques changent aussi de forme : `team_boxes` passe de 4 à 2 colonnes et de 430 à 640 px de haut, `component_heatmap` tourne ses étiquettes à la verticale.

Limite connue : sur un écran de 390 px, avec des noms d'équipe longs, la cinquième colonne d'un tableau demande un court défilement horizontal. Le nom épinglé reste visible pendant ce défilement. Je n'ai pas pu mesurer ce comportement depuis le code ; il vient de tes captures, et aucun test ne le couvre.

## 6. Ajouter un composant ou une couleur

Une nouvelle couleur s'ajoute dans `app/theme.py`, sous un nom, jamais dans une vue, un composant ou `charts.py`. Si elle sert au thème Streamlit lui-même, reporte-la aussi dans `.streamlit/config.toml`. Vérifie son contraste contre `SURFACE` avant de l'adopter (au moins 4,5 pour du texte, 3 pour une barre ou un point) et ajoute-la au tableau du § 2. `tests/test_design_system.py` échoue si une couleur hexadécimale apparaît dans `app/views/*.py`, `components.py` ou `charts.py`.

Un nouveau composant s'ajoute dans `app/components.py`. Le HTML y est construit avec `escape` sur chaque donnée, les classes CSS sont définies dans `CSS` de `theme.py`, et la vue n'écrit jamais de `style=`, de `<style` ni de `unsafe_allow_html` (ce que `test_view_has_no_inline_styling` vérifie). Une variable dynamique, comme la largeur d'une grille, passe par une propriété CSS personnalisée posée dans `components.py` (`--n`, `--cols`, `--tpl`). Ajoute un test dans `tests/test_components.py`, sur le modèle de `test_alert_tone_and_escape` : structure du HTML, échappement, erreur sur une valeur interdite. Un nouveau graphique ajoute un test dans `tests/test_charts.py`, en particulier sur le nombre de graduations et, si besoin, avec `is_mobile` simulé (voir `test_component_heatmap_labels_do_not_tilt`).

Un nouveau terme technique ajoute une entrée à `GLOSSARY` dans `mpg/glossary.py` et s'affiche avec `how(...)`. Une nouvelle option de navigation passe par `volet_selector` ; `tests/test_navigation.py` couvre son comportement.
