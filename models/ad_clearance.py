from odoo import api, fields, models
from odoo.exceptions import UserError

from .ad_termination_order import LEAVE_REASONS

DEPARTMENTS = [
    ('ops', 'Operations Dept - OPS + Armory'),
    ('aa', 'Administration Dept - AA'),
    ('lo', 'Logistics Dept - LO'),
    ('md', 'Vehicles Dept - MD'),
    ('hr', 'Human Resources Dept - HR'),
    ('fin', 'Finance Dept - FIN'),
]
DEPT_GROUPS = {
    'ops': 'abnaa_dijlah_hr.group_ad_ops_manager', 'aa': 'abnaa_dijlah_hr.group_ad_admin',
    'lo': 'abnaa_dijlah_hr.group_ad_logistics', 'md': 'abnaa_dijlah_hr.group_ad_motor',
    'hr': 'abnaa_dijlah_hr.group_ad_hr_manager', 'fin': 'abnaa_dijlah_hr.group_ad_finance',
}


class AdClearance(models.Model):
    """Deletion Form / Clearance AD-WI-FM-06-11 (استمارة براءة الذمة) - 2 pages."""
    _name = 'ad.clearance'
    _description = 'Clearance'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_seq_code = 'ad.clearance'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_clearance'

    termination_id = fields.Many2one('ad.termination.order', string='Termination order', ondelete='set null')
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='Employee')
    address = fields.Char('Residential address', related='employee_id.ad_address')
    job_title = fields.Char('Job title')
    hire_date = fields.Date('Hire date', related='employee_id.ad_start_date')
    site_id = fields.Many2one('ad.work.site', string='Workplace')
    stop_date = fields.Date('Date work stopped', required=True)
    reason = fields.Selection(LEAVE_REASONS, required=True, default='termination', string='Reason for leaving')
    order_no = fields.Char('In numbers')
    order_date = fields.Date('Dated')
    line_ids = fields.One2many('ad.clearance.line', 'clearance_id', string='Department signatures')
    due_ids = fields.One2many('ad.clearance.due', 'clearance_id', string='Dues')
    hr_note = fields.Text('Note to the managing director')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    amount_paid = fields.Monetary('An amount of', currency_field='currency_id', tracking=True)
    amount_due = fields.Monetary('Total dues', currency_field='currency_id', compute='_compute_amount_due', store=True)
    receipt_date = fields.Date('Date')
    witness1 = fields.Char('First witness')
    witness2 = fields.Char('Second witness')
    state = fields.Selection([
        ('draft', 'Draft'), ('clearing', 'Clearance from departments'), ('settled', 'Dues settled'),
        ('hr_cert', 'HR approval'), ('done', 'Approved by the managing director'), ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False, string='Status')
    all_signed = fields.Boolean(compute='_compute_all_signed', string='Signatures completed')

    @api.depends('due_ids.amount')
    def _compute_amount_due(self):
        for rec in self:
            rec.amount_due = sum(rec.due_ids.mapped('amount'))

    @api.depends('line_ids.signed_date')
    def _compute_all_signed(self):
        for rec in self:
            rec.all_signed = bool(rec.line_ids) and all(rec.line_ids.mapped('signed_date'))

    def action_start(self):
        for rec in self:
            if not rec.line_ids:
                rec.write({'line_ids': [(0, 0, {'department': code, 'sequence': i})
                                        for i, (code, _label) in enumerate(DEPARTMENTS, start=1)]})
            rec.state = 'clearing'

    def action_settle(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_finance')
        for rec in self:
            if not rec.all_signed:
                raise UserError(self.env._('Each department must sign its line before the dues are settled.'))
            rec.write({'state': 'settled', 'receipt_date': rec.receipt_date or fields.Date.context_today(rec)})
            rec.ad_sign('fin')

    def action_hr_certify(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'hr_cert'})
        self.ad_sign('hr_manager')
        self.ad_sign('hr_specialist')

    def action_md_approve(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_md')
        self._ad_before_final()
        for rec in self:
            rec.write({'state': 'done'})
            rec.ad_sign('md')
            emp = rec.employee_id.sudo()
            if 'departure_date' in emp._fields:
                emp.departure_date = rec.stop_date
            emp.active = False

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})


class AdClearanceLine(models.Model):
    _name = 'ad.clearance.line'
    _description = 'Department clearance signature'
    _order = 'sequence, id'

    clearance_id = fields.Many2one('ad.clearance', required=True, ondelete='cascade', string='Clearance')
    sequence = fields.Integer(default=10, string='Sequence')
    department = fields.Selection(DEPARTMENTS, required=True, string='Department')
    manager_name = fields.Char('Department manager name')
    has_liability = fields.Boolean('Liability outstanding')
    note = fields.Char('Notes')
    signed_user_id = fields.Many2one('res.users', string='Signed by', readonly=True)
    signed_date = fields.Date('Signature date', readonly=True)

    def action_sign(self):
        for line in self:
            if not self.env.user.has_group(DEPT_GROUPS[line.department]):
                raise UserError(self.env._('You are not allowed to sign for this department.'))
            line.write({'signed_user_id': self.env.uid, 'signed_date': fields.Date.context_today(self),
                        'manager_name': line.manager_name or self.env.user.name})
            line.clearance_id.message_post(body=self.env._(
                'Clearance from %(dept)s was given by %(user)s', dept=self.env._(dict(DEPARTMENTS)[line.department]), user=self.env.user.name))


class AdClearanceDue(models.Model):
    _name = 'ad.clearance.due'
    _description = 'Dues'
    _order = 'sequence, id'

    clearance_id = fields.Many2one('ad.clearance', required=True, ondelete='cascade', string='Clearance')
    sequence = fields.Integer(default=10, string='Sequence')
    name = fields.Char('Description', required=True)
    currency_id = fields.Many2one('res.currency', related='clearance_id.currency_id')
    amount = fields.Monetary(currency_field='currency_id', string='Amount')
