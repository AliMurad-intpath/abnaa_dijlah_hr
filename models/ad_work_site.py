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
    visibility_user_ids = fields.Many2many(
        'res.users', 'ad_work_site_user_rel', 'site_id', 'user_id', string='Users limited to this site',
        help='These users see only the forms of the sites they are listed on. A user listed on no site sees every site.')
