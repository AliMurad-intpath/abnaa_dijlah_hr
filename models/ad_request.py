from odoo import api, fields, models, tools
from odoo.exceptions import AccessError, UserError

try:
    from odoo.fields import Domain
except ImportError:  # pragma: no cover
    from odoo.orm.domains import Domain

from .ad_chain import AD_STATUS
from .ad_dashboard import _arabic_terms

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


def _arabic_fields_get(env, result):
    """Labels and selection values in Arabic, read from i18n/ar.po like the dashboard does."""
    if (env.lang or '').startswith('ar'):
        terms = _arabic_terms()
        for info in result.values():
            if info.get('string') in terms:
                info['string'] = terms[info['string']]
            if info.get('selection'):
                info['selection'] = [(key, terms.get(label, label)) for key, label in info['selection']]
    return result


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

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        return _arabic_fields_get(self.env, super().fields_get(allfields, attributes))

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
            ids = self.env[model].search([]).ids
            if ids:
                clauses.append(Domain('res_model', '=', model) & Domain('res_id', 'in', ids))
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

    def action_new_request(self):
        return {'type': 'ir.actions.act_window', 'name': self.env._('New request'), 'res_model': 'ad.request.new',
                'views': [[False, 'form']], 'target': 'new'}


class AdRequestNew(models.TransientModel):
    _name = 'ad.request.new'
    _description = 'Choose the form of a new request'

    form_type = fields.Selection(REQUEST_FORMS, string='Form', required=True, default='ad.appointment.order')

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        return _arabic_fields_get(self.env, super().fields_get(allfields, attributes))

    def action_create(self):
        self.ensure_one()
        model = self.form_type
        self.env['ad.dashboard.block']._check_form_access(model)
        self.env[model].check_access('create')
        return {'type': 'ir.actions.act_window', 'res_model': model, 'views': [[False, 'form']], 'target': 'current'}
