from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from .ad_dashboard import FORMS


def _form_key(model_name):
    return 'form_' + model_name.replace('.', '_')


def _create_key(model_name):
    return 'create_' + model_name.replace('.', '_')


# key -> Arabic name. Order = order shown in the settings list.
BLOCKS = [
    ('nav_forms', 'القائمة الجانبية'),
    ('kpi_emp', 'بطاقة: الموظفون'),
    ('kpi_open', 'بطاقة: استمارات قيد الاجراء'),
    ('kpi_present', 'بطاقة: حاضرون الآن'),
    ('kpi_out', 'بطاقة: في اجازة اليوم'),
    ('kpi_leave_pending', 'بطاقة: طلبات اجازة بانتظار الموافقة'),
    ('kpi_slips', 'بطاقة: قسائم رواتب غير مؤكدة'),
    ('panel_create', 'لوحة الانشاء السريع'),
    ('create_emp', 'انشاء: موظف جديد'),
    ('create_att', 'انشاء: تسجيل حضور'),
    ('create_leave', 'انشاء: طلب اجازة'),
    ('create_payslip', 'انشاء: قسيمة راتب ودفعة رواتب'),
] + [(_create_key(m), 'انشاء: ' + t) for m, t, *_r in FORMS] + [
    ('panel_alerts', 'لوحة التنبيهات'),
    ('alert_leave', 'تنبيه: اجازات بانتظار الموافقة'),
    ('alert_slips', 'تنبيه: قسائم رواتب غير مؤكدة'),
    ('alert_transfer', 'تنبيه: انتهاء تخويل تنقل'),
    ('alert_probation', 'تنبيه: انتهاء فترة التجربة'),
    ('alert_clearance', 'تنبيه: براءة ذمة غير مكتملة'),
    ('panel_recent', 'جدول: اخر الاستمارات'),
    ('chart_trend', 'رسم: الاستمارات خلال 6 اشهر'),
    ('chart_types', 'رسم: حسب نوع الاستمارة'),
    ('chart_sites', 'رسم: الموظفون حسب الموقع'),
] + [(_form_key(m), 'استمارة: %s (عرض وقوائم وطباعة)' % t) for m, t, *_r in FORMS]

# The grid has 12 columns. Chosen sizes: quarter = 3, half = 6, full = 12.
# Defaults (used until a size is chosen) reproduce the original arrangement:
# six cards per row, quick-create full, alerts|recent halves, three charts.
SPAN = {'1': 3, '2': 6, '4': 12}
DEFAULT_SPAN = {'panel_create': 12, 'panel_alerts': 6, 'panel_recent': 6,
                'chart_trend': 4, 'chart_types': 4, 'chart_sites': 4}


class AdDashboardBlock(models.Model):
    """Who may see / use each block of the dashboard and each form.

    Nothing selected = every user who can open the dashboard (Odoo's normal
    access rights still apply on top). Users and/or groups selected = only
    those users and members of those groups. Data of a hidden block is never
    sent to the browser, and a restricted form cannot be printed by others.
    """
    _name = 'ad.dashboard.block'
    _description = 'صلاحيات عناصر لوحة المتابعة'
    _order = 'sequence, id'

    key = fields.Char('المفتاح', required=True, readonly=True, index=True)
    name = fields.Char('العنصر', required=True, translate=True)
    sequence = fields.Integer('الترتيب', default=10)
    user_ids = fields.Many2many('res.users', 'ad_dashboard_block_user_rel', 'block_id', 'user_id',
                                string='المستخدمون المسموح لهم',
                                help='اتركها مع المجموعات فارغة لاظهار العنصر للجميع.')
    width = fields.Selection([('1', 'ربع'), ('2', 'نصف'), ('4', 'كامل')], string='عرض العنصر',
                             help='عرض العنصر في لوحة المتابعة. الفارغ = الافتراضي.')
    group_ids = fields.Many2many('res.groups', 'ad_dashboard_block_group_rel', 'block_id', 'group_id',
                                 string='المجموعات المسموح لها')

    _key_uniq = models.Constraint('unique(key)', 'المفتاح يجب ان يكون فريدا.')

    @api.model
    def _all_keys(self):
        return {k for k, _n in BLOCKS}

    @api.model
    def _ids_by_key(self):
        return {b.key: b.id for b in self.sudo().search([])}

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
            raise AccessError(_('ليس لديك صلاحية على هذه الاستمارة. راجع مدير الموارد البشرية.'))

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
    def set_width(self, key, width):
        """Called from the dashboard edit mode (HR managers / admins only)."""
        user = self.env.user
        if not (user.has_group('hr.group_hr_manager') or user.has_group('base.group_system')):
            raise AccessError(_('ليس لديك صلاحية تعديل عرض العناصر.'))
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
