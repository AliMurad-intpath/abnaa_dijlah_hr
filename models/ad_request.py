from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError

try:
    from odoo.fields import Domain
except ImportError:  # pragma: no cover
    from odoo.orm.domains import Domain

from .ad_chain import AD_STATUS, BULK_LIMIT

# model, label, the sequence used in the list
REQUEST_FORMS = [
    ('ad.interview', 'Interview rating'),
    ('ad.appointment.order', 'Appointment order'),
    ('ad.onboarding', 'Start of work'),
    ('ad.transfer', 'Guard transfer'),
    ('ad.discipline', 'Penalty'),
    ('ad.termination.order', 'Termination order'),
    ('ad.clearance', 'Clearance'),
    ('ad.employee.guarantee', 'Guarantee and pledge'),
    ('ad.employee.pledge', 'Written pledge'),
]


class AdRequest(models.Model):
    """One list for every HR form (read-only SQL view over the form tables)."""
    _name = 'ad.request'
    _description = 'HR request'
    _auto = False
    _order = 'created_on desc, id desc'

    name = fields.Char('Number', readonly=True)
    res_model = fields.Selection(REQUEST_FORMS, string='Form', readonly=True)
    res_id = fields.Integer('Record', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    subject = fields.Char('Candidate', readonly=True)
    employee_label = fields.Char('Employee / candidate', compute='_compute_employee_label')
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    ad_status = fields.Selection(AD_STATUS, string='Status', readonly=True)
    pending_step = fields.Char('Current stage', readonly=True)
    created_on = fields.Datetime('Created on', readonly=True)
    creator_id = fields.Many2one('res.users', string='Created by', readonly=True)
    awaiting_me = fields.Boolean('Awaiting my approval', compute='_compute_awaiting_me', search='_search_awaiting_me')

    def _compute_awaiting_me(self):
        for rec in self:
            rec.awaiting_me = False

    @api.model
    def _search_awaiting_me(self, operator, value):
        steps = self.env['ad.form.step'].sudo().search(self.env['ad.form.step']._pending_domain())
        by_model = {}
        for step in steps:
            by_model.setdefault(step.res_model, set()).add(step.res_id)
        clauses = [Domain('res_model', '=', model) & Domain('res_id', 'in', sorted(ids)) for model, ids in by_model.items()]
        found = Domain.OR(clauses) if clauses else Domain.FALSE
        positive = (operator == '=') == bool(value)
        return found if positive else ~found

    @api.depends('employee_id', 'subject')
    def _compute_employee_label(self):
        for rec in self:
            rec.employee_label = rec.subject or rec.employee_id.display_name or ''

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        parts = []
        for idx, (model, _label) in enumerate(REQUEST_FORMS):
            if model not in self.env:
                continue
            table = self.env[model]._table
            interview = model == 'ad.interview'
            parts.append("""
                SELECT (t.id::bigint * 10 + %(idx)s) AS id,
                       '%(model)s'::varchar AS res_model,
                       t.id AS res_id,
                       t.name AS name,
                       %(employee)s AS employee_id,
                       %(subject)s AS subject,
                       t.company_id AS company_id,
                       t.ad_status AS ad_status,
                       (SELECT s.name FROM ad_form_step s
                         WHERE s.res_model = '%(model)s' AND s.res_id = t.id AND s.state = 'pending'
                         ORDER BY s.sequence, s.id LIMIT 1) AS pending_step,
                       t.create_date AS created_on,
                       t.create_uid AS creator_id
                  FROM "%(table)s" t""" % {
                'idx': idx, 'model': model, 'table': table,
                'employee': 'NULL::integer' if interview else 't.employee_id',
                'subject': 't.candidate_name' if interview else 'NULL::varchar'})
        if not parts:
            parts.append("SELECT 0::bigint AS id, NULL::varchar AS res_model, 0 AS res_id, NULL::varchar AS name, "
                         "NULL::integer AS employee_id, NULL::varchar AS subject, NULL::integer AS company_id, "
                         "NULL::varchar AS ad_status, NULL::varchar AS pending_step, NULL::timestamp AS created_on, "
                         "NULL::integer AS creator_id WHERE false")
        self.env.cr.execute('CREATE OR REPLACE VIEW %s AS (%s)' % (self._table, ' UNION ALL '.join(parts)))

    # ----------------------------------------------------------------- access
    @api.model
    def _ad_visible_domain(self):
        """Only the forms the user may open: same rights, form permissions and record rules as the forms themselves."""
        blocks = self.env['ad.dashboard.block']
        clauses = []
        for model, _label in REQUEST_FORMS:
            if model not in self.env or not self.env[model].has_access('read'):
                continue
            try:
                blocks._check_form_access(model)
            except AccessError:
                continue
            # a sub-query, not a list of ids: the database filters with the form's own access rules in one statement
            clauses.append(Domain('res_model', '=', model) & Domain('res_id', 'in', self.env[model]._search([])))
        return Domain.OR(clauses) if clauses else Domain.FALSE

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        if not self.env.su and not kwargs.get('bypass_access'):
            domain = Domain(domain) & self._ad_visible_domain()
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    # ---------------------------------------------------------------- actions
    def action_open(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id).exists()
        if not record:
            raise UserError(self.env._('This form no longer exists.'))
        record.check_access('read')
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'views': [[False, 'form']], 'target': 'current'}

    def _bulk_targets(self):
        if len(self) > BULK_LIMIT:
            raise UserError(self.env._('Select at most %s requests at a time.', BULK_LIMIT))
        return [self.env[r.res_model].browse(r.res_id).exists() for r in self]

    def _bulk_report(self, done, failed, title):
        message = self.env._('%(done)s done, %(failed)s skipped.', done=done, failed=len(failed))
        if failed:
            message += '\n' + '\n'.join(failed[:10])
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': title, 'message': message, 'type': 'warning' if failed else 'success',
                           'sticky': bool(failed), 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def action_bulk_approve(self):
        """Approve the selected requests that are waiting for the current user (the others are skipped and listed)."""
        done, failed = 0, []
        for record in self._bulk_targets():
            if not record:
                continue
            try:
                with self.env.cr.savepoint():
                    record.action_ad_approve()
                done += 1
            except (UserError, AccessError) as exc:
                failed.append('%s: %s' % (record.display_name, exc.args[0] if exc.args else exc))
        return self._bulk_report(done, failed, self.env._('Bulk approval'))

    def action_bulk_submit(self):
        """Send the selected draft requests for approval."""
        done, failed = 0, []
        for record in self._bulk_targets():
            if not record:
                continue
            try:
                with self.env.cr.savepoint():
                    if not record.ad_can_submit:
                        raise UserError(self.env._('The request cannot be sent in its current state.'))
                    record.action_ad_submit()
                done += 1
            except Exception as exc:
                failed.append('%s: %s' % (record.display_name, exc.args[0] if exc.args else exc))
        return self._bulk_report(done, failed, self.env._('Bulk submission'))

    def action_open_bulk_create(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('Create for a whole site'), 'res_model': 'ad.bulk.create',
                'views': [[False, 'form']], 'target': 'new'}

    def action_new_request(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('New request'), 'res_model': 'ad.request.new',
                'views': [[False, 'form']], 'target': 'new'}


class AdRequestNew(models.TransientModel):
    _name = 'ad.request.new'
    _description = 'Choose the form of a new request'

    form_type = fields.Selection(REQUEST_FORMS, string='Form', required=True, default='ad.appointment.order')

    def action_create(self):
        self.ensure_one()
        model = self.form_type
        self.env['ad.dashboard.block']._check_form_access(model)
        self.env[model].check_access('create')
        return {'type': 'ir.actions.act_window', 'res_model': model, 'views': [[False, 'form']], 'target': 'current'}


class AdBulkCreate(models.TransientModel):
    """Create the same form for every guard of a site (transfers and penalties), as drafts ready to be sent."""
    _name = 'ad.bulk.create'
    _description = 'Create forms for a whole site'

    form_type = fields.Selection([('ad.transfer', 'Guard transfer'), ('ad.discipline', 'Penalty')],
                                 string='Form', required=True, default='ad.transfer')
    site_id = fields.Many2one('ad.work.site', 'Site (the guards working there)', required=True)
    exclude_employee_ids = fields.Many2many('hr.employee', 'ad_bulk_create_excl_rel', 'wizard_id', 'employee_id',
                                            string='Except these guards', domain="[('ad_work_site_id', '=', site_id)]")
    employee_count = fields.Integer('Guards', compute='_compute_employee_count')
    new_site_id = fields.Many2one('ad.work.site', 'New work site')
    start_date = fields.Date('Start date')
    violation_ids = fields.Many2many('ad.violation.type', 'ad_bulk_create_violation_rel', 'wizard_id', 'violation_id',
                                     string='Violations')
    decision = fields.Selection([('suspension', 'Suspension from work'), ('deduction', 'Salary deduction penalty'),
                                 ('termination', 'Termination penalty')], string='Decision')

    def _employees(self):
        self.ensure_one()
        return self.env['hr.employee'].search([('ad_work_site_id', '=', self.site_id.id)]) - self.exclude_employee_ids

    @api.depends('site_id', 'exclude_employee_ids')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec._employees()) if rec.site_id else 0

    def action_create(self):
        self.ensure_one()
        model = self.form_type
        self.env['ad.dashboard.block']._check_form_access(model)
        self.env[model].check_access('create')
        if model == 'ad.transfer' and not self.new_site_id:
            raise UserError(self.env._('Choose the new work site.'))
        if model == 'ad.transfer' and self.new_site_id == self.site_id:
            raise UserError(self.env._('The new site is the same as the current site.'))
        employees = self._employees()
        if not employees:
            raise UserError(self.env._('There are no guards at this site.'))
        Model = self.env[model].with_context(tracking_disable=True, mail_create_nolog=True)
        skipped = []
        if model == 'ad.transfer':
            busy = self.env[model].sudo().search([('employee_id', 'in', employees.ids), ('ad_status', 'in', ('draft', 'pending'))])
            skipped = busy.employee_id
            employees -= skipped
        vals_list = []
        for emp in employees:
            vals = Model._ad_employee_fill_values(emp)
            vals['employee_id'] = emp.id
            if model == 'ad.transfer':
                vals.update(new_site_id=self.new_site_id.id, start_date=self.start_date,
                            new_supervisor=self.new_site_id.supervisor_id.name or False)
            else:
                vals.update(violation_ids=[(6, 0, self.violation_ids.ids)], decision=self.decision or False)
            vals_list.append(vals)
        records = Model.create(vals_list)
        index = [m for m, _l in REQUEST_FORMS].index(model)
        listing = {'type': 'ir.actions.act_window', 'name': self.env._('Requests'), 'res_model': 'ad.request',
                   'views': [[False, 'list']], 'target': 'current',
                   'domain': [('id', 'in', [i * 10 + index for i in records.ids])]}
        if skipped:
            return {'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': self.env._('Created: %s', len(records)), 'type': 'warning', 'sticky': True,
                               'message': self.env._('Skipped (an open transfer already exists): %s',
                                                     ', '.join(skipped.mapped('name')[:30])),
                               'next': listing}}
        return listing
