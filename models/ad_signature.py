from odoo import fields, models


class AdSignature(models.Model):
    """Approval stamp of one step of one form (who approved and when)."""
    _name = 'ad.signature'
    _description = 'ختم موافقة الاستمارة'
    _order = 'id'

    res_model = fields.Char(required=True, index=True, string='نموذج السجل')
    res_id = fields.Many2oneReference(model_field='res_model', required=True, index=True, string='معرف السجل')
    step = fields.Char(required=True, string='الخطوة')
    user_id = fields.Many2one('res.users', string='اعتمد بواسطة', required=True)
    date = fields.Date(required=True, string='التاريخ')
    note = fields.Char(string='ملاحظة')
