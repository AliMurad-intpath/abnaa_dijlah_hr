from odoo import fields, models


class AdEmployeePledge(models.Model):
    """FM-17: written pledges for protection staff."""
    _name = 'ad.employee.pledge'
    _description = 'التعهدات الخطية لعناصر الحماية (AD-HR-FM-17)'
    _inherit = ['mail.thread', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_pledge'

    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='الموظف')
    date = fields.Date(default=fields.Date.context_today, required=True, string='التاريخ')
    employee_phone = fields.Char(related='employee_id.mobile_phone', string='رقم هاتف الموظف', readonly=False)
    employee_address = fields.Char(related='employee_id.ad_address', string='عنوان الموظف')
    guarantor_name = fields.Char('الكفيل')
    guarantor_phone = fields.Char('رقم هاتف الكفيل')
    guarantor_address = fields.Char('عنوان الكفيل')
    guarantor_date = fields.Date('تاريخ الكفالة', default=fields.Date.context_today)
    state = fields.Selection([('draft', 'مسودة'), ('signed', 'موقّع')], default='draft', tracking=True, string='الحالة')

    def action_signed(self):
        self.write({'state': 'signed'})
        self.ad_sign('hr')

    def action_draft(self):
        self.write({'state': 'draft'})
