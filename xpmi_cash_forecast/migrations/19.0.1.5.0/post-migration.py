from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Rigenera le previsioni con la fatturazione prevista.

    Senza questo passaggio le fatture programmate e le ricorrenze future
    comparirebbero solo al prossimo aggiornamento.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["xpmi.cash.forecast.line"]._refresh_forecast()
