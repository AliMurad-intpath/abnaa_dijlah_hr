from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AdAppointmentOrder(models.Model):
    """Appointment Order Form AD-WI-FM-06-02 (أمر تعيين)."""
    _name = 'ad.appointment.order'
    _description = 'Appointment order'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.appointment.order'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_appointment'

    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True, string='Date')
    employee_id = fields.Many2one('hr.employee', string='Mr. (employee)', required=True, tracking=True)
    job_title = fields.Char('Addressed to', compute='_compute_job_title', store=True, readonly=False, required=True)
    site_id = fields.Many2one('ad.work.site', string='Site', required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    nominal_salary = fields.Monetary('Monthly nominal salary', currency_field='currency_id', required=True, tracking=True)
    allowance = fields.Monetary('Work site allowance', currency_field='currency_id', tracking=True)
    probation_months = fields.Integer('Probation period (months)', default=3)
    start_date = fields.Date('Start date', required=True, tracking=True)
    state = fields.Selection([('draft', 'Draft'), ('hr', 'HR reviewed'), ('approved', 'Approved by the managing director'),
                              ('cancel', 'Cancelled')], default='draft', tracking=True, copy=False, string='Status')
    interview_ref = fields.Char('Interview rating reference')

    @api.model_create_multi
    def create(self, vals_list):
        # job_title is a required stored compute: fill it before the INSERT (imports, API calls)
        for vals in vals_list:
            if not vals.get('job_title') and vals.get('employee_id'):
                emp = self.env['hr.employee'].browse(vals['employee_id'])
                vals['job_title'] = emp.job_title or emp.job_id.name or ''
        return super().create(vals_list)

    @api.depends('employee_id')
    def _compute_job_title(self):
        for rec in self:
            if rec.employee_id and not rec.job_title:
                rec.job_title = rec.employee_id.job_title or rec.employee_id.job_id.name

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id and self.employee_id.ad_work_site_id:
            self.site_id = self.employee_id.ad_work_site_id

    def action_submit(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        self.write({'state': 'hr'})
        self.ad_sign('hr')

    def action_approve(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_md')
        self._ad_before_final()
        for rec in self:
            rec.write({'state': 'approved'})
            rec.ad_sign('md')
            rec.employee_id.sudo().write({
                'job_title': rec.job_title,
                'ad_work_site_id': rec.site_id.id,
                'ad_nominal_salary': rec.nominal_salary,
                'ad_site_allowance': rec.allowance,
                'ad_start_date': rec.start_date,
                'ad_probation_end': rec.start_date + relativedelta(months=rec.probation_months)
                if rec.start_date and rec.probation_months else False,
            })

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})
