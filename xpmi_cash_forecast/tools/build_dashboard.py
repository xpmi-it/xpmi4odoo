"""Genera `data/files/cash_forecast_dashboard.json`.

Il file è uno spreadsheet o-spreadsheet: si rigenera con

    python3 xpmi_cash_forecast/tools/build_dashboard.py

da eseguire dalla cartella che contiene il modulo. In alternativa la dashboard
si può modificare dall'interfaccia (Dashboards ▸ Modifica) ed esportare.
"""
import json
import os

MODEL = "xpmi.cash.forecast.line"
# le righe replicate per scenario, sorgente delle due linee del saldo progressivo
PROJECTION_MODEL = "xpmi.cash.forecast.projection"
FILTER_ID = "cf-filter-period"
FIELD_MATCHING = {FILTER_ID: {"chain": "period_date", "type": "date", "offset": 0}}
MEASURE = {"id": "amount", "fieldName": "amount", "aggregator": "sum"}


def odoo_chart(chart_id, title, mode, group_by, domain=None, cumulative=False,
               model=MODEL, data_sets=None, legend=None):
    """Grafico agganciato al modello.

    Il raggruppamento principale è scritto come `campo:granularità` perché la
    dashboard mostri sul grafico la scelta fra giorno, settimana, mese,
    trimestre e anno.

    Un grafico agganciato a Odoo ha un solo dominio e una sola misura: le serie
    nascono dal secondo raggruppamento. `data_sets` dà a ognuna il suo colore,
    nell'ordine in cui il modello restituisce i gruppi.

    `cumulative` somma i periodi uno dopo l'altro: partendo dal saldo di banca e
    cassa ogni punto è il saldo atteso a fine periodo. Vale però per tutte le
    serie del grafico, ed è il motivo per cui saldo progressivo e movimenti di
    periodo stanno su due grafici distinti invece che su un unico combinato.
    """
    data = {
        "title": {"text": title, "bold": True, "color": "#01666B"},
        "background": "#FFFFFF",
        "legendPosition": legend or ("none" if cumulative else "top"),
        "metaData": {
            "groupBy": group_by,
            "measure": "amount",
            "order": None,
            "resModel": model,
            "mode": mode,
        },
        "searchParams": {
            "comparison": None,
            "context": {},
            "domain": domain or [],
            "groupBy": group_by,
            "orderBy": [],
        },
        "type": "odoo_%s" % mode,
        "dataSets": data_sets if data_sets is not None else ([{}] if mode == "line" else []),
        "humanize": True,
        "verticalAxisPosition": "left",
        "stacked": mode == "bar",
        "chartId": chart_id,
        "fieldMatching": dict(FIELD_MATCHING),
    }
    if cumulative:
        data["metaData"]["cumulatedStart"] = True
        data["cumulative"] = True
        data["cumulatedStart"] = True
        data["fillArea"] = False
    return {"id": chart_id, "tag": "chart", "data": data}


def scorecard(chart_id, title, key_cell, background):
    return {
        "id": chart_id,
        "tag": "chart",
        "data": {
            "type": "scorecard",
            "title": {"text": title, "bold": True, "color": "#434343"},
            "background": background,
            "keyValue": key_cell,
            "baseline": "",
            "baselineMode": "difference",
            "baselineColorDown": "#EA6175",
            "baselineColorUp": "#43C5B1",
            "humanize": False,
            "chartId": chart_id,
        },
    }


def placed(figure, col, row, width, height, x=8, y=8):
    return dict(figure, col=col, row=row, offset={"x": x, "y": y}, width=width, height=height)


def pivot(pivot_id, name, period_field):
    """Le colonne usano i campi periodo del modello, non la data.

    Così tutto lo scaduto da oltre un mese sta in una sola colonna invece di
    aprirne una per ogni mese passato.
    """
    return {
        "type": "ODOO",
        "id": pivot_id,
        "formulaId": pivot_id,
        "name": name,
        "model": MODEL,
        "domain": [],
        "context": {},
        "columns": [{"fieldName": period_field, "order": "asc"}],
        "rows": [{"fieldName": "document_type", "order": "asc"}],
        "measures": [dict(MEASURE)],
        "fieldMatching": dict(FIELD_MATCHING),
    }


pivots = {
    "1": pivot("1", "Previsione per mese", "period_month"),
    "2": pivot("2", "Previsione per settimana", "period_week"),
    "3": {
        "type": "ODOO",
        "id": "3",
        "formulaId": "3",
        "name": "Previsione per tipo documento",
        "model": MODEL,
        "domain": [],
        "context": {},
        "columns": [],
        "rows": [{"fieldName": "document_type", "order": "asc"}],
        "measures": [dict(MEASURE)],
        "fieldMatching": dict(FIELD_MATCHING),
    },
}

OVERDUE_LABEL = "Scaduto oltre 30 gg"
PERIODS = 12  # colonne di periodo dopo quella dello scaduto

# righe di movimento del riepilogo: etichetta e tipo documento
FLOW_ROWS = [
    ("Fatture clienti", "customer_invoice"),
    ("Fatturazione prevista clienti", "customer_invoice_planned"),
    ("Ordini clienti", "sale_order"),
    ("Fatture fornitori", "vendor_bill"),
    ("Fatturazione prevista fornitori", "vendor_bill_planned"),
    ("Ordini fornitori", "purchase_order"),
]


def column_letter(index):
    """Da indice 0 a lettera di colonna (A, B, ... Z, AA)."""
    letters = ""
    while True:
        letters = chr(ord("A") + index % 26) + letters
        index = index // 26 - 1
        if index < 0:
            return letters


def summary_table(first_row, title, pivot_id, period_field, header_formula):
    """Riepilogo con il saldo riportato di periodo in periodo.

    Le colonne sono fisse (lo scaduto più i periodi successivi) perché il
    riporto ha bisogno di sapere qual è la colonna precedente: il saldo
    iniziale di un periodo è il saldo finale di quello prima, e il saldo finale
    è il saldo iniziale più i movimenti del periodo.

    La colonna dello scaduto resta senza saldo iniziale: è pregresso, non una
    proiezione futura, e non deve trascinarsi nei periodi successivi. Il saldo
    di banca e cassa apre quindi la prima colonna di periodo.
    """
    cells = {}
    styles = {}
    formats = {}
    header_row = first_row + 1
    opening_row = header_row + 1
    flow_first = opening_row + 1
    flow_last = flow_first + len(FLOW_ROWS) - 1
    closing_row = flow_last + 1

    cells["A%d" % first_row] = '=_t("%s")' % title
    styles["A%d" % first_row] = 2

    cells["A%d" % header_row] = '=_t("Periodo")'
    cells["A%d" % opening_row] = '=_t("Saldo iniziale")'
    for offset, (label, _document_type) in enumerate(FLOW_ROWS):
        cells["A%d" % (flow_first + offset)] = '=_t("%s")' % label
    cells["A%d" % closing_row] = '=_t("Saldo finale")'
    styles["A%d:A%d" % (header_row, closing_row)] = 3
    styles["A%d" % header_row] = 2
    styles["A%d" % opening_row] = 2
    styles["A%d" % closing_row] = 2

    for index in range(PERIODS + 1):
        col = column_letter(index + 1)
        previous = column_letter(index)
        overdue_column = index == 0

        # l'intestazione è anche la chiave usata da PIVOT.VALUE, quindi per lo
        # scaduto è testo letterale e non una stringa tradotta
        cells["%s%d" % (col, header_row)] = (
            OVERDUE_LABEL if overdue_column else header_formula(index - 1)
        )
        styles["%s%d" % (col, header_row)] = 5

        # lo scaduto non ha saldo iniziale: il pregresso non è una proiezione
        # futura, quindi il saldo di banca e cassa apre il primo periodo vero e
        # da lì si riporta di colonna in colonna
        if index == 1:
            cells["%s%d" % (col, opening_row)] = (
                '=IFERROR(PIVOT.VALUE(3,"amount","document_type","bank_balance"),0)'
            )
        elif not overdue_column:
            cells["%s%d" % (col, opening_row)] = "=%s%d" % (previous, closing_row)
        for offset, (_label, document_type) in enumerate(FLOW_ROWS):
            cells["%s%d" % (col, flow_first + offset)] = (
                '=IFERROR(PIVOT.VALUE(%s,"amount","document_type","%s","%s",%s$%d),0)'
                % (pivot_id, document_type, period_field, col, header_row)
            )
        cells["%s%d" % (col, closing_row)] = "=%s%d+SUM(%s%d:%s%d)" % (
            col, opening_row, col, flow_first, col, flow_last
        )

    last_col = column_letter(PERIODS + 1)
    styles["B%d:%s%d" % (opening_row, last_col, closing_row)] = 4
    formats["B%d:%s%d" % (opening_row, last_col, closing_row)] = 1
    rows = {
        "header": header_row,
        "opening": opening_row,
        "flow_first": flow_first,
        "flow_last": flow_last,
        "closing": closing_row,
    }
    return cells, styles, formats, rows


def month_header(offset):
    return '=TEXT(EDATE(TODAY(),%d),"yyyy-mm")' % offset


def week_header(offset):
    return '=TEXT(TODAY()-WEEKDAY(TODAY(),3)+%d,"yyyy-mm-dd")' % (7 * offset)


month_cells, month_styles, month_formats, MONTH_ROWS = summary_table(
    32, "Riepilogo mensile", "1", "period_month", month_header
)
week_cells, week_styles, week_formats, week_rows = summary_table(
    MONTH_ROWS["closing"] + 3, "Riepilogo settimanale", "2", "period_week", week_header
)
week_last = week_rows["closing"]

dashboard_cells = {
    "A1": '=_t("Previsioni di cassa")',
    "A2": '=_t("Fatture aperte, fatturazione prevista e ordini confermati non ancora fatturati")',
    **month_cells,
    **week_cells,
}
dashboard_styles = {"A1": 1, "A2": 3, **month_styles, **week_styles}
dashboard_formats = {**month_formats, **week_formats}

figures = [
    placed(scorecard("cf-score-bank", "Saldo banca e cassa oggi", "Dati!B2", "#F8FAFC"), 0, 3, 270, 120),
    placed(scorecard("cf-score-in", "Incassi previsti", "Dati!B3", "#F0FDF4"), 3, 3, 270, 120),
    placed(scorecard("cf-score-out", "Pagamenti previsti", "Dati!B4", "#FEF2F2"), 6, 3, 270, 120),
    placed(scorecard("cf-score-net", "Saldo previsto", "Dati!B5", "#EFF6FF"), 9, 3, 270, 120),
    # due linee: il saldo con le sole fatture e quello che aggiunge gli ordini
    # confermati non ancora fatturati. Vengono dal raggruppamento su `scenario`
    # del modello di proiezione, dove ogni riga compare una volta per ogni
    # scenario di cui fa parte
    placed(odoo_chart("cf-chart-balance", "Saldo di cassa progressivo", "line",
                      ["period_date:month", "scenario"], cumulative=True,
                      model=PROJECTION_MODEL, legend="top",
                      data_sets=[{"backgroundColor": "#01666B"},
                                 {"backgroundColor": "#43C5B1"}]),
           0, 9, 1100, 260, y=0),
    # il saldo di banca e cassa è una giacenza, non un flusso: nelle barre dei
    # movimenti non ci va
    placed(odoo_chart("cf-chart-flows", "Incassi e pagamenti previsti per periodo",
                      "bar", ["period_date:month", "document_type"],
                      domain=[("document_type", "!=", "bank_balance")]),
           0, 20, 1100, 260, y=0),
]

data_cells = {
    "A1": '=_t("Indicatore")',
    "B1": '=_t("Valore")',
    "A2": '=_t("Saldo banca e cassa oggi")',
    "B2": '=PIVOT.VALUE(3,"amount","document_type","bank_balance")',
    "A3": '=_t("Incassi previsti")',
    # la fatturazione prevista può mancare del tutto: IFERROR evita che la
    # scorecard vada in errore quando il pivot non ha quel tipo documento
    "B3": '=PIVOT.VALUE(3,"amount","document_type","customer_invoice")'
          '+IFERROR(PIVOT.VALUE(3,"amount","document_type","customer_invoice_planned"),0)'
          '+PIVOT.VALUE(3,"amount","document_type","sale_order")',
    "A4": '=_t("Pagamenti previsti")',
    "B4": '=PIVOT.VALUE(3,"amount","document_type","vendor_bill")'
          '+IFERROR(PIVOT.VALUE(3,"amount","document_type","vendor_bill_planned"),0)'
          '+PIVOT.VALUE(3,"amount","document_type","purchase_order")',
    "A5": '=_t("Saldo previsto")',
    "B5": "=B2+B3+B4",
}


def sheet(sheet_id, name, cells, figures, styles, col_number, row_number, cols,
          formats=None):
    return {
        "id": sheet_id,
        "name": name,
        "colNumber": col_number,
        "rowNumber": row_number,
        "rows": {},
        "cols": cols,
        "merges": [],
        "cells": cells,
        "styles": styles,
        "formats": formats or {},
        "borders": {},
        "conditionalFormats": [],
        "dataValidationRules": [],
        "figures": figures,
        "tables": [],
        "areGridLinesVisible": False,
        "isVisible": True,
        "headerGroups": {"ROW": [], "COL": []},
        "comments": {},
    }


data = {
    "version": "18.5.10",
    "sheets": [
        sheet("cash-forecast-dashboard", "Previsioni di cassa", dashboard_cells, figures,
              dashboard_styles, 20, week_last + 4, {"0": {"size": 200}},
              formats=dashboard_formats),
        sheet("cash-forecast-data", "Dati", data_cells, [],
              {"A1:B1": 2, "A2:A5": 3}, 6, 20, {"0": {"size": 200}, "1": {"size": 150}}),
    ],
    "styles": {
        "1": {"textColor": "#01666b", "bold": True, "fontSize": 16},
        "2": {"textColor": "#434343", "bold": True, "fontSize": 11},
        "3": {"textColor": "#434343", "verticalAlign": "middle"},
        "4": {"textColor": "#434343", "align": "right"},
        "5": {"textColor": "#434343", "bold": True, "fontSize": 11, "align": "right"},
    },
    "formats": {"1": "#,##0.00"},
    "borders": {},
    "revisionId": "START_REVISION",
    "uniqueFigureIds": True,
    "settings": {
        "locale": {
            "name": "Italiano",
            "code": "it_IT",
            "thousandsSeparator": ".",
            "decimalSeparator": ",",
            "dateFormat": "dd/mm/yyyy",
            "timeFormat": "hh:mm:ss",
            "formulaArgSeparator": ",",
            "weekStart": 1,
        }
    },
    "pivots": pivots,
    "pivotNextId": 4,
    "customTableStyles": {},
    "globalFilters": [{"id": FILTER_ID, "type": "date", "label": "Periodo"}],
    "lists": {},
    "listNextId": 1,
    "chartOdooMenusReferences": {},
}

path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "data", "files", "cash_forecast_dashboard.json")
with open(os.path.normpath(path), "w") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)
    fh.write("\n")
print("scritto", os.path.normpath(path))
