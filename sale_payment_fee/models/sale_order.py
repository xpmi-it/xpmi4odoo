# Copyright 2024 OCA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _get_collection_fee_product(self):
        """Return the collection fee product from the current payment term, or False."""
        self.ensure_one()
        if (
            self.payment_term_id
            and self.payment_term_id.collection_fee_product_id
        ):
            return self.payment_term_id.collection_fee_product_id
        return False

    def _get_installment_count(self):
        """
        Return the number of installments (lines) in the payment term.
        A payment term with a single line counts as 1.
        """
        self.ensure_one()
        if not self.payment_term_id:
            return 1
        return max(len(self.payment_term_id.line_ids), 1)

    def _find_collection_fee_line(self):
        """Return the existing collection fee order line, if any."""
        self.ensure_one()
        return self.order_line.filtered(lambda l: l.is_collection_fee)

    def _sync_collection_fee_line(self):
        """
        Create, update or delete the collection fee line depending on the
        payment term configured on the order.

        Works in both contexts:
        - onchange (order not yet saved, self.id is False / _origin.id)
        - write/saved record (self.id is a real DB id)
        """
        self.ensure_one()
        fee_product = self._get_collection_fee_product()
        existing_lines = self._find_collection_fee_line()

        if not fee_product:
            self.order_line = self.order_line - existing_lines
            return

        installments = self._get_installment_count()

        if existing_lines:
            if len(existing_lines) > 1:
                self.order_line = self.order_line - existing_lines[1:]
            line = existing_lines[0]
            line.update({"product_id": fee_product.id})
            line._onchange_product_id()
            line.update({
                "product_uom_qty": installments,
                "is_collection_fee": True,
            })
        else:
            self._create_collection_fee_line(fee_product, installments)

    def _create_collection_fee_line(self, product, qty):
        """
        Create the collection fee order line as a virtual record so that the
        onchange response includes the new line and the form shows it immediately.
        Odoo persists the virtual line when the user saves the form.
        """
        self.ensure_one()
        # Use the real DB id (via _origin) so the line knows its parent order;
        # for new unsaved orders _origin.id is False, which is also correct.
        order_id = (self._origin and self._origin.id) or False

        SaleOrderLine = self.env["sale.order.line"]

        new_line = SaleOrderLine.new({
            "order_id": order_id,
            "product_id": product.id,
            "product_uom_qty": qty,
            "is_collection_fee": True,
            "sequence": 9999,
        })
        new_line._onchange_product_id()

        # _onchange_product_id cannot resolve taxes when order_id is unset (new
        # order not yet saved) or when tax_id is a computed field. Apply them
        # explicitly from the virtual order's current company and fiscal position.
        company = self.company_id or self.env.company
        fpos = self.fiscal_position_id
        taxes = product.taxes_id.filtered(lambda t: t.company_id == company)
        new_line.tax_id = fpos.map_tax(taxes) if fpos else taxes

        new_line.product_uom_qty = qty
        new_line.is_collection_fee = True
        new_line.sequence = 9999

        # Always append to the virtual order_line so the onchange notifies the
        # form client regardless of whether the order is new or already saved.
        self.order_line |= new_line

    # -------------------------------------------------------------------------
    # Onchange
    # -------------------------------------------------------------------------

    @api.onchange("payment_term_id")
    def _onchange_payment_term_id_fee(self):
        """Sync fee line whenever the payment term changes in the UI."""
        for order in self:
            order._sync_collection_fee_line()

    # -------------------------------------------------------------------------
    # Override _create_invoices to fix qty = 1 on invoice
    # -------------------------------------------------------------------------

    def _create_invoices(self, grouped=False, final=False, date=None):
        """
        After invoice creation, set qty = 1 on any collection-fee invoice line.
        The sale order carries qty = number of installments so the amount is
        correct, but the invoice must show the product only once.
        """
        moves = super()._create_invoices(grouped=grouped, final=final, date=date)
        for move in moves:
            fee_lines = move.invoice_line_ids.filtered(
                lambda l: l.sale_line_ids
                and any(sl.is_collection_fee for sl in l.sale_line_ids)
            )
            if fee_lines:
                fee_lines.write({"quantity": 1.0})
        return moves


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_collection_fee = fields.Boolean(
        string="Is Collection Fee",
        default=False,
        copy=False,
        help="Technical flag: this line was automatically generated as a collection fee.",
    )
