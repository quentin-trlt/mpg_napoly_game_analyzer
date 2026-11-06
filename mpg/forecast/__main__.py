import logging

from mpg.analysis import run
from mpg.forecast.evaluation import freeze_next
from mpg.forecast.season import build_context, ensemble_draws, fixtures_after, simulate_season

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    a = run()
    fx = fixtures_after(a, a.league.last_gw)
    draws = ensemble_draws(build_context(a), fx)
    written = freeze_next(a, simulate_season(a, draws), draws)
    if written:
        for path in written:
            log.info("figé : %s", path)
    else:
        log.info("rien à figer : fichiers déjà existants ou aucune journée à venir")


if __name__ == "__main__":
    main()
