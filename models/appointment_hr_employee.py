from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    ad_nominal_salary = fields.Monetary('Nominal salary', currency_field='ad_currency_id', groups='abnaa_dijlah_hr.group_ad_hr_manager,abnaa_dijlah_hr.group_ad_finance,abnaa_dijlah_hr.group_ad_md')
    ad_site_allowance = fields.Monetary('Work site allowance', currency_field='ad_currency_id', groups='abnaa_dijlah_hr.group_ad_hr_manager,abnaa_dijlah_hr.group_ad_finance,abnaa_dijlah_hr.group_ad_md')
    ad_start_date = fields.Date('Start date', tracking=True)
    ad_probation_end = fields.Date('End of probation period')
