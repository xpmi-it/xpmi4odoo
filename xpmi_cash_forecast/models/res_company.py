from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    cash_forecast_include_draft_invoices = fields.Boolean(
        string="Fatture in bozza nelle previsioni di cassa",
        help="Considera nelle previsioni di cassa anche le fatture clienti e "
             "fornitori in bozza. Le bozze programmate per la registrazione "
             "automatica, comprese le fatture ricorrenti, sono considerate "
             "sempre.",
    )

    def write(self, vals):
        """Rigenera le previsioni quando cambia la scelta sulle bozze.

        La rigenerazione sta qui e non nelle impostazioni perché il campo
        collegato delle impostazioni scrive sull'azienda già al salvataggio del
        wizard: così la dashboard mostra subito il nuovo perimetro, da
        qualunque parte arrivi la modifica.
        """
        changed = "cash_forecast_include_draft_invoices" in vals and any(
            company.cash_forecast_include_draft_invoices
            != bool(vals["cash_forecast_include_draft_invoices"])
            for company in self
        )
        res = super().write(vals)
        if changed:
            self.env["xpmi.cash.forecast.line"]._refresh_forecast()
        return res
