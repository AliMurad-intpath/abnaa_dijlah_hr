from odoo import fields, models


class AdViolationType(models.Model):
    _name = 'ad.violation.type'
    _description = 'Violation type'
    _order = 'number'

    number = fields.Integer(required=True, string='No.')
    name = fields.Char('Violation', required=True, translate=True)
    active = fields.Boolean(default=True, string='Active')
