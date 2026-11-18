from odoo import models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _ad_check(self, args, kwargs):
        ref = kwargs.get('report_ref') or (args[0] if args else None)
        try:
            report = self._get_report(ref) if ref else self
        except Exception:
            return
        if report and report.model and report.model.startswith('ad.') and report.model != 'ad.dashboard':
            self.env['ad.dashboard.block']._check_form_access(report.model)

    def _render_qweb_pdf(self, *args, **kwargs):
        self._ad_check(args, kwargs)
        return super()._render_qweb_pdf(*args, **kwargs)

    def _render_qweb_html(self, *args, **kwargs):
        self._ad_check(args, kwargs)
        return super()._render_qweb_html(*args, **kwargs)
