from odoo import api, fields, models

CRITERIA = [
    ('1', 'Education and professional qualifications', 'Measured by: supporting documents confirming education and qualifications'),
    ('2', 'Work experience', 'Measured by: reference documents from previous workplaces'),
    ('3', 'Vehicle driving skills', 'Measured by: supporting document (driving license)'),
    ('4', 'Appearance and general discipline', 'Measured by: direct observation (appropriate attire)'),
    ('5', 'Physical fitness and endurance', 'Measured by: simple field tests (running, push-ups, carrying weights)'),
    ('6', 'Emotional stability and self-control', 'Measured by: a set of behavioral questions'),
    ('7', 'Security awareness and observation', 'Measured by: showing a picture or video and then asking a set of questions'),
]
LEVELS = [('excellent', 'Excellent'), ('very_good', 'Very good'), ('good', 'Good'), ('weak', 'Weak'), ('very_weak', 'Very weak')]
YESNO = [('yes', 'Yes'), ('no', 'No')]
PASSFAIL = [('pass', 'Pass'), ('fail', 'Fail')]


class AdInterview(models.Model):
    """Interview rating form AD-WI-FM-06-01 (استمارة تقييم المقابلة) - 5 pages."""
    _name = 'ad.interview'
    _description = 'Interview rating form'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.interview'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_interview'

    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    applicant_id = fields.Many2one('hr.applicant', string='Applicant record')
    employee_id = fields.Many2one('hr.employee', string='Created employee', readonly=True, copy=False)
    candidate_name = fields.Char('Candidate name', required=True, tracking=True)
    birth_date = fields.Date('Date of birth')
    phone = fields.Char('Phone number')
    governorate = fields.Char('Governorate')
    area = fields.Char('Sub-district')
    district = fields.Char('Neighborhood')
    interview_date = fields.Date('Interview date', default=fields.Date.context_today)
    job_title = fields.Char('Job title')
    referral = fields.Char('Referring party name')
    score_ids = fields.One2many('ad.interview.score', 'interview_id', string='Scores', copy=True)
    overall_score = fields.Float('Overall rating score', compute='_compute_overall', store=True, digits=(4, 1))
    ar_read = fields.Selection(LEVELS, 'Arabic proficiency - reading')
    ar_write = fields.Selection(LEVELS, 'Arabic proficiency - writing')
    ar_speak = fields.Selection(LEVELS, 'Arabic proficiency - speaking')
    en_read = fields.Selection(LEVELS, 'English proficiency - reading')
    en_write = fields.Selection(LEVELS, 'English proficiency - writing')
    en_speak = fields.Selection(LEVELS, 'English proficiency - speaking')
    # health assessment
    health_general = fields.Selection(LEVELS, 'General health condition')
    weight = fields.Char('Weight')
    height = fields.Char('Height')
    chronic_diseases = fields.Text('Chronic and infectious diseases')
    surgery_ids = fields.One2many('ad.interview.surgery', 'interview_id', string='Previous surgeries')
    q_medication = fields.Selection(YESNO, 'Regularly takes medication or drugs')
    q_tattoo = fields.Selection(YESNO, 'Tattoo on a visible part of the body')
    q_planned_surgery = fields.Selection(YESNO, 'Planned treatment or surgery')
    q_care_program = fields.Selection(YESNO, 'Under a care program')
    # security assessment
    q_party = fields.Selection(YESNO, 'Links to militias, organizations or parties')
    q_convicted = fields.Selection(YESNO, 'Convicted of a misdemeanor or felony')
    q_pending_case = fields.Selection(YESNO, 'Cases pending in court')
    reference_ids = fields.One2many('ad.interview.reference', 'interview_id', string='References')
    # training
    t_weapon = fields.Selection(PASSFAIL, 'Weapons training')
    t_force_law = fields.Selection(PASSFAIL, 'Use of force law')
    t_armed_conflict = fields.Selection(PASSFAIL, 'Armed conflict law')
    t_search = fields.Selection(PASSFAIL, 'Searching persons and vehicles')
    # recommendation
    recommendation = fields.Selection([('hire', 'Hire the candidate'), ('reject', 'Do not hire the candidate'), ('withdraw', 'Candidate withdrew')],
                                      tracking=True, string='Recommendation')
    w_salary = fields.Boolean('Salary too low')
    w_duties = fields.Boolean('Job duties')
    w_hours = fields.Boolean('Working hours')
    w_other_job = fields.Boolean('Another job')
    w_mind = fields.Boolean('Changed mind')
    w_other = fields.Char('Other reason for withdrawal')
    r_qualif = fields.Boolean('Qualifications and competencies below requirements')
    r_health = fields.Boolean('Failed the health assessment')
    r_security = fields.Boolean('Failed the security assessment')
    r_training = fields.Boolean('Did not pass security training')
    r_other = fields.Char('Other reason for not hiring')
    ack_date = fields.Date('Declaration date')
    state = fields.Selection([
        ('draft', 'Draft'), ('hr', 'HR interview'), ('ops', 'Operations / training'),
        ('done', 'Final recommendation'), ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False, string='Status')

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
    _description = 'Interview rating score'
    _order = 'sequence, id'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='Interview form')
    sequence = fields.Integer(default=10, string='Sequence')
    criterion = fields.Selection([(n, t) for n, t, _m in CRITERIA], required=True, string='Criterion')
    score = fields.Integer('Score (0-10)')
    comments = fields.Char('Comments')

    @api.constrains('score')
    def _check_score(self):
        from odoo.exceptions import ValidationError
        for rec in self:
            if not 0 <= rec.score <= 10:
                raise ValidationError(self.env._('Scores must be between 0 and 10.'))


class AdInterviewSurgery(models.Model):
    _name = 'ad.interview.surgery'
    _description = 'Surgery (interview)'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='Interview form')
    name = fields.Char('Operation type', required=True)
    date = fields.Date('Date')


class AdInterviewReference(models.Model):
    _name = 'ad.interview.reference'
    _description = 'Reference (interview)'

    interview_id = fields.Many2one('ad.interview', required=True, ondelete='cascade', string='Interview form')
    name = fields.Char('Reference name', required=True)
    relation = fields.Char('Relationship')
    phone = fields.Char('Phone number')
