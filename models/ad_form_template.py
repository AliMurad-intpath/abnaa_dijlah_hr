from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AdFormTemplate(models.Model):
    _name = 'ad.form.template'
    _description = 'Document control header'
    _order = 'code'

    name = fields.Char('Form name', required=True)
    code = fields.Char('Doc', required=True, help='Document code printed in the header')
    issue = fields.Char('Issue', default='02')
    issue_date = fields.Char('Issue Date', default='02-01-2024')
    rev_date = fields.Char('Rev. Date', default='00-00-00')
    title_ar = fields.Char('Title in Arabic')
    title_en = fields.Char('Title in English')
    title_layout = fields.Selection(
        [('stack', 'Arabic title with English below'),
         ('inline', 'English and Arabic on one line'),
         ('ar_only', 'Arabic title only')],
        default='stack', required=True, string='Title layout')
    logo = fields.Image('Logo of this form', max_width=800, max_height=800,
                        help='Optional: overrides the company logo for this form only.')
    active = fields.Boolean(default=True, string='Active')

    @api.constrains('code')
    def _check_code_unique(self):
        for rec in self:
            if self.search_count([('code', '=', rec.code), ('id', '!=', rec.id)]):
                raise ValidationError(self.env._('The form code %s already exists.', rec.code))
