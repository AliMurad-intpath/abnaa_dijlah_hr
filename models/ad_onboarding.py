from odoo import fields, models


class AdOnboarding(models.Model):
    """Effective Date Notice AD-WI-FM-06-03 (استمارة تاريخ مباشرة العمل)."""
    _name = 'ad.onboarding'
    _description = 'استمارة تاريخ مباشرة العمل'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.onboarding'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_onboarding'

    date = fields.Date(default=fields.Date.context_today, required=True, string='التاريخ')
    employee_id = fields.Many2one('hr.employee', string='اسم الموظف', required=True, tracking=True)
    appointment_id = fields.Many2one('ad.appointment.order', string='رقم امر التعيين',
                                     domain="[('employee_id', '=', employee_id)]")
    site_id = fields.Many2one('ad.work.site', string='موقع العمل')
    start_date = fields.Date('تاريخ المباشرة', tracking=True)
    start_shift = fields.Selection([('am', 'قبل الظهر (ق.ظ)'), ('pm', 'بعد الظهر (ب.ظ)')], string='الفترة (ق.ظ / ب.ظ)', default='am')
    supervisor_name = fields.Char('اسم المشرف')
    supervisor_mobile = fields.Char('رقم الموبايل')
    # HR stage
    medical_done = fields.Boolean('فحص طبي')
    medical_letter = fields.Char('رقم الكتاب')
    salary_done = fields.Boolean('توطين راتب')
    salary_letter = fields.Char('رقم الكتاب ')
    auth_done = fields.Boolean('كتاب تخويل')
    auth_letter = fields.Char('رقم الكتاب  ')
    # Logistics stage
    issue_date = fields.Date('تاريخ تجهيز الموظف بالمواد')
    shirt_size = fields.Char('قميص')
    trouser_size = fields.Char('بنطرون')
    shoe_size = fields.Char('حذاء')
    has_pouch = fields.Boolean('جعبة')
    other_items = fields.Char('أخرى')
    # Operations stage confirmations
    ops_medical = fields.Boolean('العمليات تؤيد استلام الفحص الطبي')
    ops_salary = fields.Boolean('العمليات تؤيد استلام توطين الراتب')
    ops_auth = fields.Boolean('العمليات تؤيد استلام التخويل')
    training_done = fields.Boolean('تم استيفاء التدريب')
    trainer_name = fields.Char('المدرب')
    state = fields.Selection([
        ('draft', 'مسودة'), ('hr', 'اكتمل قسم الموارد البشرية'), ('logistics', 'تم تجهيز الموظف'),
        ('site', 'مشرف الموقع'), ('ops', 'العمليات'), ('done', 'معتمد من المدير المفوض'), ('cancel', 'ملغاة'),
    ], default='draft', tracking=True, copy=False, string='الحالة')

    def action_hr(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        self.write({'state': 'hr'}); self.ad_sign('hr')

    def action_logistics(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_logistics')
        self.write({'state': 'logistics'}); self.ad_sign('logistics')

    def action_site(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_site_supervisor')
        self.write({'state': 'site'}); self.ad_sign('site')

    def action_ops(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_ops_manager')
        self.write({'state': 'ops'}); self.ad_sign('ops')

    def action_done(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_md')
        self._ad_before_final()
        for rec in self:
            rec.write({'state': 'done'}); rec.ad_sign('md')
            emp = rec.employee_id.sudo()
            vals = {}
            if rec.start_date:
                vals['ad_start_date'] = rec.start_date
            if rec.site_id:
                vals['ad_work_site_id'] = rec.site_id.id
            emp.write(vals)

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})
