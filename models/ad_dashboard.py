from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

# (model, short title, form code, closed states, kind colour, icon)
FORMS = [
    ('ad.interview', 'Interview rating', '06-01', ('done', 'cancel'), 'bar', 'comments'),
    ('ad.appointment.order', 'Appointment order', '06-02', ('approved', 'cancel'), 'kpi', 'file'),
    ('ad.onboarding', 'Start of work', '06-03', ('done', 'cancel'), 'column', 'login'),
    ('ad.transfer', 'Guard transfer', 'HR-FM-09', ('done', 'cancel'), 'area', 'swap'),
    ('ad.discipline', 'Penalty', 'HR-FM-10', ('approved', 'acknowledged', 'cancel'), 'pie', 'gavel'),
    ('ad.termination.order', 'Termination order', '06-10', ('approved', 'cancel'), 'doughnut', 'logout'),
    ('ad.clearance', 'Clearance', '06-11', ('done', 'cancel'), 'doughnut', 'check'),
    ('ad.employee.guarantee', 'Guarantee and pledge', 'Annex', ('signed', 'cancel'), 'table', 'shield'),
    ('ad.employee.pledge', 'Written pledge', 'FM-17', ('signed', 'cancel'), 'table', 'pen'),
]


class AdDashboard(models.AbstractModel):
    _name = 'ad.dashboard'
    _description = 'Abnaa Dijlah Company Forms dashboard'

    # ---- helpers -------------------------------------------------------
    def _ok(self, model_name, mode='read'):
        env = self.env
        return model_name in env and env[model_name].has_access(mode)

    def _view_id(self, xmlid):
        rec = self.env.ref(xmlid, raise_if_not_found=False)
        return rec.id if rec else False

    # ---- main entry ----------------------------------------------------
    @api.model
    def get_data(self, edit=False, lang=None):
        """All numbers for the OWL screen. Runs with the caller's rights, so a
        user only counts (and can only create) what they are allowed to."""
        if lang in ('ar', 'en'):
            installed = self.env['res.lang'].search([('active', '=', True)]).mapped('code')
            code = next((c for c in installed if c == lang or c.startswith(lang + '_')), None)
            if code:
                self = self.with_context(lang=code)
        env = self.env
        Block = env['ad.dashboard.block']
        can_edit = env.user.has_group('hr.group_hr_manager') or env.user.has_group('base.group_system')
        edit = bool(edit and can_edit)
        allowed = Block._all_keys() if edit else Block._allowed_keys()
        can = allowed.__contains__
        today = date.today()
        now = fields.Datetime.now()
        months = [(today.replace(day=1) - relativedelta(months=i)) for i in range(5, -1, -1)]
        tiles, trend, recent, create = [], [0] * 6, [], []
        for model_name, title, code, closed, kind, icon in FORMS:
            fkey = 'form_' + model_name.replace('.', '_')
            ckey = 'create_' + model_name.replace('.', '_')
            if not self._ok(model_name) or not can(fkey):
                continue
            Model = env[model_name]
            open_dom = [('state', 'not in', list(closed))] if 'state' in Model._fields else []
            row = {'block': fkey, 'model': model_name, 'title': env._(title), 'code': code, 'kind': kind, 'icon': icon,
                   'closed': list(closed), 'open': Model.search_count(open_dom),
                   'total': Model.search_count([]), 'created_6m': 0}
            sel = dict(Model._fields['state']._description_selection(env)) if 'state' in Model._fields else {}
            for idx, m in enumerate(months):
                n = Model.search_count([
                    ('create_date', '>=', m.strftime('%Y-%m-%d')),
                    ('create_date', '<', (m + relativedelta(months=1)).strftime('%Y-%m-%d'))])
                trend[idx] += n
                row['created_6m'] += n
            tiles.append(row)
            for rec in Model.search([], order='create_date desc', limit=6):
                recent.append({
                    'model': model_name, 'id': rec.id, 'title': env._(title), 'name': rec.display_name,
                    'state': sel.get(rec.state, '') if 'state' in rec._fields else '',
                    'when': rec.create_date, 'who': rec.create_uid.name,
                })
            if can(ckey) and Model.has_access('create'):
                create.append({'block': ckey, 'key': model_name, 'label': env._(title), 'model': model_name, 'icon': icon,
                               'group': 'forms', 'target': 'current'})
        if not can('chart_types'):
            for t in tiles:
                t['created_6m'] = 0
        recent.sort(key=lambda r: r['when'], reverse=True)
        recent = recent[:8]
        for r in recent:
            r['when'] = fields.Datetime.to_string(r['when'])

        Employee = env['hr.employee']
        kpis, alerts, sites = [], [], []
        if can('kpi_emp') and self._ok('hr.employee'):
            kpis.append({'key': 'emp', 'label': env._('Employees'), 'value': Employee.search_count([]),
                         'icon': 'users', 'kind': 'kpi', 'model': 'hr.employee', 'domain': []})
        if can('kpi_open'):
            kpis.append({'key': 'open', 'label': env._('Forms in progress'),
                         'value': sum(t['open'] for t in tiles), 'icon': 'file', 'kind': 'column'})

        # approvals waiting for this user (the form approval chain)
        if can('kpi_approvals') and self._ok('ad.form.step'):
            domain = env['ad.form.step']._pending_domain()
            kpis.append({'key': 'approvals', 'label': env._('My pending approvals'),
                         'value': env['ad.form.step'].sudo().search_count(domain),
                         'icon': 'check-user', 'kind': 'kpi', 'model': 'ad.form.step', 'domain': domain})
        # Attendance
        if self._ok('hr.attendance') and (can('kpi_present') or can('create_att')):
            n = env['hr.attendance'].search_count([('check_out', '=', False)])
            if can('kpi_present'):
              kpis.append({'key': 'present', 'label': env._('Present now'), 'value': n, 'icon': 'check-user',
                         'kind': 'area', 'model': 'hr.attendance', 'domain': [('check_out', '=', False)]})
            if can('create_att') and env['hr.attendance'].has_access('create'):
                create.append({'block': 'create_att', 'key': 'att', 'label': env._('Check-in'), 'model': 'hr.attendance',
                               'icon': 'clock', 'group': 'hr', 'target': 'new'})
        # Time off
        if self._ok('hr.leave') and any(can(k) for k in ('kpi_out', 'kpi_leave_pending', 'alert_leave', 'create_leave')):
            Leave = env['hr.leave']
            out_dom = [('state', '=', 'validate'), ('date_from', '<=', now), ('date_to', '>=', now)]
            pend_dom = [('state', 'in', ['confirm', 'validate1'])]
            if can('kpi_out'):
              kpis.append({'key': 'out', 'label': env._('On leave today'), 'value': Leave.search_count(out_dom),
                         'icon': 'calendar', 'kind': 'doughnut', 'model': 'hr.leave', 'domain': out_dom})
            pend = Leave.search_count(pend_dom)
            if can('kpi_leave_pending'):
              kpis.append({'key': 'leave_pending', 'label': env._('Leave requests awaiting approval'), 'value': pend,
                         'icon': 'calendar', 'kind': 'pie', 'model': 'hr.leave', 'domain': pend_dom})
            if pend and can('alert_leave'):
                alerts.append({'block': 'alert_leave', 'text': env._('%s leave request(s) awaiting approval', pend), 'model': 'hr.leave',
                               'domain': pend_dom, 'level': 'warn'})
            if can('create_leave') and Leave.has_access('create'):
                create.append({'block': 'create_leave', 'key': 'leave', 'label': env._('Leave request'), 'model': 'hr.leave', 'icon': 'calendar',
                               'group': 'hr', 'target': 'new',
                               'view_id': self._view_id('hr_holidays.hr_leave_view_form_dashboard')})
        # Payroll (Enterprise)
        if self._ok('hr.payslip') and any(can(k) for k in ('kpi_slips', 'alert_slips', 'create_payslip')):
            Slip = env['hr.payslip']
            draft_dom = [('state', 'in', ['draft', 'verify'])]
            n = Slip.search_count(draft_dom)
            if can('kpi_slips'):
              kpis.append({'key': 'slips', 'label': env._('Unconfirmed payslips'), 'value': n, 'icon': 'wallet',
                         'kind': 'bar', 'model': 'hr.payslip', 'domain': draft_dom})
            if n and can('alert_slips'):
                alerts.append({'block': 'alert_slips', 'text': env._('%s payslip(s) not yet confirmed', n), 'model': 'hr.payslip',
                               'domain': draft_dom, 'level': 'info'})
            if can('create_payslip') and Slip.has_access('create'):
                create.append({'block': 'create_payslip', 'key': 'slip', 'label': env._('New payslip'), 'model': 'hr.payslip',
                               'icon': 'wallet', 'group': 'hr', 'target': 'current'})
            if can('create_payslip') and 'hr.payslip.run' in env and env['hr.payslip.run'].has_access('create'):
                create.append({'block': 'create_payslip', 'key': 'batch', 'label': env._('Payslip batch'), 'model': 'hr.payslip.run',
                               'icon': 'wallet', 'group': 'hr', 'target': 'current'})
        if can('create_emp') and Employee.has_access('create'):
            create.insert(0, {'block': 'create_emp', 'key': 'emp', 'label': env._('New employee'), 'model': 'hr.employee',
                              'icon': 'user-plus', 'group': 'hr', 'target': 'current'})

        # Alerts from the AD forms
        if can('alert_transfer') and 'ad.transfer' in env and self._ok('ad.transfer'):
            dom = [('state', '=', 'done'), ('valid_until', '>=', today),
                   ('valid_until', '<=', today + timedelta(days=7))]
            n = env['ad.transfer'].search_count(dom)
            if n:
                alerts.append({'block': 'alert_transfer', 'text': env._('%s transfer authorization(s) expiring within 7 days', n), 'model': 'ad.transfer',
                               'domain': dom, 'level': 'warn'})
        if can('alert_probation') and 'ad_probation_end' in Employee._fields and self._ok('hr.employee'):
            dom = [('ad_probation_end', '>=', today), ('ad_probation_end', '<=', today + timedelta(days=30))]
            n = Employee.search_count(dom)
            if n:
                alerts.append({'block': 'alert_probation', 'text': env._('%s employee(s) whose probation ends within 30 days', n), 'model': 'hr.employee',
                               'domain': dom, 'level': 'warn'})
        if can('alert_clearance') and 'ad.clearance' in env and self._ok('ad.clearance'):
            dom = [('state', 'in', ['draft', 'clearing'])]
            n = env['ad.clearance'].search_count(dom)
            if n:
                alerts.append({'block': 'alert_clearance', 'text': env._('%s clearance(s) not completed', n), 'model': 'ad.clearance',
                               'domain': dom, 'level': 'info'})

        if can('chart_sites') and 'ad_work_site_id' in Employee._fields and self._ok('hr.employee'):
            for site, c in Employee._read_group([('ad_work_site_id', '!=', False)],
                                                ['ad_work_site_id'], ['__count'],
                                                order='__count desc', limit=8):
                sites.append({'id': site.id, 'name': site.display_name, 'count': c})
        return {
            'today': today.strftime('%Y-%m-%d'),
            'user_name': env.user.name,
            'show': {k: True for k in allowed},
            'can_edit_access': can_edit, 'edit': edit,
            'ids': Block._ids_by_key() if can_edit else {},
            'widths': Block._widths()[0], 'wset': Block._widths()[1], 'orders': Block._orders(),
            'kpis': kpis, 'tiles': tiles if (can('nav_forms') or can('chart_types')) else [], 'alerts': alerts, 'create': create,
            'recent': recent if can('panel_recent') else [],
            'trend': ([{'label': m.strftime('%m/%Y'), 'count': trend[i]} for i, m in enumerate(months)]
                      if can('chart_trend') else []),
            'sites': sites,
        }
