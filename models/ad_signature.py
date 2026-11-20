from odoo import fields, models


class AdSignature(models.Model):
    """Approval stamp of one step of one form (who approved and when)."""
    _name = 'ad.signature'
    _description = 'Form approval stamp'
    _order = 'id'

    res_model = fields.Char(required=True, index=True, string='Record model')
    res_id = fields.Many2oneReference(model_field='res_model', required=True, index=True, string='Record ID')
    step = fields.Char(required=True, string='Step')
    user_id = fields.Many2one('res.users', string='Approved by', required=True)
    date = fields.Date(required=True, string='Date')
    note = fields.Char(string='Note')
