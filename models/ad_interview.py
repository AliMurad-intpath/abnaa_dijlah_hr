from odoo import api, fields, models

CRITERIA = [
    ('1', 'التعليم والمؤهلات المهنية', 'طريقة القياس: وثائق ثبوتية لتأكيد مستوى التعليم والمؤهلات'),
    ('2', 'الخبرة العملية', 'طريقة القياس: وثائق مرجعية من أماكن العمل السابقة'),
    ('3', 'مهارات قيادة العجلات', 'طريقة القياس: وثيقة ثبوتية ( إجازة السوق)'),
    ('4', 'المظهر والانضباط العام', 'طريقة القياس: ملاحظة مباشرة (ان يكون الهندام مناسب)'),
    ('5', 'اللياقة البدنية والتحمل', 'طريقة القياس: اختبارات ميدانية بسيطة (جري، تمرين ضغط، حمل اوزان)'),
    ('6', 'الثبات الانفعالي وضبط النفس', 'طريقة القياس: طرح مجموعة من الأسئلة السلوكية'),
    ('7', 'الوعي الأمني والملاحظة', 'طريقة القياس: عرض صورة او فديو ومن ثم طرح مجموعة من الأسئلة'),
]
LEVELS = [('excellent', 'ممتاز'), ('very_good', 'جيد جدا'), ('good', 'جيد'), ('weak', 'ضعيف'), ('very_weak', 'ضعيف جدا')]
YESNO = [('yes', 'نعم'), ('no', 'كلا')]
PASSFAIL = [('pass', 'اجتياز'), ('fail', 'اخفاق')]


class AdInterview(models.Model):
    """Interview rating form AD-WI-FM-06-01 (استمارة تقييم المقابلة) - 5 pages."""
    _name = 'ad.interview'
    _description = 'استمارة تقييم المقابلة'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.interview'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_interview'

    date = fields.Date(default=fields.Date.context_today, required=True, string='التاريخ')
    applicant_id = fields.Many2one('hr.applicant', string='سجل المتقدم')
    employee_id = fields.Many2one('hr.employee', string='الموظف المنشأ', readonly=True, copy=False)
    candidate_name = fields.Char('اسم المرشح', required=True, tracking=True)
    birth_date = fields.Date('تاريخ الميلاد')
    phone = fields.Char('رقم الهاتف')
    governorate = fields.Char('المحافظة')
    area = fields.Char('الناحية')
    district = fields.Char('الحي')
    interview_date = fields.Date('تاريخ المقابلة', default=fields.Date.context_today)
    job_title = fields.Char('المسمى الوظيفي')
    referral = fields.Char('اسم جهة الترشيح')
    score_ids = fields.One2many('ad.interview.score', 'interview_id', string='الدرجات', copy=True)
    overall_score = fields.Float('درجة التقييم العام', compute='_compute_overall', store=True, digits=(4, 1))
    ar_read = fields.Selection(LEVELS, 'اتقان العربية - قراءة')
    ar_write = fields.Selection(LEVELS, 'اتقان العربية - كتابة')
    ar_speak = fields.Selection(LEVELS, 'اتقان العربية - محادثة')
    en_read = fields.Selection(LEVELS, 'اتقان الانكليزية - قراءة')
    en_write = fields.Selection(LEVELS, 'اتقان الانكليزية - كتابة')
    en_speak = fields.Selection(LEVELS, 'اتقان الانكليزية - محادثة')
    # health assessment
    health_general = fields.Selection(LEVELS, 'الوضع الصحي العام')
    weight = fields.Char('الوزن')
    height = fields.Char('الطول')
    chronic_diseases = fields.Text('الامراض المزمنة والمعدية')
    surgery_ids = fields.One2many('ad.interview.surgery', 'interview_id', string='العمليات الجراحية السابقة')
    q_medication = fields.Selection(YESNO, 'يتعاطى ادوية او عقاقير بشكل دوري')
    q_tattoo = fields.Selection(YESNO, 'وشم على جزء ظاهر من الجسم')
    q_planned_surgery = fields.Selection(YESNO, 'علاج او عمليات جراحية مخطط لها')
    q_care_program = fields.Selection(YESNO, 'يخضع لبرنامج رعاية')
    # security assessment
    q_party = fields.Selection(YESNO, 'صلة بالميليشيات او تنظيمات او احزاب')
    q_convicted = fields.Selection(YESNO, 'محكوم بجريمة او جنحة او جناية')
    q_pending_case = fields.Selection(YESNO, 'قضايا منظورة في المحاكم')
    reference_ids = fields.One2many('ad.interview.reference', 'interview_id', string='المعرّفون')
    # training
    t_weapon = fields.Selection(PASSFAIL, 'تدريب السلاح')
    t_force_law = fields.Selection(PASSFAIL, 'قانون استخدام القوة')
    t_armed_conflict = fields.Selection(PASSFAIL, 'قانون النزاع المسلح')
    t_search = fields.Selection(PASSFAIL, 'تفتيش الاشخاص والعجلات')
    # recommendation
    recommendation = fields.Selection([('hire', 'تعيين المرشح'), ('reject', 'عدم تعيين المرشح'), ('withdraw', 'انسحاب المرشح')],
                                      tracking=True, string='التوصية')
    w_salary = fields.Boolean('الراتب منخفض جدا')
    w_duties = fields.Boolean('الواجبات الوظيفية')
    w_hours = fields.Boolean('ساعات العمل')
    w_other_job = fields.Boolean('وظيفة أخرى')
    w_mind = fields.Boolean('تغير الرأي')
    w_other = fields.Char('سبب آخر للانسحاب')
    r_qualif = fields.Boolean('المؤهلات والجدارات دون المتطلبات')
    r_health = fields.Boolean('اخفاق في التقييم الصحي')
    r_security = fields.Boolean('اخفاق في التقييم الامني')
    r_training = fields.Boolean('عدم اجتياز التدريب الأمني')
    r_other = fields.Char('سبب آخر لعدم التعيين')
    ack_date = fields.Date('تاريخ الإقرار')
    state = fields.Selection([
        ('draft', 'مسودة'), ('hr', 'مقابلة الموارد البشرية'), ('ops', 'العمليات / التدريب'),
        ('done', 'التوصية النهائية'), ('cancel', 'ملغاة'),
    ], default='draft', tracking=True, copy=False, string='الحالة')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.score_ids:
                rec.score_ids = [(0, 0, {'sequence': int(n), 'criterion': n}) for n, _t, _m in CRITERIA]
        return records

    @api.depends('score_ids.score')
    def _compute_overall(self):
        for rec in self:
            scored = rec.score_ids.filtered(lambda s: s.score)
            rec.overall_score = sum(scored.mapped('score')) / len(scored) if scored else 0.0

    @api.onchange('applicant_id')
    def _onchange_applicant_id(self):
        app = self.applicant_id
        if app:
            self.candidate_name = getattr(app, 'partner_name', False) or app.display_name
            self.phone = getattr(app, 'partner_phone', False) or getattr(app, 'phone', False) or self.phone
            self.job_title = app.job_id.name if app.job_id else self.job_title

    def action_hr(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        self.write({'state': 'hr'}); self.ad_sign('hr')

    def action_ops(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_ops_manager')
        self.write({'state': 'ops'}); self.ad_sign('ops')

    def action_done(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self._ad_before_final()
        self.write({'state': 'done'}); self.ad_sign('hr_manager')

    def action_create_employee(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        for rec in self:
            if not rec.employee_id:
                rec.employee_id = self.env['hr.employee'].create({
                    'name': rec.candidate_name, 'mobile_phone': rec.phone, 'job_title': rec.job_title,
                    'birthday': rec.birth_date,
                })
        return {'type': 'ir.actions.act_window', 'res_model': 'hr.employee', 'view_mode': 'form', 'res_id': self.employee_id.id}

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})


class AdInterviewScore(models.Model):
    _name = 'ad.interview.score'
    _description = 'درجة تقييم المقابلة'
    _order = 'sequence, id'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='استمارة المقابلة')
    sequence = fields.Integer(default=10, string='التسلسل')
    criterion = fields.Selection([(n, t) for n, t, _m in CRITERIA], required=True, string='المعيار')
    score = fields.Integer('الدرجة (0-10)')
    comments = fields.Char('التعليقات')

    @api.constrains('score')
    def _check_score(self):
        from odoo.exceptions import ValidationError
        for rec in self:
            if not 0 <= rec.score <= 10:
                raise ValidationError(self.env._('يجب أن تكون الدرجات بين 0 و 10.'))


class AdInterviewSurgery(models.Model):
    _name = 'ad.interview.surgery'
    _description = 'عملية جراحية (المقابلة)'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='استمارة المقابلة')
    name = fields.Char('نوع العملية', required=True)
    date = fields.Date('التاريخ')


class AdInterviewReference(models.Model):
    _name = 'ad.interview.reference'
    _description = 'معرّف (المقابلة)'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='استمارة المقابلة')
    name = fields.Char('اسم المعرف', required=True)
    relation = fields.Char('العلاقة')
    phone = fields.Char('رقم الهاتف')
