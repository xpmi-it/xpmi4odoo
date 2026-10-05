from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

DOCUMENT_TYPES = [
    ("bank_balance", "Saldo banca e cassa"),
    ("customer_invoice", "Fattura cliente"),
    ("vendor_bill", "Fattura fornitore"),
    ("customer_invoice_planned", "Fatturazione prevista clienti"),
    ("vendor_bill_planned", "Fatturazione prevista fornitori"),
    ("sale_order", "Ordine cliente"),
    ("purchase_order", "Ordine fornitore"),
]

# Tutto ciò che è scaduto da più di questi giorni finisce in un unico periodo,
# altrimenti il riepilogo si riempie di colonne passate.
OVERDUE_DAYS = 30
OVERDUE_LABEL = "Scaduto oltre %s gg" % OVERDUE_DAYS

# Tipi di documento contabile considerati "fatture aperte".
INVOICE_MOVE_TYPES = ("out_invoice", "out_refund", "in_invoice", "in_refund")

# Da dove arriva una riga di fattura: registrata, in bozza, programmata
# (bozza con registrazione automatica) o ricorrenza futura non ancora creata.
INVOICE_SOURCES = [
    ("posted", "Registrata"),
    ("draft", "Bozza"),
    ("scheduled", "Programmata"),
    ("recurring", "Ricorrenza futura"),
]

# Periodicità di `account.move.auto_post` che generano ricorrenze.
PERIODIC_AUTO_POST = ("monthly", "quarterly", "yearly")

# Le ricorrenze future si proiettano fino a questi mesi da oggi, anche quando
# `auto_post_until` è più lontano o manca del tutto: senza un limite una
# ricorrenza senza fine produrrebbe righe all'infinito, e lo stesso orizzonte
# per tutte evita che il saldo progressivo cambi pendenza a seconda della
# fine indicata sulla fattura.
RECURRING_HORIZON_MONTHS = 12


class CashForecastLine(models.Model):
    _name = "xpmi.cash.forecast.line"
    _description = "Riga di previsione di cassa"
    _order = "forecast_date, id"
    _rec_name = "name"

    name = fields.Char(string="Documento", required=True, index=True)
    forecast_date = fields.Date(
        string="Data prevista",
        required=True,
        index=True,
        help="Data attesa dell'incasso o del pagamento: scadenza per le fatture, "
             "data di consegna prevista più i giorni del termine di pagamento "
             "per gli ordini.",
    )
    document_date = fields.Date(
        string="Data documento",
        help="Data della fattura o data di consegna prevista dell'ordine.",
    )
    period_date = fields.Date(
        string="Periodo",
        required=True,
        index=True,
        help="Data usata per raggruppare grafici e riepiloghi, con la scelta "
             "dell'intervallo (giorno, settimana, mese, trimestre, anno). "
             "Coincide con la data prevista, tranne per le previsioni scadute "
             "da oltre un mese, riportate a oggi perché sono incassi e "
             "pagamenti attesi adesso.",
    )
    period_month = fields.Char(
        string="Periodo (mese)",
        required=True,
        index=True,
        help="Mese previsto dell'incasso o del pagamento. Le previsioni scadute "
             "da oltre un mese sono raccolte in un unico periodo.",
    )
    period_week = fields.Char(
        string="Periodo (settimana)",
        required=True,
        index=True,
        help="Come il periodo mensile, ma per settimana, identificata dal lunedì.",
    )
    is_overdue = fields.Boolean(
        string="Scaduto oltre un mese",
        index=True,
    )
    direction = fields.Selection(
        selection=[("in", "Incasso"), ("out", "Pagamento")],
        string="Segno",
        required=True,
        index=True,
    )
    document_type = fields.Selection(
        selection=DOCUMENT_TYPES,
        string="Tipo documento",
        required=True,
        index=True,
    )
    amount = fields.Monetary(
        string="Importo previsto",
        currency_field="currency_id",
        help="Importo IVA inclusa, in valuta aziendale, positivo per gli incassi "
             "e negativo per i pagamenti.",
    )
    currency_id = fields.Many2one("res.currency", string="Valuta", required=True)
    company_id = fields.Many2one("res.company", string="Azienda", required=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Partner", index=True)
    payment_term_id = fields.Many2one("account.payment.term", string="Termini di pagamento")
    move_id = fields.Many2one(
        "account.move",
        string="Fattura",
        ondelete="cascade",
        help="Per le ricorrenze future è l'ultima fattura della serie, da cui "
             "la ricorrenza è proiettata.",
    )
    invoice_source = fields.Selection(
        selection=INVOICE_SOURCES,
        string="Origine fattura",
        index=True,
        help="Registrata: fattura aperta. Bozza: fattura in bozza, considerata "
             "solo se abilitato nelle impostazioni. Programmata: bozza che Odoo "
             "registrerà da solo alla data contabile. Ricorrenza futura: "
             "fattura ricorrente non ancora creata, dedotta dall'ultima della "
             "serie.",
    )
    sale_order_id = fields.Many2one("sale.order", string="Ordine cliente", ondelete="cascade")
    purchase_order_id = fields.Many2one(
        "purchase.order", string="Ordine fornitore", ondelete="cascade"
    )

    def action_open_document(self):
        """Apre il documento di origine della riga."""
        self.ensure_one()
        document = self.move_id or self.sale_order_id or self.purchase_order_id
        if not document:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": document._name,
            "res_id": document.id,
            "view_mode": "form",
        }

    # ------------------------------------------------------------------
    # Generazione delle previsioni
    # ------------------------------------------------------------------

    @api.model
    def _action_open_forecast(self):
        """Azione di menu: rigenera le previsioni e apre le viste."""
        self._refresh_forecast()
        return self.env["ir.actions.actions"]._for_xml_id(
            "xpmi_cash_forecast.action_cash_forecast_line"
        )

    @api.model
    def _cron_refresh_forecast(self):
        self._refresh_forecast()

    @api.model
    def action_refresh_forecast(self):
        """Rigenera subito le previsioni: quello che fa il cron, su richiesta.

        La chiama il bottone di aggiornamento della dashboard, che non può
        invocare i metodi interni.
        """
        self._refresh_forecast()
        return True

    @api.model
    def _refresh_forecast_if_stale(self, max_age_minutes=5):
        """Rigenera le previsioni se sono più vecchie di qualche minuto.

        Serve all'apertura della dashboard: i dati restano freschi senza
        rigenerare tutto a ogni caricamento della pagina.
        """
        last = self.sudo().search([], order="create_date desc", limit=1)
        if last and fields.Datetime.now() - last.create_date < timedelta(
            minutes=max_age_minutes
        ):
            return False
        self._refresh_forecast()
        return True

    @api.model
    def _refresh_forecast(self):
        """Ricostruisce da zero tutte le righe di previsione."""
        self.sudo().search([]).unlink()
        planned_moves = self._get_planned_invoice_moves()
        vals_list = (
            self._collect_bank_balance_vals()
            + self._collect_invoice_vals()
            + self._collect_planned_invoice_vals(planned_moves)
            + self._collect_recurring_invoice_vals(planned_moves)
            + self._collect_sale_order_vals(planned_moves)
            + self._collect_purchase_order_vals(planned_moves)
        )
        self._apply_period(vals_list)
        return self.sudo().create(vals_list)

    @api.model
    def _apply_period(self, vals_list):
        """Assegna a ogni riga i campi di periodo.

        Le righe scadute da oltre un mese confluiscono tutte nello stesso
        periodo, sia come data (`period_date`, che tiene la scelta
        dell'intervallo nelle viste) sia come etichetta (`period_month` e
        `period_week`, usate dai riepiloghi della dashboard).
        """
        today = fields.Date.context_today(self)
        threshold = today - timedelta(days=OVERDUE_DAYS)
        for vals in vals_list:
            date = vals["forecast_date"]
            overdue = date < threshold
            vals["is_overdue"] = overdue
            # lo scaduto è liquidità attesa adesso: portandolo a oggi il saldo
            # progressivo parte dal saldo di banca e cassa e non da periodi
            # passati
            vals["period_date"] = today if overdue else date
            vals["period_month"] = OVERDUE_LABEL if overdue else date.strftime("%Y-%m")
            # la settimana è identificata dal suo lunedì: i riepiloghi ne
            # ricostruiscono l'etichetta con una semplice formula di data
            monday = date - timedelta(days=date.weekday())
            vals["period_week"] = OVERDUE_LABEL if overdue else str(monday)
        return vals_list

    @api.model
    def _collect_bank_balance_vals(self):
        """Saldo odierno dei conti di banca e cassa, una riga per azienda.

        È il punto di partenza della previsione: sommato ai flussi dà il saldo
        atteso alla fine di ogni periodo. La riga è creata anche a saldo zero,
        così sul grafico della dashboard la serie del saldo resta la prima
        (i gruppi arrivano in ordine alfabetico sul valore tecnico e
        `bank_balance` precede gli altri tipi di documento).
        """
        today = fields.Date.context_today(self)
        groups = self.env["account.move.line"].sudo()._read_group(
            [
                ("parent_state", "=", "posted"),
                ("account_id.account_type", "=", "asset_cash"),
                ("date", "<=", today),
            ],
            ["company_id"],
            ["balance:sum"],
        )
        vals_list = []
        for company, balance in groups:
            vals_list.append({
                "name": "Saldo banca e cassa",
                "forecast_date": today,
                "document_date": today,
                "direction": "in" if balance > 0 else "out",
                "document_type": "bank_balance",
                "amount": balance,
                "currency_id": company.currency_id.id,
                "company_id": company.id,
            })
        return vals_list

    @api.model
    def _collect_invoice_vals(self):
        """Fatture clienti e fornitori aperte, dalle righe di credito/debito.

        Si parte dalle righe contabili e non dalla fattura perché una fattura
        con termini di pagamento a più scadenze genera un incasso per ogni
        scadenza, ognuna con il proprio residuo.
        """
        lines = self.env["account.move.line"].sudo().search([
            ("parent_state", "=", "posted"),
            ("account_id.account_type", "in", ("asset_receivable", "liability_payable")),
            ("reconciled", "=", False),
            ("move_id.move_type", "in", INVOICE_MOVE_TYPES),
        ])
        vals_list = []
        for line in lines:
            amount = line.amount_residual
            if line.company_currency_id.is_zero(amount):
                continue
            move = line.move_id
            vals_list.append({
                "name": move.name,
                "forecast_date": line.date_maturity or move.invoice_date_due or move.date,
                "document_date": move.invoice_date or move.date,
                "direction": "in" if amount > 0 else "out",
                "document_type": (
                    "customer_invoice" if move.is_sale_document() else "vendor_bill"
                ),
                "amount": amount,
                "currency_id": line.company_currency_id.id,
                "company_id": move.company_id.id,
                "partner_id": move.partner_id.id,
                "payment_term_id": move.invoice_payment_term_id.id,
                "move_id": move.id,
                "invoice_source": "posted",
            })
        return vals_list

    @api.model
    def _get_planned_invoice_moves(self):
        """Fatture in bozza che entrano nella previsione.

        - Le bozze con registrazione automatica (`auto_post` diverso da `no`)
          entrano sempre: Odoo le registrerà da solo alla data contabile. Fra
          queste c'è la prossima fattura di ogni serie ricorrente, che Odoo crea
          in bozza nel momento in cui registra la precedente.
        - Le altre bozze entrano solo per le aziende che le hanno abilitate
          nelle impostazioni di contabilità.
        """
        draft_companies = self.env["res.company"].sudo().search([
            ("cash_forecast_include_draft_invoices", "=", True),
        ])
        return self.env["account.move"].sudo().search([
            ("state", "=", "draft"),
            ("move_type", "in", INVOICE_MOVE_TYPES),
            "|",
            ("auto_post", "!=", "no"),
            ("company_id", "in", draft_companies.ids),
        ])

    @api.model
    def _invoice_term_lines(self, move):
        """Righe di credito/debito della fattura, una per scadenza."""
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type
            in ("asset_receivable", "liability_payable")
        )

    @api.model
    def _planned_invoice_line_vals(self, move, forecast_date, document_date, amount,
                                   source, name=None):
        """Valori di una riga di previsione da una scadenza di fattura non registrata."""
        return {
            "name": name or self._invoice_display_name(move),
            "forecast_date": forecast_date,
            "document_date": document_date,
            "direction": "in" if amount > 0 else "out",
            "document_type": (
                "customer_invoice_planned" if move.is_sale_document()
                else "vendor_bill_planned"
            ),
            "amount": amount,
            "currency_id": move.company_currency_id.id,
            "company_id": move.company_id.id,
            "partner_id": move.partner_id.id,
            "payment_term_id": move.invoice_payment_term_id.id,
            "move_id": move.id,
            "invoice_source": source,
        }

    @api.model
    def _invoice_display_name(self, move):
        """Nome della fattura: le bozze non hanno ancora un numero."""
        if move.name and move.name != "/":
            return move.name
        return "Bozza %s" % (move.ref or move.partner_id.display_name or move.id)

    @api.model
    def _collect_planned_invoice_vals(self, planned_moves):
        """Fatture in bozza e programmate, una riga per scadenza.

        Una bozza non può essere riconciliata, quindi l'importo è tutto il
        saldo della riga di credito/debito.
        """
        vals_list = []
        for move in planned_moves:
            source = "draft" if move.auto_post == "no" else "scheduled"
            for line in self._invoice_term_lines(move):
                if line.company_currency_id.is_zero(line.balance):
                    continue
                vals_list.append(self._planned_invoice_line_vals(
                    move,
                    line.date_maturity or move.invoice_date_due or move.date,
                    move.invoice_date or move.date,
                    line.balance,
                    source,
                ))
        return vals_list

    @api.model
    def _collect_recurring_invoice_vals(self, planned_moves):
        """Ricorrenze future delle fatture periodiche, non ancora create.

        Odoo tiene in vita una serie ricorrente con una sola bozza alla volta:
        quando registra una fattura crea in bozza la successiva, finché la data
        non supera `auto_post_until`. Le ricorrenze oltre quella bozza non
        esistono ancora e si proiettano qui, replicando l'ultima fattura della
        serie; la bozza stessa entra già dalle fatture programmate e quelle
        registrate e non pagate dalle fatture aperte, senza doppi conteggi.

        Esempio: fattura mensile dal 26 febbraio al 26 dicembre e oggi è il 30
        settembre. Settembre è registrata, ottobre è la bozza programmata,
        novembre e dicembre sono le ricorrenze future.

        Una serie senza bozza pendente è conclusa (fine ricorrenza raggiunta,
        bozza cancellata o registrazione automatica disattivata) e non
        proietta niente. Oltre `RECURRING_HORIZON_MONTHS` da oggi non si
        proietta comunque.
        """
        Move = self.env["account.move"].sudo()
        horizon = fields.Date.context_today(self) + relativedelta(
            months=RECURRING_HORIZON_MONTHS
        )
        # l'ultima bozza di ogni serie, identificata dalla sua prima fattura
        tails = {}
        for move in planned_moves.filtered(
            lambda move: move.auto_post in PERIODIC_AUTO_POST
        ):
            origin = move.auto_post_origin_id or move
            if origin not in tails or move.date > tails[origin].date:
                tails[origin] = move

        vals_list = []
        for origin, tail in tails.items():
            end_date = horizon
            if tail.auto_post_until:
                end_date = min(end_date, tail.auto_post_until)
            date = tail.date
            invoice_date = tail.invoice_date
            while True:
                # stessa regola di `account.move._copy_recurring_entries`, che
                # mantiene il giorno del mese della prima fattura della serie
                date = Move._apply_delta_recurring_entries(
                    date, origin.date, tail.auto_post
                )
                if date > end_date:
                    break
                if invoice_date and origin.invoice_date:
                    invoice_date = Move._apply_delta_recurring_entries(
                        invoice_date, origin.invoice_date, tail.auto_post
                    )
                else:
                    invoice_date = date
                name = "%s (ricorrenza %s)" % (
                    self._invoice_display_name(tail), date.strftime("%m/%Y")
                )
                for forecast_date, amount in self._recurring_terms(
                    tail, date, invoice_date
                ):
                    vals_list.append(self._planned_invoice_line_vals(
                        tail, forecast_date, invoice_date, amount, "recurring",
                        name=name,
                    ))
        return vals_list

    @api.model
    def _recurring_terms(self, tail, date, invoice_date):
        """Scadenze e importi di una ricorrenza futura della fattura `tail`.

        Replica quello che farà Odoo quando creerà la copia: con un termine di
        pagamento le scadenze sono ricalcolate dalla nuova data fattura, con gli
        stessi importi di `account.move._compute_needed_terms`; senza termine
        la scadenza mantiene la distanza in giorni dalla data contabile.
        Restituisce coppie (data, importo in valuta aziendale).
        """
        payment_term = tail.invoice_payment_term_id
        if payment_term:
            sign = 1 if tail.is_inbound(include_receipts=True) else -1
            terms = payment_term._compute_terms(
                date_ref=invoice_date,
                currency=tail.currency_id,
                company=tail.company_id,
                tax_amount_currency=tail.amount_tax * sign,
                tax_amount=tail.amount_tax_signed,
                untaxed_amount_currency=tail.amount_untaxed * sign,
                untaxed_amount=tail.amount_untaxed_signed,
                cash_rounding=tail.invoice_cash_rounding_id,
                sign=sign,
            )
            return [
                (fields.Date.to_date(term["date"]), term["company_amount"])
                for term in terms["line_ids"]
                if not tail.company_currency_id.is_zero(term["company_amount"])
            ]
        offset = date - tail.date
        return [
            ((line.date_maturity or tail.invoice_date_due or tail.date) + offset,
             line.balance)
            for line in self._invoice_term_lines(tail)
            if not line.company_currency_id.is_zero(line.balance)
        ]

    @api.model
    def _collect_sale_order_vals(self, planned_moves):
        """Ordini clienti confermati, per la parte non ancora fatturata."""
        orders = self.env["sale.order"].sudo().search([("state", "=", "sale")])
        vals_list = []
        for order in orders:
            residual = self._sale_order_residual(order, planned_moves)
            if order.currency_id.is_zero(residual):
                continue
            base_date = self._to_forecast_date(
                order, order.commitment_date or order.expected_date or order.date_order
            )
            for forecast_date, amount in self._split_on_payment_term(
                order, residual, base_date
            ):
                vals_list.append({
                    "name": order.name,
                    "forecast_date": forecast_date,
                    "document_date": base_date,
                    "direction": "in",
                    "document_type": "sale_order",
                    "amount": amount,
                    "currency_id": order.company_id.currency_id.id,
                    "company_id": order.company_id.id,
                    "partner_id": order.partner_id.id,
                    "payment_term_id": order.payment_term_id.id,
                    "sale_order_id": order.id,
                })
        return vals_list

    @api.model
    def _collect_purchase_order_vals(self, planned_moves):
        """Ordini fornitori confermati, per la parte non ancora fatturata."""
        orders = self.env["purchase.order"].sudo().search([
            ("state", "in", ("purchase", "done")),
        ])
        vals_list = []
        for order in orders:
            residual = self._purchase_order_residual(order, planned_moves)
            if order.currency_id.is_zero(residual):
                continue
            base_date = self._to_forecast_date(
                order, order.date_planned or order.date_order
            )
            for forecast_date, amount in self._split_on_payment_term(
                order, residual, base_date
            ):
                vals_list.append({
                    "name": order.name,
                    "forecast_date": forecast_date,
                    "document_date": base_date,
                    "direction": "out",
                    "document_type": "purchase_order",
                    "amount": -amount,
                    "currency_id": order.company_id.currency_id.id,
                    "company_id": order.company_id.id,
                    "partner_id": order.partner_id.id,
                    "payment_term_id": order.payment_term_id.id,
                    "purchase_order_id": order.id,
                })
        return vals_list

    @api.model
    def _sale_order_residual(self, order, planned_moves):
        """Importo dell'ordine cliente non ancora fatturato, imposte incluse.

        `amount_invoiced` conta solo le fatture registrate: le bozze che
        entrano nella previsione vanno tolte anche dall'ordine, altrimenti lo
        stesso importo comparirebbe due volte.
        """
        residual = order.amount_total - order.amount_invoiced
        today = fields.Date.context_today(self)
        for invoice_line in order.order_line.invoice_lines:
            invoice = invoice_line.move_id
            if invoice not in planned_moves:
                continue
            # stesso calcolo di `sale.order.line._compute_amount_invoiced`
            residual -= invoice_line.currency_id._convert(
                invoice_line.price_total,
                order.currency_id,
                order.company_id,
                invoice.invoice_date or today,
            ) * -invoice.direction_sign
        return max(residual, 0.0)

    @api.model
    def _purchase_order_residual(self, order, planned_moves):
        """Importo dell'ordine fornitore non ancora fatturato, imposte incluse.

        Si usa il rapporto tra quantità ordinata e quantità già fatturata: la
        previsione riguarda tutto quanto resta da fatturare, anche quando la
        merce non è ancora stata ricevuta. Sugli ordini clienti si usa invece
        `amount_invoiced`, che l'ordine espone già ed è esatto anche con gli
        acconti.

        Al contrario delle vendite, `qty_invoiced` conta anche le bozze: quelle
        escluse dalla previsione si restituiscono all'ordine, altrimenti la
        loro quantità non comparirebbe da nessuna parte.
        """
        total = 0.0
        for line in order.order_line:
            if line.display_type:
                continue
            quantity = line.product_qty
            if not quantity:
                continue
            remaining = (
                quantity
                - line.qty_invoiced
                + self._purchase_line_excluded_draft_qty(line, planned_moves)
            )
            if remaining <= 0:
                continue
            total += line.price_total * (remaining / quantity)
        return total

    @api.model
    def _purchase_line_excluded_draft_qty(self, line, planned_moves):
        """Quantità della riga d'ordine sulle bozze escluse dalla previsione."""
        quantity = 0.0
        for invoice_line in line.invoice_lines:
            invoice = invoice_line.move_id
            if invoice.state != "draft" or invoice in planned_moves:
                continue
            # stesso calcolo di `purchase.order.line._prepare_qty_invoiced`
            sign = {"in_invoice": 1, "in_refund": -1}.get(invoice.move_type, 0)
            quantity += sign * invoice_line.product_uom_id._compute_quantity(
                invoice_line.quantity, line.product_uom_id
            )
        return quantity

    @api.model
    def _to_forecast_date(self, record, value):
        """Riporta una data/ora del documento a una data nel fuso dell'utente."""
        if not value:
            return fields.Date.context_today(record)
        if isinstance(value, datetime):
            return fields.Datetime.context_timestamp(record, value).date()
        return value

    @api.model
    def _split_on_payment_term(self, order, amount_currency, base_date):
        """Ripartisce l'importo dell'ordine sulle scadenze del termine di pagamento.

        Restituisce coppie (data, importo in valuta aziendale) con la data di
        consegna prevista come riferimento, così che l'incasso o il pagamento
        cada dopo i giorni previsti dal termine.
        """
        company = order.company_id
        amount_company = order.currency_id._convert(
            amount_currency, company.currency_id, company, base_date
        )
        payment_term = order.payment_term_id
        if not payment_term:
            return [(base_date, amount_company)]
        terms = payment_term._compute_terms(
            date_ref=base_date,
            currency=order.currency_id,
            company=company,
            tax_amount=0.0,
            tax_amount_currency=0.0,
            sign=1,
            untaxed_amount=amount_company,
            untaxed_amount_currency=amount_currency,
        )
        return [
            (term["date"], term["company_amount"])
            for term in terms["line_ids"]
            if term["company_amount"]
        ]
