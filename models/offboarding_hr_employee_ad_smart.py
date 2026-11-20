from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_termination_count = fields.Integer(compute='_compute_ad_termination_count', string='Termination orders')
    ad_clearance_count = fields.Integer(compute='_compute_ad_clearance_count', string='Clearance')

    def _compute_ad_termination_count(self):
        counts = self._ad_count_of('ad.termination.order')
        for emp in self:
            emp.ad_termination_count = counts.get(emp.id, 0)

    def action_ad_open_termination(self):
        return self._ad_open_forms('ad.termination.order', 'Termination orders')

    def _compute_ad_clearance_count(self):
        counts = self._ad_count_of('ad.clearance')
        for emp in self:
            emp.ad_clearance_count = counts.get(emp.id, 0)

    def action_ad_open_clearance(self):
        return self._ad_open_forms('ad.clearance', 'Clearance')
