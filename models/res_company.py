from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ad_md_name = fields.Char('Managing director (printed)', default='مصطفى عبدالمجيد عبدالحميد')
    ad_md_title = fields.Char('Managing director title (printed)', default='المدير المفوض')
    ad_license_code = fields.Char('Company security license code', default='100')
    ad_logo = fields.Image('Print logo', max_width=800, max_height=800,
                           help='Shown in the header of all forms. If empty, the default logo is used.')
    ad_use_approvals = fields.Boolean(
        'Approval chain', default=True,
        help='When enabled, final approval of forms is only possible through the approval chain ("Send for approval" button). When disabled, the old manual approval buttons are used.')
    ad_reminder_enabled = fields.Boolean('Remind approvers of pending approvals', default=True)
    ad_reminder_after_days = fields.Integer(
        'First reminder after (days)', default=1, help='Number of days a form waits before the first reminder to the approver.')
    ad_reminder_repeat_days = fields.Integer(
        'Repeat reminder every (days)', default=1, help='After the first reminder, it repeats every N days until a decision is made.')
    ad_last_summary = fields.Date(copy=False)
    ad_reminder_summary = fields.Boolean(
        'Daily summary for the HR manager', default=True,
        help='One daily notification to HR managers listing all forms still awaiting an approver.')
