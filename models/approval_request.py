import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ApprovalCategory(models.Model):
    _inherit = 'approval.category'

    ad_model = fields.Char('استمارة AD', index=True, help='The Abnaa Dijlah HR form this approval type serves.')
    ad_user_ids = fields.Many2many('res.users', 'ad_approval_category_user_rel', 'category_id', 'user_id',
                                   string='المستخدمون المسموح لهم',
                                   help='اتركها مع المجموعات فارغة لاظهار نوع الموافقة للجميع. '
                                        'اضف المعتمدين هنا ايضا ليتمكنوا من رؤية الطلبات.')
    ad_group_ids = fields.Many2many('res.groups', 'ad_approval_category_group_rel', 'category_id', 'group_id',
                                    string='المجموعات المسموح لها')

    @api.model
    def _search(self, domain, *args, **kwargs):
        """Hide approval types from users who were not allowed them.

        Nothing chosen on a type = visible to everyone. Approvals managers and
        administrators always see every type. (Odoo 20 has no ir.rule, so the
        filter is applied here, on every search / list / dropdown.)"""
        user = self.env.user
        if (not self.env.su and not kwargs.get('bypass_access')
                and not user.has_group('approvals.group_approval_manager')
                and not user.has_group('base.group_system')):
            groups = (user.all_group_ids if 'all_group_ids' in user._fields else user.group_ids).ids
            extra = ['|', '|', '&', ('ad_user_ids', '=', False), ('ad_group_ids', '=', False),
                     ('ad_user_ids', 'in', [user.id]), ('ad_group_ids', 'in', groups)]
            try:
                from odoo.fields import Domain
                domain = Domain(domain) & Domain(extra)
            except ImportError:
                from odoo.osv import expression
                domain = expression.AND([domain, extra])
        return super()._search(domain, *args, **kwargs)


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


class ApprovalApprover(models.Model):
    _inherit = 'approval.approver'

    ad_last_reminder = fields.Datetime('اخر تذكير', copy=False)


class ApprovalRequestReminder(models.Model):
    _inherit = 'approval.request'

    @api.model
    def _cron_ad_remind(self):
        """Remind approvers of requests waiting for them: first after N days, then
        every M days until answered (days are set on the company). Plus one daily
        summary to HR managers. Runs every few hours; the timestamps decide."""
        now = fields.Datetime.now()
        Approver = self.env['approval.approver'].sudo()
        waiting = Approver.search([('status', '=', 'pending')])
        late_rows = {}
        for ap in waiting:
            req = ap.request_id
            if not req or req.request_status != 'pending':
                continue
            company = req.company_id or self.env.company
            if not company.ad_reminder_enabled:
                continue
            after = max(company.ad_reminder_after_days, 1)
            repeat = max(company.ad_reminder_repeat_days, 1)
            since = ap.ad_last_reminder
            due = (since + timedelta(days=repeat)) if since else (ap.write_date + timedelta(days=after))
            if now < due:
                continue
            days = max((now - (req.create_date or now)).days, 1)
            try:
                req.sudo().message_notify(
                    partner_ids=ap.user_id.partner_id.ids,
                    subject=self.env._('تذكير: طلب موافقة بانتظارك'),
                    body=Markup('%s <a href="#" data-oe-model="approval.request" data-oe-id="%s">%s</a> (%s)') % (
                        self.env._('طلب الموافقة بانتظار قرارك منذ %s يوم:', days), req.id, req.display_name,
                        req.category_id.display_name or ''),
                )
                ap.ad_last_reminder = now
                late_rows.setdefault(req.company_id.id or self.env.company.id, []).append((req, ap, days))
            except Exception:
                _logger.exception('approval reminder failed for request %s', req.id)
        self._ad_send_daily_summary(now)

    @api.model
    def _ad_send_daily_summary(self, now):
        param = self.env['ir.config_parameter'].sudo()
        today = str(fields.Date.to_date(now))
        if param.get_param('abnaa_dijlah_hr.last_approval_summary') == today:
            return
        pending = self.sudo().search([('request_status', '=', 'pending')])
        if not pending:
            return
        by_company = {}
        for req in pending:
            company = req.company_id or self.env.company
            if not (company.ad_reminder_enabled and company.ad_reminder_summary):
                continue
            who = ', '.join(req.approver_ids.filtered(lambda a: a.status == 'pending').mapped('user_id.name')) or '-'
            by_company.setdefault(company, []).append(
                Markup('<li><a href="#" data-oe-model="approval.request" data-oe-id="%s">%s</a> — %s</li>') % (
                    req.id, req.display_name, who))
        managers = self.env.ref('hr.group_hr_manager').sudo()
        users = managers.all_user_ids if 'all_user_ids' in managers._fields else managers.user_ids
        for company, rows in by_company.items():
            partners = users.filtered(lambda u: company in u.company_ids).partner_id
            if not partners:
                continue
            body = Markup('<p>%s</p><ul>%s</ul>') % (
                self.env._('طلبات موافقة ما زالت بانتظار المعتمدين: %s', len(rows)), Markup('').join(rows))
            self.env['approval.request'].sudo().message_notify(
                partner_ids=partners.ids, subject=self.env._('ملخص يومي: موافقات معلقة'), body=body)
        param.set_param('abnaa_dijlah_hr.last_approval_summary', today)
