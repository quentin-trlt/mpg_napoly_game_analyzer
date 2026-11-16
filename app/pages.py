from app.components import hero
from app.navigation import volet_selector
from app.views import (
    analyse_mercato,
    chance,
    coaching,
    equipe,
    favoris,
    joueurs,
    journee,
    ligue,
    matchs,
    mercato,
    predictions,
    suivi,
)
from app.views.palmares import render as render_palmares
from mpg.analysis import Analysis


def _eyebrow(a: Analysis, name: str) -> str:
    return f"{name} · {a.meta['saison']}"


def ma_journee(a: Analysis, team_id: int) -> None:
    journee.render(a, team_id)


def mon_equipe(a: Analysis, team_id: int) -> None:
    hero(_eyebrow(a, "Mon équipe"), "Où en est mon équipe, que me reste-t-il ?")
    equipe.header(a, team_id)
    volet = volet_selector({"profil": "Profil", "effectif": "Effectif", "bonus": "Bonus"})
    if volet == "profil":
        equipe.profil(a, team_id)
    elif volet == "effectif":
        equipe.effectif(a, team_id)
    else:
        equipe.bonus(a, team_id)


def page_ligue(a: Analysis, team_id: int) -> None:
    hero(_eyebrow(a, "Ligue"), "Qui est où, qui a fait quoi ?")
    volet = volet_selector({"classement": "Classement", "matchs": "Matchs et calendrier"})
    if volet == "classement":
        ligue.render(a, team_id)
    else:
        matchs.render(a, team_id)


def palmares(a: Analysis, team_id: int) -> None:
    render_palmares(a, team_id)


def pronostics(a: Analysis, team_id: int) -> None:
    hero(_eyebrow(a, "Pronostics"), "Qui va gagner, et avait-on vu juste ?")
    volet = volet_selector({"predictions": "Prédictions", "suivi": "Suivi des pronostics"})
    if volet == "predictions":
        predictions.render(a, team_id)
    else:
        suivi.render(a, team_id)


def pourquoi(a: Analysis, team_id: int) -> None:
    hero(_eyebrow(a, "Pourquoi ce classement ?"), "Mérite, chance ou coaching ?")
    volet = volet_selector({"favoris": "Favoris vs réalité", "chance": "Chance", "coaching": "Coaching"})
    if volet == "favoris":
        favoris.render(a, team_id)
    elif volet == "chance":
        chance.render(a, team_id)
    else:
        coaching.render(a, team_id)


def joueurs_mercato(a: Analysis, team_id: int) -> None:
    hero(_eyebrow(a, "Joueurs et mercato"), "Qui sont les bons joueurs, qui a bien acheté ?")
    volet = volet_selector({"joueurs": "Joueurs", "mercato": "Mercato", "analyse-mercato": "Classement des mercatos"})
    if volet == "joueurs":
        joueurs.render(a, team_id)
    elif volet == "mercato":
        mercato.render(a, team_id)
    else:
        analyse_mercato.render(a, team_id)
