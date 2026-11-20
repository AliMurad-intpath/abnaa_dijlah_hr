from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .ad_dashboard import FORMS


def _form_key(model_name):
    return 'form_' + model_name.replace('.', '_')


def _create_key(model_name):
    return 'create_' + model_name.replace('.', '_')


# key -> Arabic name. Order = order shown in the settings list.
BLOCKS = [
    ('nav_forms', 'Sidebar'),
    ('nav_overview', 'Sidebar: Overview (dashboard)'),
    ('kpi_emp', 'Card: Employees'),
    ('kpi_open', 'Card: Forms in progress'),
    ('kpi_present', 'Card: Present now'),
    ('kpi_out', 'Card: On leave today'),
    ('kpi_leave_pending', 'Card: Leave requests awaiting approval'),
    ('kpi_slips', 'Card: Unconfirmed payslips'),
    ('kpi_approvals', 'Card: My pending approvals'),
    ('panel_create', 'Quick create panel'),
    ('create_emp', 'Create: New employee'),
    ('create_att', 'Create: Check-in'),
    ('create_leave', 'Create: Leave request'),
    ('create_payslip', 'Create: Payslip and payslip batch'),
] + [(_create_key(m), 'Create: ' + t) for m, t, *_r in FORMS] + [
    ('panel_alerts', 'Alerts panel'),
    ('alert_leave', 'Alert: Leaves awaiting approval'),
    ('alert_slips', 'Alert: Unconfirmed payslips'),
    ('alert_transfer', 'Alert: Transfer authorization expiring'),
    ('alert_probation', 'Alert: Probation ending'),
    ('alert_clearance', 'Alert: Incomplete clearance'),
    ('panel_recent', 'Table: Latest forms'),
    ('chart_trend', 'Chart: Forms over 6 months'),
    ('chart_types', 'Chart: By form type'),
    ('chart_sites', 'Chart: Employees by site'),
] + [(_form_key(m), 'Form: %s (view, lists and print)' % t) for m, t, *_r in FORMS]

# The grid has 12 columns. Chosen sizes: quarter = 3, half = 6, full = 12.
# Defaults (used until a size is chosen) reproduce the original arrangement:
# six cards per row, quick-create full, alerts|recent halves, three charts.
SPAN = {'1': 3, '2': 6, '4': 12}
DEFAULT_SPAN = {'panel_create': 12, 'panel_alerts': 6, 'panel_recent': 6,
                'chart_trend': 4, 'chart_types': 4, 'chart_sites': 4}

# blocks that can be resized / moved on the dashboard, in their default order
LAYOUT = ['kpi_emp', 'kpi_open', 'kpi_present', 'kpi_out', 'kpi_leave_pending', 'kpi_slips',
          'kpi_approvals', 'panel_create', 'panel_alerts', 'panel_recent', 'chart_trend', 'chart_types', 'chart_sites']


class AdDashboardBlock(models.Model):
    """Who may see / use each block of the dashboard and each form.

    Nothing selected = every user who can open the dashboard (Odoo's normal
    access rights still apply on top). Users and/or groups selected = only
    those users and members of those groups. Data of a hidden block is never
    sent to the browser, and a restricted form cannot be printed by others.
    """
    _name = 'ad.dashboard.block'
    _description = 'Dashboard block permissions'
    _order = 'sequence, id'

    key = fields.Char('Key', required=True, readonly=True, index=True)
    name = fields.Char('Block', required=True, translate=True)
    sequence = fields.Integer('Order', default=10)
    user_ids = fields.Many2many('res.users', 'ad_dashboard_block_user_rel', 'block_id', 'user_id',
                                string='Allowed users',
                                help='Leave empty together with groups to show the block to everyone.')
    width = fields.Selection([('1', 'Quarter'), ('2', 'Half'), ('4', 'Full')], string='Block width',
                             help='Block width on the dashboard. Empty = default.')
    group_ids = fields.Many2many('res.groups', 'ad_dashboard_block_group_rel', 'block_id', 'group_id',
                                 string='Allowed groups')

    _key_uniq = models.Constraint('unique(key)', 'The key must be unique.')

    @api.model
    def _all_keys(self):
        return {k for k, _n in BLOCKS}

    @api.model
    def _ids_by_key(self):
        """Id of the permission record of every key (missing records are created)."""
        Block = self.sudo()
        have = {b.key: b.id for b in Block.search([])}
        names = dict(BLOCKS)
        for key in sorted(self._all_keys() - set(have)):
            have[key] = Block.create({'key': key, 'name': names.get(key, key)}).id
        return have

    @api.model
    def _allowed_keys(self):
        """Keys the current user may see."""
        user = self.env.user
        every = self._all_keys()
        if user.has_group('base.group_system'):
            return every
        fname = next((f for f in ('all_group_ids', 'group_ids', 'groups_id') if f in user._fields), None)
        mine = set(user[fname].ids) if fname else set()
        cfg = {b.key: (set(b.user_ids.ids), set(b.group_ids.ids)) for b in self.sudo().search([])}
        out = set()
        for k in every:
            users, groups = cfg.get(k, (set(), set()))
            if (not users and not groups) or user.id in users or (groups & mine):
                out.add(k)
        return out

    @api.model
    def _check_form_access(self, model_name):
        if _form_key(model_name) not in self._allowed_keys():
            raise AccessError(_('You do not have access to this form. Contact the HR manager.'))

    @api.model
    def _widths(self):
        """(spans, chosen): spans on the 12-column grid for every key, and the
        explicitly chosen size ('1'/'2'/'4') of the keys that have one."""
        spans, chosen = {}, {}
        for b in self.sudo().search([]):
            if b.width:
                chosen[b.key] = b.width
            spans[b.key] = SPAN[b.width] if b.width else (2 if b.key.startswith('kpi_') else DEFAULT_SPAN.get(b.key, 4))
        return spans, chosen

    @api.model
    def _layout_keys(self):
        return list(LAYOUT)

    @api.model
    def _layout_order(self):
        keys = self._layout_keys()
        seq = {b.key: b.sequence for b in self.sudo().search([('key', 'in', keys)])}
        return sorted(keys, key=lambda k: (seq.get(k, 10), keys.index(k)))

    @api.model
    def _orders(self):
        return {k: i for i, k in enumerate(self._layout_order())}

    @api.model
    def move_block(self, key, delta, visible):
        """Move a block one place earlier (-1) or later (+1) among the visible ones."""
        user = self.env.user
        if not (user.has_group('hr.group_hr_manager') or user.has_group('base.group_system')):
            raise AccessError(_('You do not have permission to change the block order.'))
        order = self._layout_order()
        vis = [k for k in order if k in set(visible or [])]
        if key not in vis:
            return False
        i = vis.index(key)
        j = i + (1 if delta > 0 else -1)
        if not 0 <= j < len(vis):
            return False
        ia, ib = order.index(vis[i]), order.index(vis[j])
        order[ia], order[ib] = order[ib], order[ia]
        recs = {b.key: b for b in self.sudo().search([('key', 'in', self._layout_keys())])}
        for n, k in enumerate(order):
            if k in recs:
                recs[k].sequence = 10 * (n + 1)
            else:
                self.sudo().create({'key': k, 'name': dict(BLOCKS).get(k, k), 'sequence': 10 * (n + 1)})
        return True

    @api.model
    def set_width(self, key, width):
        """Called from the dashboard edit mode (HR managers / admins only)."""
        user = self.env.user
        if not (user.has_group('hr.group_hr_manager') or user.has_group('base.group_system')):
            raise AccessError(_('You do not have permission to change the block width.'))
        width = str(width) if width else False      # 0 / empty = back to default
        if (width and width not in SPAN) or key not in self._all_keys():
            raise ValueError('bad width or key')
        rec = self.sudo().search([('key', '=', key)], limit=1)
        if rec:
            rec.width = width
        elif width:
            name = dict(BLOCKS).get(key, key)
            self.sudo().create({'key': key, 'name': name, 'width': width})
        return True
