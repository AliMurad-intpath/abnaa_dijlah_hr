from odoo import fields, models


class AdOnboarding(models.Model):
    """Effective Date Notice AD-WI-FM-06-03 (استمارة تاريخ مباشرة العمل)."""
    _name = 'ad.onboarding'
    _description = 'Start of work date form'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.onboarding'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_onboarding'

    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    employee_id = fields.Many2one('hr.employee', string='Employee name', required=True, tracking=True)
    appointment_id = fields.Many2one('ad.appointment.order', string='Appointment order number',
                                     domain="[('employee_id', '=', employee_id)]")
    site_id = fields.Many2one('ad.work.site', string='Work site')
    start_date = fields.Date('Start date', tracking=True)
    start_shift = fields.Selection([('am', 'Morning (AM)'), ('pm', 'Afternoon (PM)')], string='Period (AM / PM)', default='am')
    supervisor_name = fields.Char('Supervisor name')
    supervisor_mobile = fields.Char('Mobile number')
    # HR stage
    medical_done = fields.Boolean('Medical examination')
    medical_letter = fields.Char('Letter number')
    salary_done = fields.Boolean('Salary domiciliation')
    salary_letter = fields.Char('Letter number ')
    auth_done = fields.Boolean('Authorization letter')
    auth_letter = fields.Char('Letter number  ')
    # Logistics stage
    issue_date = fields.Date('Date employee was issued equipment')
    shirt_size = fields.Char('Shirt')
    trouser_size = fields.Char('Trousers')
    shoe_size = fields.Char('Shoes')
    has_pouch = fields.Boolean('Belt pouch')
    other_items = fields.Char('Other')
    # Operations stage confirmations
    ops_medical = fields.Boolean('Operations confirms receipt of the medical examination')
    ops_salary = fields.Boolean('Operations confirms receipt of the salary domiciliation')
    ops_auth = fields.Boolean('Operations confirms receipt of the authorization')
    training_done = fields.Boolean('Training completed')
    trainer_name = fields.Char('Trainer')
    state = fields.Selection([
        ('draft', 'Draft'), ('hr', 'HR section completed'), ('logistics', 'Employee equipped'),
        ('site', 'Site supervisor'), ('ops', 'Operations'), ('done', 'Approved by the managing director'), ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False, string='Status')

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
