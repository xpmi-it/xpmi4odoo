from . import controllers
from . import models


def post_init_hook(env):
    """Popola le previsioni all'installazione.

    Senza questa prima generazione la dashboard resta vuota finché non gira il
    cron notturno.
    """
    env["xpmi.cash.forecast.line"]._refresh_forecast()
