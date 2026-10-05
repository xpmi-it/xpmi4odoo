from odoo import http
from odoo.http import request

from odoo.addons.spreadsheet_dashboard.controllers.dashboards_controllers import (
    DashboardDataRoute,
)


class CashForecastDashboardRoute(DashboardDataRoute):

    @http.route(readonly=False)
    def get_dashboard_data(self, dashboard):
        """Aggiorna le previsioni prima di servire la dashboard di cassa.

        La rotta di origine è in sola lettura: la si riapre in scrittura perché
        la dashboard legga sempre documenti aggiornati e non l'ultimo giro di
        cron.
        """
        forecast_dashboard = request.env.ref(
            "xpmi_cash_forecast.spreadsheet_dashboard_cash_forecast",
            raise_if_not_found=False,
        )
        if forecast_dashboard and dashboard == forecast_dashboard:
            request.env["xpmi.cash.forecast.line"]._refresh_forecast_if_stale()
        return super().get_dashboard_data(dashboard)
