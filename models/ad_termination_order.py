from odoo import api, fields, models

LEAVE_REASONS = [
    ('martyr', 'For his martyrdom'),
    ('death', 'For his death'),
    ('resignation', 'For his resignation'),
    ('termination', 'Termination of his services'),
    ('investigation', 'Investigation board'),
]


class AdTerminationOrder(models.Model):
    """Order termination services AD-WI-FM-06-10 (أمر انهاء خدمات)."""
    _name = 'ad.termination.order'
    _description = 'Termination order'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.termination.order'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_termination'

    date = fields.Date(default=fields.Date.context_today, required=True, tracking=True, string='Date')
    employee_id = fields.Many2one('hr.employee', string='Mr. (employee)', required=True, tracking=True)
    capacity = fields.Char('In the capacity of', compute='_compute_from_employee', store=True, readonly=False)
    site_id = fields.Many2one('ad.work.site', string='Assigned to site', compute='_compute_from_employee', store=True, readonly=False)
    effective_date = fields.Date('Effective from', required=True, tracking=True)
    reason = fields.Selection(LEAVE_REASONS, required=True, default='termination', tracking=True, string='Reason for leaving')
    disciplinary_ref = fields.Char('Penalties form reference')
    state = fields.Selection([('draft', 'Draft'), ('hr', 'HR reviewed'), ('approved', 'Approved by the managing director'),
                              ('cancel', 'Cancelled')], default='draft', tracking=True, copy=False, string='Status')
    clearance_id = fields.Many2one('ad.clearance', string='Clearance', readonly=True, copy=False)

    @api.depends('employee_id')
    def _compute_from_employee(self):
        for rec in self:
            emp = rec.employee_id
            if emp:
                rec.capacity = emp.job_title or emp.job_id.name
                rec.site_id = emp.ad_work_site_id

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
            if not rec.clearance_id:
                clearance = self.env['ad.clearance'].sudo().create(rec._prepare_clearance_vals())
                clearance.action_start()
                rec.clearance_id = clearance

    def _prepare_clearance_vals(self):
        self.ensure_one()
        return {
            'termination_id': self.id, 'employee_id': self.employee_id.id, 'job_title': self.capacity,
            'site_id': self.site_id.id, 'stop_date': self.effective_date, 'reason': self.reason,
            'order_no': self.name, 'order_date': self.date, 'company_id': self.company_id.id,
        }

    def action_open_clearance(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'ad.clearance', 'view_mode': 'form', 'res_id': self.clearance_id.id}

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})
