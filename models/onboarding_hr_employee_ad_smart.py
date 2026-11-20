from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_onboarding_count = fields.Integer(compute='_compute_ad_onboarding_count', string='Start of work')

    def _compute_ad_onboarding_count(self):
        counts = self._ad_count_of('ad.onboarding')
        for emp in self:
            emp.ad_onboarding_count = counts.get(emp.id, 0)

    def action_ad_open_onboarding(self):
        return self._ad_open_forms('ad.onboarding', 'Start of work')
