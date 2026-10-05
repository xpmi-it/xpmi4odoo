**Italiano**

Previsione di cassa costruita dai documenti gia registrati: saldo di banca e
cassa, fatture clienti e fornitori aperte, fatturazione prevista (fatture
programmate, ricorrenti e, se abilitate, in bozza), ordini clienti e fornitori
confermati non ancora fatturati.

Il modello `xpmi.cash.forecast.line` viene ricostruito da zero a ogni
aggiornamento. Ogni riga e un movimento di cassa atteso, in valuta aziendale,
positivo per gli incassi e negativo per i pagamenti.

| Origine | Data prevista | Importo |
|---|---|---|
| Saldo banca e cassa | oggi | saldo contabile dei conti `asset_cash` registrati fino a oggi |
| Fatture clienti e fornitori aperte | scadenza della singola riga di credito/debito (`date_maturity`) | residuo da incassare/pagare della riga |
| Fatture programmate (bozze con `auto_post`) | scadenza della riga di credito/debito | importo della riga |
| Ricorrenze future delle fatture periodiche | scadenza ricalcolata sulla data della ricorrenza | importo dell'ultima fattura della serie |
| Fatture in bozza (se abilitate) | scadenza della riga di credito/debito | importo della riga |
| Ordini clienti confermati | data di consegna prevista + termine di pagamento | totale ordine meno quanto gia fatturato |
| Ordini fornitori confermati | data di arrivo prevista + termine di pagamento | quota non ancora fatturata delle righe |

**Tutti gli importi sono IVA inclusa**, perche la previsione riguarda il denaro
che entra ed esce dal conto:

- fatture: il residuo della riga di credito/debito e il totale documento, IVA
  compresa, al netto di quanto gia incassato o pagato;
- ordini clienti: `amount_total` meno `amount_invoiced`, entrambi IVA inclusa;
- ordini fornitori: `price_total` delle righe (IVA inclusa) in proporzione alla
  quantita non ancora fatturata.

Dettagli:

- Le fatture sono lette dalle righe contabili di credito/debito non
  riconciliate: una fattura con termine di pagamento a piu scadenze genera una
  previsione per ogni scadenza, ciascuna con il proprio residuo.
- Per gli ordini la data di partenza e `commitment_date`/`expected_date` (ordini
  clienti) e `date_planned` (ordini fornitori); su quella data si applica il
  termine di pagamento dell'ordine con lo stesso motore usato dalle fatture
  (`account.payment.term._compute_terms`), quindi un termine a piu scadenze
  produce piu righe di previsione.
- Degli ordini si considera solo la parte **non ancora fatturata**: la parte gia
  fatturata e coperta dalle righe delle fatture, senza doppi conteggi.

## Fatturazione prevista

Le fatture non ancora registrate hanno i tipi documento *Fatturazione prevista
clienti* e *Fatturazione prevista fornitori*; il campo *Origine fattura* dice da
dove arriva la riga.

- **Programmata**: fattura in bozza con registrazione automatica (`auto_post`
  diverso da *No*), che Odoo registrera da solo alla data contabile. Entra
  sempre nella previsione.
- **Ricorrenza futura**: una fattura periodica (`auto_post` mensile, trimestrale
  o annuale) vive in Odoo con una sola bozza alla volta — quando ne registra
  una, crea in bozza la successiva, fino a `auto_post_until`. Le ricorrenze
  successive a quella bozza non esistono ancora e il modulo le proietta
  replicando l'ultima fattura della serie, con le stesse regole di Odoo: data
  che mantiene il giorno del mese della prima fattura e scadenze ricalcolate dal
  termine di pagamento (senza termine, stessa distanza in giorni dalla data
  contabile). Si proietta fino a `auto_post_until` e comunque non oltre
  `RECURRING_HORIZON_MONTHS` (12) mesi da oggi, cosi anche le ricorrenze senza
  fine restano limitate. Una serie senza bozza pendente e conclusa e non
  proietta niente.
- **Bozza**: fattura in bozza senza registrazione automatica. Entra solo se
  l'azienda lo ha abilitato in *Contabilita ▸ Configurazione ▸ Impostazioni ▸
  Previsioni di cassa*.

Esempio: fattura fornitore di 1.000 del 26 febbraio, mensile fino al 26
dicembre, oggi 30 settembre. Le fatture fino a settembre sono registrate (in
previsione se non pagate), ottobre e la bozza programmata, novembre e dicembre
sono ricorrenze future: 1.000 per ottobre, novembre e dicembre.

Le bozze che entrano nella previsione sono tolte dal residuo degli ordini da cui
nascono, e quelle escluse vi sono restituite: lo stesso importo non compare mai
due volte ne sparisce.

Il saldo di banca e cassa e il punto di partenza: sommato ai flussi da il saldo
atteso alla fine di ogni periodo, ed e la somma mostrata dalla scorecard *Saldo
previsto*.

Il modulo aggiunge una dashboard spreadsheet e le viste grafico / pivot / lista,
entrambe in sola lettura: le righe non si creano ne si modificano a mano, sono
sempre il risultato della rigenerazione.

**English**

Cash forecast built from the documents already encoded: bank and cash balance,
open customer and vendor invoices, planned invoicing (scheduled, recurring and,
when enabled, draft invoices), confirmed sale and purchase orders not yet
invoiced.

The `xpmi.cash.forecast.line` model is rebuilt from scratch on every refresh.
Each line is an expected cash movement, in company currency, positive for money
in and negative for money out.

| Source | Forecast date | Amount |
|---|---|---|
| Bank and cash balance | today | accounting balance of the `asset_cash` accounts posted up to today |
| Open customer and vendor invoices | due date of the single receivable/payable line (`date_maturity`) | residual amount of the line |
| Confirmed sale orders | expected delivery date + payment term | order total minus what is already invoiced |
| Confirmed purchase orders | expected arrival date + payment term | not yet invoiced share of the lines |

Planned invoicing covers draft invoices scheduled for automatic posting (always
included), the future occurrences of periodic invoices (`auto_post` monthly,
quarterly or yearly) that Odoo has not created yet — projected from the last
invoice of the series with Odoo's own date and payment term rules, up to
`auto_post_until` and at most 12 months ahead — and plain draft invoices, only
for companies enabling them in the Accounting settings.

**All amounts are tax included**, because the forecast is about the money that
actually enters and leaves the account. Only the **not yet invoiced** part of an
order is taken: the invoiced part is already covered by the invoice lines, so
nothing is counted twice.

The module adds a spreadsheet dashboard and graph / pivot / list views, both
read only: lines are never created or edited by hand, they are always the result
of a refresh.
