def migrate(cr, version):
    """Svuota le previsioni prima di aggiungere i campi di periodo.

    Le righe sono rigenerate dalla post-migrazione: cancellarle prima evita
    che i nuovi campi obbligatori restino a NULL sulle righe vecchie.
    """
    cr.execute("DELETE FROM xpmi_cash_forecast_line")
