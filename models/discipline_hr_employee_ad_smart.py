from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_discipline_count = fields.Integer(compute='_compute_ad_discipline_count', string='العقوبات')

    def _compute_ad_discipline_count(self):
        counts = self._ad_count_of('ad.discipline')
        for emp in self:
            emp.ad_discipline_count = counts.get(emp.id, 0)

    def action_ad_open_discipline(self):
        return self._ad_open_forms('ad.discipline', 'العقوبات')
