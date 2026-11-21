from odoo import fields, models
from odoo.exceptions import UserError


class AdFormRejectWizard(models.TransientModel):
    _name = 'ad.form.reject.wizard'
    _description = 'Reject form'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    step_name = fields.Char('Stage', readonly=True)
    note = fields.Text('Rejection reason', required=True)
    mode = fields.Selection([('reject', 'Reject'), ('back', 'Send back')], default='reject', required=True)

    def action_confirm(self):
        self.ensure_one()
        if self.res_model not in self.env or not hasattr(self.env[self.res_model], '_ad_do_reject'):
            raise UserError(self.env._('Invalid form.'))
        record = self.env[self.res_model].browse(self.res_id)
        if self.mode == 'back':
            record._ad_do_send_back(self.note)
        else:
            record._ad_do_reject(self.note)
        return {'type': 'ir.actions.client', 'tag': 'soft_reload'}
