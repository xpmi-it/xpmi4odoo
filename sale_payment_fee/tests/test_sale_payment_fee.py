# Copyright 2024 OCA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import tagged
from odoo.tests.common import Form, TransactionCase


@tagged("post_install", "-at_install")
class TestSalePaymentFee(TransactionCase):
    """Tests for sale_payment_fee: fee line creation, taxes, onchange and invoicing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ── Taxes ─────────────────────────────────────────────────────────────
        cls.tax_22 = cls.env["account.tax"].create(
            {
                "name": "IVA 22%",
                "amount": 22.0,
                "type_tax_use": "sale",
            }
        )
        cls.tax_10 = cls.env["account.tax"].create(
            {
                "name": "IVA 10%",
                "amount": 10.0,
                "type_tax_use": "sale",
            }
        )

        # ── Products ──────────────────────────────────────────────────────────
        cls.fee_product = cls.env["product.product"].create(
            {
                "name": "Spese di Incasso",
                "type": "service",
                "list_price": 5.0,
                "invoice_policy": "order",
                "taxes_id": [(6, 0, [cls.tax_22.id])],
            }
        )
        cls.fee_product_2 = cls.env["product.product"].create(
            {
                "name": "Spese di Incasso B",
                "type": "service",
                "list_price": 8.0,
                "invoice_policy": "order",
            }
        )
        cls.sale_product = cls.env["product.product"].create(
            {
                "name": "Prodotto di Vendita",
                "type": "consu",
                "list_price": 100.0,
                "invoice_policy": "order",
            }
        )

        # ── Payment terms ─────────────────────────────────────────────────────
        cls.term_single = cls.env["account.payment.term"].create(
            {
                "name": "Pagamento 30 gg con spese",
                "collection_fee_product_id": cls.fee_product.id,
                "line_ids": [
                    (0, 0, {"value": "percent", "value_amount": 100, "nb_days": 30})
                ],
            }
        )
        cls.term_three = cls.env["account.payment.term"].create(
            {
                "name": "3 Rate con spese",
                "collection_fee_product_id": cls.fee_product.id,
                "line_ids": [
                    (0, 0, {"value": "percent", "value_amount": 33, "nb_days": 30}),
                    (0, 0, {"value": "percent", "value_amount": 33, "nb_days": 60}),
                    (0, 0, {"value": "percent", "value_amount": 34, "nb_days": 90}),
                ],
            }
        )
        cls.term_no_fee = cls.env["account.payment.term"].create(
            {
                "name": "Immediato senza spese",
                "line_ids": [
                    (0, 0, {"value": "percent", "value_amount": 100, "nb_days": 0})
                ],
            }
        )

        # ── Fiscal position (maps 22% → 10%) ──────────────────────────────────
        cls.fiscal_position = cls.env["account.fiscal.position"].create(
            {
                "name": "Test FP",
                "tax_ids": [
                    (
                        0,
                        0,
                        {
                            "tax_src_id": cls.tax_22.id,
                            "tax_dest_id": cls.tax_10.id,
                        },
                    )
                ],
            }
        )

        # ── Partner ───────────────────────────────────────────────────────────
        cls.partner = cls.env["res.partner"].create({"name": "Cliente Test"})

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_order(self, payment_term=None, fiscal_position=None):
        """Create a minimal sale order via ORM (onchanges are NOT triggered)."""
        vals = {
            "partner_id": self.partner.id,
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": self.sale_product.id,
                        "product_uom_qty": 1,
                        "price_unit": 100.0,
                    },
                )
            ],
        }
        if payment_term:
            vals["payment_term_id"] = payment_term.id
        if fiscal_position:
            vals["fiscal_position_id"] = fiscal_position.id
        return self.env["sale.order"].create(vals)

    def _fee_lines(self, order):
        return order.order_line.filtered(lambda l: l.is_collection_fee)

    # ── Tests: fee line creation ──────────────────────────────────────────────

    def test_01_fee_line_created_on_order_with_term(self):
        """Fee line is created when the order has a payment term with a fee product."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        fee_lines = self._fee_lines(order)
        self.assertEqual(len(fee_lines), 1, "Should have exactly 1 fee line")
        self.assertEqual(fee_lines.product_id, self.fee_product)
        self.assertEqual(fee_lines.product_uom_qty, 1.0)

    def test_02_fee_qty_equals_installments(self):
        """Fee quantity must equal the number of installments in the payment term."""
        order = self._make_order(self.term_three)
        order._sync_collection_fee_line()
        fee_lines = self._fee_lines(order)
        self.assertEqual(len(fee_lines), 1)
        self.assertEqual(
            fee_lines.product_uom_qty,
            3.0,
            "Qty should be 3 (number of installments)",
        )

    def test_03_no_fee_line_without_product_on_term(self):
        """No fee line is created when the payment term has no fee product."""
        order = self._make_order(self.term_no_fee)
        order._sync_collection_fee_line()
        self.assertEqual(len(self._fee_lines(order)), 0, "No fee line expected")

    def test_04_no_fee_line_without_payment_term(self):
        """No fee line when no payment term is set on the order."""
        order = self._make_order()
        order._sync_collection_fee_line()
        self.assertEqual(len(self._fee_lines(order)), 0)

    # ── Tests: payment term change ────────────────────────────────────────────

    def test_05_fee_removed_when_term_changed_to_no_fee(self):
        """Switching to a term without fee removes the existing fee line."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        self.assertEqual(len(self._fee_lines(order)), 1)

        order.payment_term_id = self.term_no_fee
        order._sync_collection_fee_line()
        self.assertEqual(
            len(self._fee_lines(order)),
            0,
            "Fee line should be removed after switching to a no-fee term",
        )

    def test_06_fee_qty_updated_when_term_changes_installment_count(self):
        """Changing payment term updates the fee line qty to the new installment count."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        self.assertEqual(self._fee_lines(order).product_uom_qty, 1.0)

        order.payment_term_id = self.term_three
        order._sync_collection_fee_line()
        self.assertEqual(
            self._fee_lines(order).product_uom_qty,
            3.0,
            "Qty should update to 3",
        )

    def test_07_fee_product_updated_when_term_changes(self):
        """Changing payment term updates the fee product on the existing fee line."""
        term_b = self.env["account.payment.term"].create(
            {
                "name": "Term B",
                "collection_fee_product_id": self.fee_product_2.id,
                "line_ids": [
                    (0, 0, {"value": "percent", "value_amount": 100, "nb_days": 15})
                ],
            }
        )
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        self.assertEqual(self._fee_lines(order).product_id, self.fee_product)

        order.payment_term_id = term_b
        order._sync_collection_fee_line()
        self.assertEqual(
            self._fee_lines(order).product_id,
            self.fee_product_2,
            "Product should be updated to fee_product_2",
        )

    # ── Tests: uniqueness and ordering ────────────────────────────────────────

    def test_08_only_one_fee_line_present(self):
        """Calling _sync_collection_fee_line multiple times must not create duplicates."""
        order = self._make_order(self.term_three)
        order._sync_collection_fee_line()
        order._sync_collection_fee_line()
        order._sync_collection_fee_line()
        self.assertEqual(
            len(self._fee_lines(order)),
            1,
            "Must never have more than 1 fee line",
        )

    def test_09_fee_line_at_end_of_order(self):
        """Fee line sequence must be greater than or equal to all normal line sequences."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        normal_seq = order.order_line.filtered(
            lambda l: not l.is_collection_fee
        ).mapped("sequence")
        fee_seq = self._fee_lines(order).mapped("sequence")
        self.assertTrue(
            all(fs >= max(normal_seq) for fs in fee_seq),
            "Fee line should have the highest sequence",
        )

    # ── Tests: taxes ─────────────────────────────────────────────────────────

    def test_10_fee_line_has_taxes_from_product(self):
        """Fee line must carry the taxes defined on the fee product."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        fee_line = self._fee_lines(order)
        self.assertTrue(fee_line.tax_id, "Fee line should have at least one tax")
        self.assertIn(
            self.tax_22,
            fee_line.tax_id,
            "IVA 22% from the fee product should be on the fee line",
        )

    def test_11_fee_line_no_taxes_when_product_has_none(self):
        """Fee line must have no taxes when the fee product has none configured."""
        term = self.env["account.payment.term"].create(
            {
                "name": "Term no-tax product",
                "collection_fee_product_id": self.fee_product_2.id,
                "line_ids": [
                    (0, 0, {"value": "percent", "value_amount": 100, "nb_days": 30})
                ],
            }
        )
        order = self._make_order(term)
        order._sync_collection_fee_line()
        fee_line = self._fee_lines(order)
        self.assertFalse(
            fee_line.tax_id,
            "Fee line should have no taxes when the product has none",
        )

    def test_12_fee_line_taxes_mapped_by_fiscal_position(self):
        """Fiscal position tax mapping must be applied to the fee line taxes."""
        order = self._make_order(
            self.term_single, fiscal_position=self.fiscal_position
        )
        order._sync_collection_fee_line()
        fee_line = self._fee_lines(order)
        self.assertNotIn(
            self.tax_22,
            fee_line.tax_id,
            "Source tax (22%) should be replaced by fiscal position mapping",
        )
        self.assertIn(
            self.tax_10,
            fee_line.tax_id,
            "Mapped tax (10%) should be applied via fiscal position",
        )

    # ── Tests: onchange (UI simulation) ──────────────────────────────────────

    def test_13_onchange_adds_fee_line_on_new_virtual_order(self):
        """Onchange on a new (not yet saved) virtual order must add the fee line."""
        order = self.env["sale.order"].new(
            {
                "partner_id": self.partner.id,
                "payment_term_id": self.term_single.id,
            }
        )
        order._onchange_payment_term_id_fee()
        fee_lines = order.order_line.filtered(lambda l: l.is_collection_fee)
        self.assertEqual(
            len(fee_lines),
            1,
            "Fee line must be present in the virtual order after onchange",
        )

    def test_14_onchange_adds_fee_line_on_existing_order(self):
        """Onchange on an existing saved order must persist the fee line after save."""
        order = self._make_order()
        order_form = Form(order)
        order_form.payment_term_id = self.term_single
        order = order_form.save()
        self.assertEqual(
            len(self._fee_lines(order)),
            1,
            "Fee line must be saved after onchange is triggered on an existing order",
        )

    def test_15_onchange_removes_fee_line_without_error(self):
        """Switching from a fee term to a no-fee term via Form must not raise errors."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        self.assertEqual(len(self._fee_lines(order)), 1)

        order_form = Form(order)
        order_form.payment_term_id = self.term_no_fee
        order = order_form.save()
        self.assertEqual(
            len(self._fee_lines(order)),
            0,
            "Fee line must be removed without errors when switching to a no-fee term",
        )

    def test_16_onchange_adds_taxes_on_new_virtual_order(self):
        """Fee line taxes must be set correctly even on a new (unsaved) order."""
        order = self.env["sale.order"].new(
            {
                "partner_id": self.partner.id,
                "payment_term_id": self.term_single.id,
            }
        )
        order._onchange_payment_term_id_fee()
        fee_line = order.order_line.filtered(lambda l: l.is_collection_fee)
        self.assertTrue(fee_line, "Fee line must exist on the new virtual order")
        self.assertIn(
            self.tax_22,
            fee_line.tax_id,
            "IVA 22% must be on the fee line even for unsaved orders",
        )

    # ── Tests: invoicing ──────────────────────────────────────────────────────

    def test_17_invoice_fee_qty_is_one(self):
        """When invoicing, the collection fee line must appear with qty = 1."""
        order = self._make_order(self.term_three)
        order._sync_collection_fee_line()
        self.assertEqual(self._fee_lines(order).product_uom_qty, 3.0)

        order.action_confirm()
        invoices = order._create_invoices()
        self.assertTrue(invoices, "Invoice should be created")

        fee_inv_lines = invoices.invoice_line_ids.filtered(
            lambda l: l.sale_line_ids
            and any(sl.is_collection_fee for sl in l.sale_line_ids)
        )
        self.assertEqual(len(fee_inv_lines), 1)
        self.assertEqual(
            fee_inv_lines.quantity,
            1.0,
            "Invoice fee line must have qty = 1 regardless of installment count",
        )

    def test_18_invoice_without_fee_term_has_no_fee_line(self):
        """An order with a no-fee payment term must produce an invoice with no fee line."""
        order = self._make_order(self.term_no_fee)
        order._sync_collection_fee_line()
        order.action_confirm()
        invoices = order._create_invoices()
        fee_inv_lines = invoices.invoice_line_ids.filtered(
            lambda l: l.sale_line_ids
            and any(sl.is_collection_fee for sl in l.sale_line_ids)
        )
        self.assertEqual(len(fee_inv_lines), 0)

    # ── Tests: installment count helper ──────────────────────────────────────

    def test_19_installment_count_single(self):
        """_get_installment_count returns 1 for a single-line payment term."""
        order = self._make_order(self.term_single)
        self.assertEqual(order._get_installment_count(), 1)

    def test_20_installment_count_three(self):
        """_get_installment_count returns 3 for a three-line payment term."""
        order = self._make_order(self.term_three)
        self.assertEqual(order._get_installment_count(), 3)

    def test_21_installment_count_no_term(self):
        """_get_installment_count returns 1 when no payment term is set."""
        order = self._make_order()
        self.assertEqual(order._get_installment_count(), 1)

    # ── Tests: is_collection_fee flag ────────────────────────────────────────

    def test_22_is_collection_fee_flag_true(self):
        """Fee line must have is_collection_fee = True."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        self.assertTrue(self._fee_lines(order).is_collection_fee)

    def test_23_regular_line_is_not_fee(self):
        """All regular order lines must have is_collection_fee = False."""
        order = self._make_order(self.term_single)
        order._sync_collection_fee_line()
        regular = order.order_line.filtered(lambda l: not l.is_collection_fee)
        self.assertTrue(
            all(not l.is_collection_fee for l in regular),
            "Regular lines must never be flagged as collection fee",
        )
