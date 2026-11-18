from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def _ad_count_of(self, model_name):
        """{employee_id: number of AD forms of `model_name`} in one query."""
        data = self.env[model_name]._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        return {emp.id: count for emp, count in data}

    def _ad_open_forms(self, model_name, title):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
