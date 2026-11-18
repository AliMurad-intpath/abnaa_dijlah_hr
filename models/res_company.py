from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ad_md_name = fields.Char('المدير المفوض (يطبع)', default='مصطفى عبدالمجيد عبدالحميد')
    ad_md_title = fields.Char('عنوان المدير المفوض (يطبع)', default='المدير المفوض')
    ad_license_code = fields.Char('رمز رخصة الشركة الامنية', default='100')
    ad_logo = fields.Image('شعار الطباعة', max_width=800, max_height=800,
                           help='يظهر في ترويسة كل الاستمارات. اذا ترك فارغا يستخدم الشعار الافتراضي.')
