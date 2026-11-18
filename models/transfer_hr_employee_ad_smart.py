from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_transfer_count = fields.Integer(compute='_compute_ad_transfer_count', string='التنقلات')

    def _compute_ad_transfer_count(self):
        counts = self._ad_count_of('ad.transfer')
        for emp in self:
            emp.ad_transfer_count = counts.get(emp.id, 0)

    def action_ad_open_transfer(self):
        return self._ad_open_forms('ad.transfer', 'التنقلات')
