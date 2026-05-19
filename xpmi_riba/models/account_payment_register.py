from odoo import models, fields, api

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_batch(self, batch_result):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_batch(batch_result)
        method_id = payment_vals['payment_method_line_id']
        payment_type = payment_vals['payment_type']
        payment_method_code = self.env['account.payment.method.line'].browse(method_id).code
        if payment_method_code != 'riba' or payment_type != 'inbound':
            return payment_vals

        return self._payment_vals_for_riba(batch_result, payment_vals)

    def _create_payment_vals_from_wizard(self, batch_result):
        payment_vals = super(AccountPaymentRegister, self)._create_payment_vals_from_wizard(batch_result)
        method_id = payment_vals['payment_method_line_id']
        payment_type = payment_vals['payment_type']

        payment_method_code = self.env['account.payment.method.line'].browse(method_id).code
        if payment_method_code != 'riba' or  payment_type != 'inbound':
            return payment_vals
        return self._payment_vals_for_riba(batch_result, payment_vals)

    def _payment_vals_for_riba(self, batch_result, payment_vals):
        lines = batch_result['lines']
        move = lines.move_id

        pay_lines_ids = self.env['account.move'].browse(move.id).matched_payment_ids
        move_domain = [
            ('move_id', '=', move.id),
            ('display_type', '=', 'payment_term')
        ]
        move_lines = self.env['account.move.line'].search(move_domain)

        num_pay_line = len(pay_lines_ids)
        maturity_date = move_lines[num_pay_line].date_maturity
        amount = move_lines[num_pay_line].amount_currency

        if maturity_date:
            payment_vals['date'] = maturity_date
        if amount:
            payment_vals['amount'] = amount

        return payment_vals