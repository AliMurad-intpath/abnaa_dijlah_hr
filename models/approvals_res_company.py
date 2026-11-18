from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ad_use_approvals = fields.Boolean(
        'الموافقة النهائية عبر تطبيق الموافقات', default=False,
        help='When on, the final approval of the HR forms can only be given through an approval request '
             '(button "طلب موافقة"); the manual final-approval buttons are refused.')
