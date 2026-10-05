from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Rigenera le previsioni con i campi di periodo valorizzati."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["xpmi.cash.forecast.line"]._refresh_forecast()
