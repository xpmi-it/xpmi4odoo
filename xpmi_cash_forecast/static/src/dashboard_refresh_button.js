import { patch } from "@web/core/utils/patch";
import { browser } from "@web/core/browser/browser";
import { useState } from "@odoo/owl";
import { SpreadsheetDashboardAction } from "@spreadsheet_dashboard/bundle/dashboard_action/dashboard_action";

const FORECAST_MODEL = "xpmi.cash.forecast.line";
// i grafici della dashboard leggono xpmi.cash.forecast.line e .projection
const FORECAST_MODEL_PREFIX = "xpmi.cash.forecast";

/**
 * Bottone di aggiornamento sulla dashboard delle previsioni di cassa.
 *
 * La dashboard rigenera le previsioni da sola quando sono più vecchie di
 * cinque minuti; il bottone serve a non aspettare dopo aver registrato una
 * fattura o un ordine. Fa lo stesso lavoro del cron e poi ricarica la pagina.
 *
 * Ricaricare la pagina, invece di aggiornare le sorgenti dati dello
 * spreadsheet, è il modo sicuro di rivedere i numeri nuovi: la dashboard tiene
 * in memoria tutto quello che ha letto all'apertura — pivot, grafici e le celle
 * che dipendono da loro — e alla riapertura riparte dai dati appena rigenerati.
 *
 * Il bottone compare sulle dashboard che leggono le previsioni, riconosciute
 * dai grafici agganciati al modello: è una lettura sincrona dello spreadsheet
 * già in memoria, senza chiamate al server che possano fallire lasciando il
 * bottone invisibile.
 */
patch(SpreadsheetDashboardAction.prototype, {
    setup() {
        super.setup();
        this.cashForecast = useState({ refreshing: false });
    },

    get isCashForecastDashboard() {
        const model = this.loader.getActiveDashboard()?.model;
        if (!model) {
            return false;
        }
        try {
            return model.getters.getOdooChartIds().some((chartId) => {
                const definition = model.getters.getChartDefinition(chartId);
                return definition.metaData?.resModel?.startsWith(FORECAST_MODEL_PREFIX);
            });
        } catch {
            // una dashboard di un altro modulo non deve rompersi per il bottone
            return false;
        }
    },

    async refreshCashForecast() {
        if (this.cashForecast.refreshing) {
            return;
        }
        this.cashForecast.refreshing = true;
        try {
            await this.orm.call(FORECAST_MODEL, "action_refresh_forecast", []);
        } catch (error) {
            // l'icona smette di girare solo se restiamo sulla pagina
            this.cashForecast.refreshing = false;
            throw error;
        }
        browser.location.reload();
    },
});
