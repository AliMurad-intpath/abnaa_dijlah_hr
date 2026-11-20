from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ad_md_name = fields.Char('المدير المفوض (يطبع)', default='مصطفى عبدالمجيد عبدالحميد')
    ad_md_title = fields.Char('عنوان المدير المفوض (يطبع)', default='المدير المفوض')
    ad_license_code = fields.Char('رمز رخصة الشركة الامنية', default='100')
    ad_logo = fields.Image('شعار الطباعة', max_width=800, max_height=800,
                           help='يظهر في ترويسة كل الاستمارات. اذا ترك فارغا يستخدم الشعار الافتراضي.')
    ad_use_approvals = fields.Boolean(
        'سلسلة الموافقات', default=True,
        help='عند التفعيل لا تتم الموافقة النهائية على الاستمارات الا عبر سلسلة الموافقات (زر "ارسال للموافقة"). '
             'عند الايقاف تعمل ازرار الموافقة اليدوية القديمة.')
    ad_reminder_enabled = fields.Boolean('تذكير المعتمدين بالموافقات المعلقة', default=True)
    ad_reminder_after_days = fields.Integer(
        'اول تذكير بعد (ايام)', default=1, help='عدد ايام انتظار الاستمارة قبل اول تذكير للمعتمد.')
    ad_reminder_repeat_days = fields.Integer(
        'تكرار التذكير كل (ايام)', default=1, help='بعد اول تذكير يتكرر كل N يوم حتى يتم القرار.')
    ad_last_summary = fields.Date(copy=False)
    ad_reminder_summary = fields.Boolean(
        'ملخص يومي لمدير الموارد البشرية', default=True,
        help='اشعار يومي واحد لمدراء الموارد البشرية بكل الاستمارات التي ما زالت بانتظار معتمد.')
