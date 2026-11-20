from odoo import api, fields, models


class AdEmployeeGuarantee(models.Model):
    """Annex AD-HR-FM-Annex: Employment Guarantee (كفالة) + Written pledge (تعهد خطي)."""
    _name = 'ad.employee.guarantee'
    _description = 'Guarantee and written pledge (annex)'
    _inherit = ['mail.thread', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_annex'

    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='Employee')
    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    capacity = fields.Char('In the capacity of', compute='_compute_capacity', store=True, readonly=False)
    guarantor_name = fields.Char('Guarantor', required=True)
    guarantor_phone = fields.Char('Guarantor phone number')
    guarantor_address = fields.Char('Guarantor address')
    witness1 = fields.Char('First witness')
    witness2 = fields.Char('Second witness')
    legal_advisor = fields.Char('Legal advisor')
    pledge_company = fields.Char('Company name in the pledge', default="شركة أبناء دجلة لخدمات الامن والحماية المحدودة")
    state = fields.Selection([('draft', 'Draft'), ('signed', 'Signed and stamped')], default='draft', tracking=True, string='Status')

    @api.depends('employee_id')
    def _compute_capacity(self):
        for rec in self:
            rec.capacity = rec.employee_id.job_title or rec.employee_id.job_id.name or False

    def action_signed(self):
        self.write({'state': 'signed'})
        self.ad_sign('hr')

    def action_draft(self):
        self.write({'state': 'draft'})
