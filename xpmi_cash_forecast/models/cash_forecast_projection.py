from odoo import fields, models
from odoo.tools.sql import SQL

from .cash_forecast_line import DOCUMENT_TYPES

SCENARIOS = [
    ("invoices", "Banca e fatture"),
    ("orders", "Banca, fatture e ordini"),
]

# Tipi di documento che compongono lo scenario delle fatture: il saldo di banca
# e cassa, le fatture registrate e la fatturazione prevista (bozze, fatture
# programmate e ricorrenze future). Il secondo scenario aggiunge gli ordini.
INVOICE_SCENARIO_TYPES = (
    "bank_balance",
    "customer_invoice",
    "vendor_bill",
    "customer_invoice_planned",
    "vendor_bill_planned",
)


class CashForecastProjection(models.Model):
    """Le righe di previsione replicate per scenario.

    Serve al grafico del saldo progressivo, che deve mostrare due linee: il
    saldo con le sole fatture e il saldo con anche gli ordini. Un grafico
    agganciato a Odoo ha un solo dominio e una sola misura, quindi le due linee
    possono nascere solo da un raggruppamento: qui ogni riga di previsione
    compare una volta per ogni scenario di cui fa parte (banca e fatture in
    entrambi, ordini solo nel secondo) e il raggruppamento su `scenario` dà le
    due linee, conservando il menu dell'intervallo (giorno, settimana, mese,
    trimestre, anno) che i grafici su celle non hanno.

    Non ha una tabella propria: `_table_query` legge al volo
    `xpmi.cash.forecast.line`, quindi segue ogni rigenerazione delle previsioni
    e lascia intatti pivot, scorecard e viste che leggono il modello di partenza
    senza doppi conteggi.
    """

    _name = "xpmi.cash.forecast.projection"
    _description = "Proiezione di cassa per scenario"
    _auto = False
    _order = "period_date, id"

    name = fields.Char(string="Documento", readonly=True)
    scenario = fields.Selection(
        selection=SCENARIOS,
        string="Scenario",
        readonly=True,
        help="Banca e fatture è il saldo con le fatture aperte e la "
             "fatturazione prevista (bozze, fatture programmate e ricorrenti); "
             "banca, fatture e ordini aggiunge gli ordini confermati non ancora "
             "fatturati.",
    )
    forecast_date = fields.Date(string="Data prevista", readonly=True)
    period_date = fields.Date(string="Periodo", readonly=True)
    document_type = fields.Selection(
        selection=DOCUMENT_TYPES, string="Tipo documento", readonly=True
    )
    amount = fields.Monetary(
        string="Importo previsto", currency_field="currency_id", readonly=True
    )
    currency_id = fields.Many2one("res.currency", string="Valuta", readonly=True)
    company_id = fields.Many2one("res.company", string="Azienda", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Partner", readonly=True)
    line_id = fields.Many2one(
        "xpmi.cash.forecast.line", string="Riga di previsione", readonly=True
    )

    @property
    def _table_query(self):
        """Ogni riga di previsione una volta per ogni scenario di cui fa parte.

        Le fatture, registrate e previste, e il saldo di banca e cassa compaiono
        in tutti e due gli scenari, gli ordini solo in quello che li considera.

        Lo scaduto oltre un mese resta fuori da tutti e due: è pregresso e non
        una proiezione futura, come nel riepilogo dove ha una colonna sua che
        non si riporta.

        Il saldo di banca e cassa è datato **il giorno prima del primo flusso**
        invece che oggi: è la giacenza da cui parte la proiezione, quindi deve
        precedere ogni incasso e ogni pagamento. Con la data di oggi le righe
        già scadute da meno di un mese — che restano nel periodo in cui sono
        scadute — verrebbero prima del saldo, e il cumulato partirebbe da quelle
        invece che dalla giacenza. Il minimo è per azienda ed è calcolato prima
        di separare gli scenari, così le due linee del grafico partono dallo
        stesso punto. Cambia solo `period_date`, il campo su cui grafici e
        riepiloghi raggruppano: `forecast_date` resta oggi, che è la data vera
        del saldo.
        """
        return SQL(
            """
                WITH forecast AS (
                    SELECT
                        line.id,
                        line.name,
                        line.forecast_date,
                        line.document_type,
                        line.amount,
                        line.currency_id,
                        line.company_id,
                        line.partner_id,
                        CASE
                            WHEN line.document_type = 'bank_balance'
                                THEN COALESCE(
                                    MIN(line.period_date) FILTER (
                                        WHERE line.document_type != 'bank_balance'
                                    ) OVER (PARTITION BY line.company_id) - 1,
                                    line.period_date
                                )
                            ELSE line.period_date
                        END AS period_date
                    FROM xpmi_cash_forecast_line line
                    WHERE NOT line.is_overdue
                )
                SELECT
                    forecast.id * 2 AS id,
                    'invoices' AS scenario,
                    forecast.id AS line_id,
                    forecast.name,
                    forecast.forecast_date,
                    forecast.period_date,
                    forecast.document_type,
                    forecast.amount,
                    forecast.currency_id,
                    forecast.company_id,
                    forecast.partner_id
                FROM forecast
                WHERE forecast.document_type IN %s
                UNION ALL
                SELECT
                    forecast.id * 2 + 1 AS id,
                    'orders' AS scenario,
                    forecast.id AS line_id,
                    forecast.name,
                    forecast.forecast_date,
                    forecast.period_date,
                    forecast.document_type,
                    forecast.amount,
                    forecast.currency_id,
                    forecast.company_id,
                    forecast.partner_id
                FROM forecast
            """,
            INVOICE_SCENARIO_TYPES,
        )
