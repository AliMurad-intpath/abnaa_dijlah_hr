from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AdFormTemplate(models.Model):
    _name = 'ad.form.template'
    _description = 'ترويسة ضبط الوثيقة'
    _order = 'code'

    name = fields.Char('اسم الاستمارة', required=True)
    code = fields.Char('Doc', required=True, help='Document code printed in the header')
    issue = fields.Char('Issue', default='02')
    issue_date = fields.Char('Issue Date', default='02-01-2024')
    rev_date = fields.Char('Rev. Date', default='00-00-00')
    title_ar = fields.Char('العنوان بالعربية')
    title_en = fields.Char('العنوان بالانكليزية')
    title_layout = fields.Selection(
        [('stack', 'العنوان العربي وتحته الانكليزي'),
         ('inline', 'الانكليزي والعربي في سطر واحد'),
         ('ar_only', 'العنوان العربي فقط')],
        default='stack', required=True, string='تنسيق العنوان')
    logo = fields.Image('شعار هذه الاستمارة', max_width=800, max_height=800,
                        help='اختياري: يغلب شعار الشركة لهذه الاستمارة فقط.')
    active = fields.Boolean(default=True, string='نشط')

    @api.constrains('code')
    def _check_code_unique(self):
        for rec in self:
            if self.search_count([('code', '=', rec.code), ('id', '!=', rec.id)]):
                raise ValidationError(self.env._('رمز الاستمارة %s موجود مسبقا.', rec.code))
