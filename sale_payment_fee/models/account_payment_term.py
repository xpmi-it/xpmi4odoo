# Copyright 2024 OCA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class AccountPaymentTerm(models.Model):
    _inherit = "account.payment.term"

    collection_fee_product_id = fields.Many2one(
        comodel_name="product.product",
        string="Collection Fee Product",
        domain=[("type", "=", "service")],
        help=(
            "If set, this service product will be automatically added as a line "
            "in the sale order when this payment term is selected. "
            "The quantity will match the number of installments."
        ),
    )
