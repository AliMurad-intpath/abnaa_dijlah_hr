from odoo import fields, models


class AdWorkSite(models.Model):
    _name = 'ad.work.site'
    _description = 'Work site'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char('Site', required=True, tracking=True)
    code = fields.Char('Code')
    partner_id = fields.Many2one('res.partner', string='Customer')
    governorate = fields.Char('Governorate')
    area = fields.Char('Area')
    supervisor_id = fields.Many2one('hr.employee', string='Current supervisor', tracking=True)
    supervisor_mobile = fields.Char('Supervisor mobile number')
    active = fields.Boolean(default=True, string='Active')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, string='Company')
