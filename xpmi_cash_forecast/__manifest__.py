# -*- coding: utf-8 -*-
{
    "name": "XPMI Cash Forecast",
    "summary": "Previsioni di cassa da fatture aperte, ricorrenti e ordini confermati",
    "version": "19.0.1.5.0",
    "development_status": "Beta",
    "category": "Accounting/Accounting",
    "license": "LGPL-3",
    "author": "XPMI srls",
    "website": "https://www.xpmi.it/",
    "maintainers": ["mcalcagni"],
    "depends": [
        "account",
        "sale",
        "purchase",
        "spreadsheet_dashboard",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/cash_forecast_security.xml",
        "data/ir_cron.xml",
        "data/dashboards.xml",
        "views/cash_forecast_views.xml",
        "views/cash_forecast_projection_views.xml",
        "views/res_config_settings_views.xml",
        "views/xpmi_cash_forecast_menus.xml",
    ],
    "assets": {
        # bundle caricato con lo spreadsheet: è dove vive l'azione dashboard
        "spreadsheet.o_spreadsheet": [
            "xpmi_cash_forecast/static/src/dashboard_refresh_button.js",
            "xpmi_cash_forecast/static/src/dashboard_refresh_button.xml",
        ],
    },
    "post_init_hook": "post_init_hook",
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": False,
    "auto_install": False,
}
