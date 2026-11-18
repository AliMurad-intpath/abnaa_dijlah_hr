from odoo import fields, models


class AdWorkSite(models.Model):
    _name = 'ad.work.site'
    _description = 'موقع عمل'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('الموقع', required=True, tracking=True)
    code = fields.Char('الرمز')
    partner_id = fields.Many2one('res.partner', string='الزبون')
    governorate = fields.Char('المحافظة')
    area = fields.Char('المنطقة')
    supervisor_id = fields.Many2one('hr.employee', string='المشرف الحالي', tracking=True)
    supervisor_mobile = fields.Char('رقم موبايل المشرف')
    active = fields.Boolean(default=True, string='نشط')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, string='الشركة')
