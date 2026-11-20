from odoo import fields, models


class AdEmployeePledge(models.Model):
    """FM-17: written pledges for protection staff."""
    _name = 'ad.employee.pledge'
    _description = 'Written pledges for security personnel (AD-HR-FM-17)'
    _inherit = ['mail.thread', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_pledge'

    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='Employee')
    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    employee_phone = fields.Char(related='employee_id.mobile_phone', string='Employee phone number', readonly=False)
    employee_address = fields.Char(related='employee_id.ad_address', string='Employee address')
    guarantor_name = fields.Char('Guarantor')
    guarantor_phone = fields.Char('Guarantor phone number')
    guarantor_address = fields.Char('Guarantor address')
    guarantor_date = fields.Date('Guarantee date', default=fields.Date.context_today)
    state = fields.Selection([('draft', 'Draft'), ('signed', 'Signed')], default='draft', tracking=True, string='Status')

    def action_signed(self):
        self.write({'state': 'signed'})
        self.ad_sign('hr')

    def action_draft(self):
        self.write({'state': 'draft'})
