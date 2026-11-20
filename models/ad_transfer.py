from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class AdTransfer(models.Model):
    """Guard transfer to work sites AD-HR-FM-09 (استمارة تنقلات الحراس لمواقع العمل)."""
    _name = 'ad.transfer'
    _description = 'Guard transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'date desc, id desc'
    _ad_seq_code = 'ad.transfer'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_transfer'

    date = fields.Date(default=fields.Date.context_today, required=True, string='Date')
    employee_id = fields.Many2one('hr.employee', string='Employee name', required=True, tracking=True)
    old_site_id = fields.Many2one('ad.work.site', string='Current work site',
                                  compute='_compute_old_site', store=True, readonly=False)
    employee_no = fields.Char('Employee number', related='employee_id.ad_employee_no')
    old_supervisor = fields.Char('Current supervisor')
    old_supervisor_mobile = fields.Char('Supervisor mobile number')
    new_site_id = fields.Many2one('ad.work.site', string='New work site', required=True, tracking=True)
    new_supervisor = fields.Char('Receiving supervisor')
    start_date = fields.Date('Start date', tracking=True)
    start_shift = fields.Selection([('am', 'AM'), ('pm', 'PM')], default='am', string='Period (AM / PM)')
    leave_date = fields.Date('Instead of work site')
    leave_shift = fields.Selection([('am', 'AM'), ('pm', 'PM')], default='am', string='Period (AM / PM)')
    state = fields.Selection([
        ('draft', 'Draft'), ('ops', 'Operations'), ('site', 'Site confirmation'),
        ('hr', 'HR confirmation'), ('done', 'Authorized by the managing director'), ('cancel', 'Cancelled'),
    ], default='draft', tracking=True, copy=False, string='Status')
    md_date = fields.Date('Managing director authorization date', readonly=True, copy=False)
    valid_until = fields.Date('Authorization valid until', compute='_compute_valid_until', store=True)
    reminder_sent = fields.Boolean(copy=False, string='Alert sent')

    @api.depends('employee_id')
    def _compute_old_site(self):
        for rec in self:
            rec.old_site_id = rec.employee_id.ad_work_site_id

    @api.depends('md_date')
    def _compute_valid_until(self):
        for rec in self:
            rec.valid_until = rec.md_date + relativedelta(months=1) if rec.md_date else False

    def action_ops(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_ops_manager')
        self.write({'state': 'ops'}); self.ad_sign('ops')

    def action_site(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_ops_manager')
        self.write({'state': 'site'}); self.ad_sign('ops_site')

    def action_hr(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_user')
        for rec in self:
            rec.write({'state': 'hr'}); rec.ad_sign('hr')
            rec.employee_id.sudo().ad_work_site_id = rec.new_site_id

    def action_done(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_md')
        self._ad_before_final()
        self.write({'state': 'done', 'md_date': fields.Date.context_today(self)})
        self.ad_sign('md')

    def action_cancel(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'cancel'})

    def action_draft(self):
        self.ad_require_group('abnaa_dijlah_hr.group_ad_hr_manager')
        self.write({'state': 'draft'})

    @api.model
    def _cron_authorization_expiry(self):
        """Remind operations when an MD authorization expires within 3 days."""
        today = fields.Date.context_today(self)
        for rec in self.search([('state', '=', 'done'), ('reminder_sent', '=', False),
                                ('valid_until', '<=', today + relativedelta(days=3))]):
            rec.activity_schedule('mail.mail_activity_data_todo', date_deadline=rec.valid_until,
                                  summary=self.env._('Transfer authorization expires'),
                                  user_id=rec.create_uid.id)
            rec.reminder_sent = True
