from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    ad_approval_count = fields.Integer('طلبات الموافقة', compute='_compute_ad_approval_count')

    def _compute_ad_approval_count(self):
        data = self.env['approval.request'].sudo()._read_group(
            [('ad_employee_id', 'in', self.ids)], ['ad_employee_id'], ['__count'])
        counts = {emp.id: c for emp, c in data}
        for emp in self:
            emp.ad_approval_count = counts.get(emp.id, 0)

    def action_ad_open_approvals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': 'طلبات الموافقة', 'res_model': 'approval.request',
            'view_mode': 'list,form', 'domain': [('ad_employee_id', '=', self.id)],
        }
