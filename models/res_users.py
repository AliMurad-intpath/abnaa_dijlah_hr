from odoo import fields, models


class ResUsers(models.Model):
    _inherit = 'res.users'

    ad_site_ids = fields.Many2many('ad.work.site', 'ad_work_site_user_rel', 'user_id', 'site_id', string='Visible work sites',
                                   help='Empty = the user sees the forms of every site.')
