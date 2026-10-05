**Italiano**

Il modulo funziona sui documenti gia registrati subito dopo l'installazione.

In *Contabilita ▸ Configurazione ▸ Impostazioni ▸ Previsioni di cassa* l'opzione
**Fatture in bozza nelle previsioni di cassa**, per azienda e disattivata di
default, aggiunge alla previsione le fatture clienti e fornitori in bozza. Le
bozze programmate e le fatture ricorrenti entrano sempre. Cambiare l'opzione
rigenera subito le previsioni.

Le previsioni sono rigenerate:

- all'installazione del modulo (`post_init_hook`), altrimenti la dashboard
  resterebbe vuota fino al primo giro di cron;
- all'apertura della dashboard, se le righe sono piu vecchie di cinque minuti,
  cosi ordini e fatture appena registrati compaiono senza aspettare il cron;
- a ogni apertura del menu in Contabilita;
- dal bottone *Aggiorna* in alto nella dashboard, che rigenera subito le
  previsioni senza aspettare i cinque minuti e poi ricarica la pagina: serve
  dopo aver registrato una fattura o un ordine;
- una volta al giorno dal cron *Previsioni di cassa: aggiornamento*, che resta
  come rete di sicurezza e si puo disattivare o rischedulare da
  *Impostazioni ▸ Tecnico ▸ Automazione ▸ Azioni pianificate*.

Le soglie sono costanti di codice: `OVERDUE_DAYS` in
`models/cash_forecast_line.py` per l'accorpamento dello scaduto,
`RECURRING_HORIZON_MONTHS` nello stesso file per l'orizzonte delle ricorrenze e
`max_age_minutes` di `_refresh_forecast_if_stale` per la freschezza dei dati
della dashboard.

Il bottone della dashboard e un'estensione dell'azione standard
(`static/src/dashboard_refresh_button.js` e `.xml`, nel bundle
`spreadsheet.o_spreadsheet`): chiama `action_refresh_forecast`, cioe lo stesso
lavoro del cron, e poi ricarica la pagina. Il ricaricamento non e una pigrizia:
la dashboard tiene in memoria tutto quello che ha letto all'apertura — pivot,
grafici e le celle che dipendono da loro — e riaprirla e il modo sicuro di
rivedere i numeri appena rigenerati; al rientro le previsioni sono fresche di
pochi secondi, quindi non vengono rigenerate una seconda volta. Il bottone
compare sulle dashboard che leggono le previsioni, riconosciute dai grafici
agganciati al modello.

La dashboard spreadsheet si puo modificare dall'interfaccia
(*Dashboard ▸ Modifica*) oppure rigenerare da
`tools/build_dashboard.py`, che riscrive `data/files/cash_forecast_dashboard.json`:

```bash
python3 xpmi_cash_forecast/tools/build_dashboard.py
```

**English**

The module works on the documents already encoded right after installation.
The *Fatture in bozza nelle previsioni di cassa* option in the Accounting
settings, per company and off by default, adds draft invoices to the forecast;
scheduled and recurring invoices are always included.

The forecast is rebuilt on install (`post_init_hook`), when the dashboard is
opened and the lines are older than five minutes, on every opening of the
Accounting menu, from the *Aggiorna* button on top of the dashboard, which
rebuilds the forecast right away and reloads the page, and once a day by the
*Previsioni di cassa: aggiornamento* scheduled action, which can be disabled or
rescheduled from *Settings ▸ Technical ▸ Automation ▸ Scheduled Actions*.

The spreadsheet dashboard can be edited from the interface
(*Dashboards ▸ Edit*) or regenerated with `tools/build_dashboard.py`, which
rewrites `data/files/cash_forecast_dashboard.json`.
