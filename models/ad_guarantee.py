from odoo import api, fields, models


class AdEmployeeGuarantee(models.Model):
    """Annex AD-HR-FM-Annex: Employment Guarantee (كفالة) + Written pledge (تعهد خطي)."""
    _name = 'ad.employee.guarantee'
    _description = 'كفالة وتعهد خطي (ملحق)'
    _inherit = ['mail.thread', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_annex'

    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='الموظف')
    date = fields.Date(default=fields.Date.context_today, required=True, string='التاريخ')
    capacity = fields.Char('بصفة', compute='_compute_capacity', store=True, readonly=False)
    guarantor_name = fields.Char('الكفيل', required=True)
    guarantor_phone = fields.Char('رقم هاتف الكفيل')
    guarantor_address = fields.Char('عنوان الكفيل')
    witness1 = fields.Char('الشاهد الاول')
    witness2 = fields.Char('الشاهد الثاني')
    legal_advisor = fields.Char('المشاور القانوني')
    pledge_company = fields.Char('اسم الشركة في التعهد', default="شركة أبناء دجلة لخدمات الامن والحماية المحدودة")
    state = fields.Selection([('draft', 'مسودة'), ('signed', 'موقّع ومختوم')], default='draft', tracking=True, string='الحالة')

    @api.depends('employee_id')
    def _compute_capacity(self):
        for rec in self:
            rec.capacity = rec.employee_id.job_title or rec.employee_id.job_id.name or False

    def action_signed(self):
        self.write({'state': 'signed'})
        self.ad_sign('hr')

    def action_draft(self):
        self.write({'state': 'draft'})
