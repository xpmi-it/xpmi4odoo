from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    cash_forecast_include_draft_invoices = fields.Boolean(
        related="company_id.cash_forecast_include_draft_invoices",
        readonly=False,
    )
