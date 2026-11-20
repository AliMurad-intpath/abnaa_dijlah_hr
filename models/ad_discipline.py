from odoo import api, fields, models


class AdDiscipline(models.Model):
    """Penalty form AD-HR-FM-10 (استمارة العقوبات)."""
    _name = 'ad.discipline'
    _description = 'Penalties form'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.discipline'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_penalty'

    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    employee_id = fields.Many2one('hr.employee', string='Employee name', required=True, tracking=True)
    job_title = fields.Char('Job title', compute='_compute_employee_data', store=True, readonly=False)
    employee_no = fields.Char('Employee number', compute='_compute_employee_data', store=True, readonly=False)
    violation_ids = fields.Many2many('ad.violation.type', string='Violations')
    repetition = fields.Selection([('1', 'First'), ('2', 'Second'), ('3', 'Third')],
                                  compute='_compute_repetition', store=True, readonly=False, tracking=True, string='Violation repetition')
    decision = fields.Selection([
        ('suspension', 'Suspension from work'),
        ('deduction', 'Salary deduction penalty'),
        ('termination', 'Termination penalty'),
    ], tracking=True, string='Decision')
    date_from = fields.Date('From date')
    date_to = fields.Date('To date')
    total_days = fields.Integer('Total days', compute='_compute_total_days', store=True, readonly=False)
    deduction_type = fields.Char('Deduction type')
    deduction_amount = fields.Monetary('Deduction amount', currency_field='currency_id')
    deduction_from = fields.Date('From date')
    termination_from = fields.Date('From date')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    state = fields.Selection([
        ('draft', 'Draft'), ('hr', 'HR review'), ('ops', 'Operations'), ('approved', 'Approved by the managing director'),
        ('acknowledged', 'Employee acknowledgment of receipt'), ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False, string='Status')

    @api.depends('employee_id')
    def _compute_employee_data(self):
        for rec in self:
            rec.job_title = rec.employee_id.job_title or rec.employee_id.job_id.name
            rec.employee_no = rec.employee_id.ad_employee_no

    @api.depends('employee_id', 'date')
    def _compute_repetition(self):
        for rec in self:
            if not rec.employee_id:
                rec.repetition = '1'
                continue
            domain = [('employee_id', '=', rec.employee_id.id), ('state', 'in', ('approved', 'acknowledged'))]
            if rec.id:
                domain.append(('id', '!=', rec.id))
            prior = self.search_count(domain)
            rec.repetition = str(min(prior + 1, 3))

    @api.depends('date_from', 'date_to')
    def _compute_total_days(self):
        for rec in self:
            rec.total_days = (rec.date_to - rec.date_from).days + 1 if rec.date_from and rec.date_to else 0

    def action_hr(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        self.write({'state': 'hr'}); self.ad_sign('hr')

    def action_ops(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_ops_manager')
        self.write({'state': 'ops'}); self.ad_sign('ops')

    def action_approve(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_md')
        self._ad_before_final()
        self.write({'state': 'approved'}); self.ad_sign('md')

    def action_acknowledge(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        self.write({'state': 'acknowledged'}); self.ad_sign('employee')

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})
