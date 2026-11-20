from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_interview_count = fields.Integer(compute='_compute_ad_interview_count', string='Interview')

    def _compute_ad_interview_count(self):
        counts = self._ad_count_of('ad.interview')
        for emp in self:
            emp.ad_interview_count = counts.get(emp.id, 0)

    def action_ad_open_interview(self):
        return self._ad_open_forms('ad.interview', 'Interview')
