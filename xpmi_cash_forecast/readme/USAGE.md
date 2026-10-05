**Italiano**

Le previsioni si consultano da due punti principali:

- **Dashboard ▸ Finance ▸ Previsioni di cassa**: dashboard spreadsheet con il
  grafico del saldo progressivo e i riepiloghi mensile e settimanale;
- **Contabilita ▸ Rendicontazione ▸ Previsioni di cassa**: viste grafico, pivot
  e lista sulle singole righe di previsione, con i filtri di ricerca.

Sotto **Dashboard ▸ Configurazione** ci sono in piu due liste di sola lettura sui
dati grezzi, utili a controllare cosa alimenta la dashboard riga per riga:

- *Righe di previsione di cassa*: il contenuto di `xpmi.cash.forecast.line`;
- *Proiezione di cassa*: il contenuto di `xpmi.cash.forecast.projection`, cioe le
  righe replicate per scenario che disegnano le due linee del saldo progressivo.

A differenza del menu di rendicontazione queste liste **non rigenerano** le
previsioni: mostrano i dati cosi come sono al momento, quelli lasciati
dall'ultimo aggiornamento manuale o dal cron giornaliero.

Tutti questi punti sono accessibili ai gruppi *Contabilita / Sola lettura* e
*Contabilita / Fatturazione*.

## Periodo e scaduto

Grafici e riepiloghi non raggruppano sulla data prevista ma su campi di periodo,
che raccolgono in **un solo periodo** tutto cio che e scaduto da piu di un mese:
senza questo accorpamento il riepilogo aprirebbe una colonna per ogni mese
passato. La soglia e la costante `OVERDUE_DAYS` in
`models/cash_forecast_line.py`.

- `period_date` (data) e la data prevista, tranne per lo scaduto oltre soglia
  che e riportato a **oggi**: sono incassi e pagamenti attesi adesso, e cosi il
  saldo progressivo parte dal saldo di banca e cassa invece che da periodi
  passati. Lo usano il grafico e il pivot delle viste Odoo e il grafico della
  dashboard, cosi resta la **scelta dell'intervallo** (giorno, settimana, mese,
  trimestre, anno): nella dashboard quel menu compare solo se il raggruppamento
  del grafico e scritto come `campo:granularita`, qui `period_date:month`.
- `period_month` e `period_week` (testo) sono le stesse informazioni come
  etichetta, con lo scaduto reso esplicito (`Scaduto oltre 30 gg`, definito in
  `OVERDUE_LABEL`). Le usa la dashboard, dove non esiste un selettore di
  intervallo e l'etichetta deve dire da se cosa contiene; nel riepilogo lo
  scaduto e sempre la prima colonna perche la posizione e fissata dal
  generatore, non dedotta dall'ordine alfabetico.

Nelle viste Odoo, oltre al raggruppamento *Periodo*, ci sono le etichette
mese/settimana e il filtro *Scaduto oltre un mese*.

## Saldo progressivo

La dashboard ha due grafici, entrambi agganciati a un modello Odoo e quindi
entrambi con il **menu dell'intervallo** (giorno, settimana, mese, trimestre,
anno), che il client offre solo quando il raggruppamento principale e scritto
come `campo:granularita` — qui `period_date:month`:

- *Saldo di cassa progressivo*: due linee cumulate, che partono entrambe dal
  saldo di banca e cassa e sommano i flussi periodo dopo periodo —
  **Banca e fatture** con le fatture aperte e la fatturazione prevista (bozze,
  fatture programmate e ricorrenti) e **Banca, fatture e ordini** che aggiunge
  gli ordini confermati non ancora fatturati;
- *Incassi e pagamenti previsti per periodo*: barre per tipo di documento, senza
  il saldo di banca e cassa che e una giacenza e non un flusso.

Le due linee arrivano da `xpmi.cash.forecast.projection`
(`models/cash_forecast_projection.py`), non da `xpmi.cash.forecast.line`: un
grafico agganciato a Odoo ha un solo dominio e una sola misura, quindi due
scenari possono nascere solo da un raggruppamento. Il modello non ha una tabella
propria — `_table_query` rilegge le righe di previsione — e ripete ogni riga una
volta per ogni scenario di cui fa parte: banca, fatture e fatturazione prevista
in tutti e due, ordini solo nel secondo. Il grafico raggruppa su
`period_date:month` e `scenario`, cosi
resta un grafico Odoo con il suo menu dell'intervallo; pivot, scorecard e viste
continuano a leggere `xpmi.cash.forecast.line`, senza doppi conteggi.

Nella proiezione il saldo di banca e cassa non e datato oggi ma **il giorno
prima del primo flusso**: e la giacenza di partenza, quindi deve precedere ogni
incasso e ogni pagamento. Con la data di oggi le righe gia scadute da meno di un
mese — che restano nel periodo in cui sono scadute — verrebbero prima del saldo e
il cumulato partirebbe da quelle invece che dalla giacenza. Il minimo e calcolato
per azienda e prima di separare gli scenari, cosi le due linee partono dallo
stesso punto; cambia solo il periodo, la data prevista del saldo resta oggi.

Come il riepilogo, le due linee **lasciano fuori lo scaduto oltre un mese**: e
pregresso e non una proiezione futura, e sommarlo al saldo di banca e cassa —
che quel pregresso non lo contiene — gonfierebbe tutta la curva. Le due linee
partono quindi dal saldo di banca e cassa e coincidono con la riga *saldo
finale* del riepilogo mensile, quella con gli ordini.

Sono due grafici e non un unico combinato perche la cumulazione di un grafico
Odoo vale per tutte le sue serie: in un combo le barre dei movimenti
diventerebbero anch'esse progressive. Un combinato con saldo e movimenti insieme
e possibile solo leggendo le celle del riepilogo, ma perderebbe il menu
dell'intervallo: e il motivo per cui anche le due linee del saldo progressivo
sono costruite con un raggruppamento e non con le celle del riepilogo.

La dashboard mostra il grafico del saldo progressivo e due riepiloghi,
**mensile** e **settimanale**, con il periodo in testa alle colonne:

```
                    Scaduto oltre 30 gg   2026-09   2026-10
saldo iniziale                                11.726    63.591
fatture clienti               149.800         51.865        69
...
saldo finale                  149.800         63.591    63.660
```

Il **saldo si riporta** da un periodo al successivo: il saldo iniziale e il
saldo finale del periodo precedente, e il saldo finale e il saldo iniziale piu
i movimenti del periodo. La colonna dello scaduto fa eccezione: **non ha saldo
iniziale** e non si riporta, perche e pregresso e non una proiezione futura —
mostra solo i movimenti gia scaduti e il loro totale. Il saldo di banca e cassa
apre quindi la prima colonna di periodo, non quella dello scaduto.
Per poter fare il riporto le colonne sono fisse (`PERIODS` in
`tools/build_dashboard.py`, dodici periodi piu quello dello scaduto) e le celle
leggono i pivot con `PIVOT.VALUE`, invece di essere una tabella pivot espansa.

**English**

The forecast is available from two main places:

- **Dashboards ▸ Finance ▸ Previsioni di cassa**: spreadsheet dashboard with the
  running balance chart and the monthly and weekly summaries;
- **Accounting ▸ Reporting ▸ Previsioni di cassa**: graph, pivot and list views
  on the single forecast lines, with the search filters.

**Dashboards ▸ Configuration** additionally holds two read only lists on the raw
data — the forecast lines and the per scenario projection — to check row by row
what feeds the dashboard. Unlike the reporting menu they do not refresh the
forecast: they show the data as left by the last manual refresh or by the daily
cron.

All of them are available to the *Accounting / Read only* and *Accounting /
Billing* groups.

Charts and summaries do not group on the forecast date but on period fields,
which collect in **one single period** everything overdue by more than a month
(`OVERDUE_DAYS` in `models/cash_forecast_line.py`); without it the summary would
open a column for every past month. `period_date` keeps the interval selector
(day, week, month, quarter, year) of the Odoo and dashboard charts, while
`period_month` and `period_week` are the same information as a label, used by the
dashboard summaries where no interval selector exists.

The dashboard shows two charts — the cumulated *running cash balance*, with one
line for bank and invoices and one that also adds the confirmed orders, and the
per period *money in and out* bars, kept apart because cumulation in an Odoo
chart applies to every series — plus the monthly and weekly summaries, where the
closing balance of a period is carried over as the opening balance of the next
one.

In the projection the bank and cash balance is not dated today but **the day
before the first flow**: it is the opening amount, so it has to come before every
money in and out. With today's date the lines overdue by less than a month —
which stay in the period they came due in — would come before the balance and the
running total would start from those instead of from the opening amount. The
minimum is per company and taken before the scenarios are split, so both lines
start from the same point; only the period changes, the forecast date of the
balance stays today.

Whatever is overdue by more than a month stays out of the running balance and
out of the carry over: it is past due, not a forecast, and the bank balance does
not contain it, so adding it would inflate the whole curve. The two lines come
from the `xpmi.cash.forecast.projection` model, which has no table of its own and
repeats every forecast line once per scenario it belongs to: an Odoo chart has a
single domain and a single measure, so two scenarios can only come from a group
by, and this way the chart keeps its interval selector.
