import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ApprovalCategory(models.Model):
    _inherit = 'approval.category'

    ad_model = fields.Char('استمارة AD', index=True, help='The Abnaa Dijlah HR form this approval type serves.')


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    ad_res_model = fields.Char('نموذج الاستمارة', index=True, copy=False)
    ad_res_id = fields.Integer('رقم الاستمارة', index=True, copy=False)
    ad_employee_id = fields.Many2one('hr.employee', 'الموظف (استمارة AD)', copy=False, index=True)
    ad_synced = fields.Boolean('تمت المزامنة مع الاستمارة', copy=False)

    def _ad_sync(self):
        """Apply the final outcome of the request on the linked HR form (once)."""
        for request in self.filtered(lambda r: r.ad_res_model and not r.ad_synced):
            status = request.request_status
            if status not in ('approved', 'refused', 'cancel'):
                continue
            record = self.env[request.ad_res_model].sudo().browse(request.ad_res_id).exists()
            if record and record.ad_approval_request_id == request:
                if status == 'approved':
                    record._ad_apply_approved(request)
                else:
                    record._ad_apply_refused(request)
            request.sudo().ad_synced = True

    def action_approve(self, *args, **kwargs):
        res = super().action_approve(*args, **kwargs)
        self._ad_sync()
        return res

    def action_refuse(self, *args, **kwargs):
        res = super().action_refuse(*args, **kwargs)
        self._ad_sync()
        return res

    def action_cancel(self, *args, **kwargs):
        res = super().action_cancel(*args, **kwargs)
        self._ad_sync()
        return res

    def action_withdraw(self, *args, **kwargs):
        res = super().action_withdraw(*args, **kwargs)
        self._ad_sync()
        return res

    @api.model
    def _cron_ad_sync(self):
        """Safety net: catches outcomes that did not go through the buttons above."""
        todo = self.sudo().search([('ad_res_model', '!=', False), ('ad_synced', '=', False),
                                   ('request_status', 'in', ['approved', 'refused', 'cancel'])])
        for request in todo:
            try:
                with self.env.cr.savepoint():
                    request._ad_sync()
            except Exception:
                _logger.exception('Approval request %s could not be applied to its HR form', request.id)
