from odoo import fields, models


class AdViolationType(models.Model):
    _name = 'ad.violation.type'
    _description = 'نوع المخالفة'
    _order = 'number'

    number = fields.Integer(required=True, string='الرقم')
    name = fields.Char('المخالفة', required=True, translate=True)
    active = fields.Boolean(default=True, string='نشط')
