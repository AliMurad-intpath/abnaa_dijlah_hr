from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ad_use_approvals = fields.Boolean(
        'الموافقة النهائية عبر تطبيق الموافقات', default=False,
        help='When on, the final approval of the HR forms can only be given through an approval request '
             '(button "طلب موافقة"); the manual final-approval buttons are refused.')

    ad_reminder_enabled = fields.Boolean('تذكير المعتمدين بالموافقات المعلقة', default=True)
    ad_reminder_after_days = fields.Integer(
        'اول تذكير بعد (ايام)', default=1,
        help='Days a request waits for an approver before the first reminder.')
    ad_reminder_repeat_days = fields.Integer(
        'تكرار التذكير كل (ايام)', default=1,
        help='After the first reminder, repeat every N days until the request is answered.')
    ad_reminder_summary = fields.Boolean(
        'ملخص يومي لمدير الموارد البشرية', default=True,
        help='Send HR managers one daily notification listing every request still waiting for an approver.')
