from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_guarantee_count = fields.Integer(compute='_compute_ad_guarantee_count', string='الكفالة')
    ad_pledge_count = fields.Integer(compute='_compute_ad_pledge_count', string='التعهدات')

    def _compute_ad_guarantee_count(self):
        counts = self._ad_count_of('ad.employee.guarantee')
        for emp in self:
            emp.ad_guarantee_count = counts.get(emp.id, 0)

    def action_ad_open_guarantee(self):
        return self._ad_open_forms('ad.employee.guarantee', 'الكفالة')

    def _compute_ad_pledge_count(self):
        counts = self._ad_count_of('ad.employee.pledge')
        for emp in self:
            emp.ad_pledge_count = counts.get(emp.id, 0)

    def action_ad_open_pledge(self):
        return self._ad_open_forms('ad.employee.pledge', 'التعهدات')
