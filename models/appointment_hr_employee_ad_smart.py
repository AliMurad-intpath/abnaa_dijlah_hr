from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_appointment_count = fields.Integer(compute='_compute_ad_appointment_count', string='أوامر التعيين')

    def _compute_ad_appointment_count(self):
        counts = self._ad_count_of('ad.appointment.order')
        for emp in self:
            emp.ad_appointment_count = counts.get(emp.id, 0)

    def action_ad_open_appointment(self):
        return self._ad_open_forms('ad.appointment.order', 'أوامر التعيين')
