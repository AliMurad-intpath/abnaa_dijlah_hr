from odoo import api, fields, models
from odoo.exceptions import UserError

from .ad_termination_order import LEAVE_REASONS

DEPARTMENTS = [
    ('ops', 'قسم العمليات - OPS + المشجب'),
    ('aa', 'قسم الإدارة- AA'),
    ('lo', 'قسم اللوجيستسك- LO'),
    ('md', 'قسم الاليات- MD'),
    ('hr', 'قسم الموارد البشرية- HR'),
    ('fin', 'قسم المالية-FIN'),
]
DEPT_GROUPS = {
    'ops': 'abnaa_dijlah_hr.group_ad_ops_manager', 'aa': 'abnaa_dijlah_hr.group_ad_admin',
    'lo': 'abnaa_dijlah_hr.group_ad_logistics', 'md': 'abnaa_dijlah_hr.group_ad_motor',
    'hr': 'abnaa_dijlah_hr.group_ad_hr_manager', 'fin': 'abnaa_dijlah_hr.group_ad_finance',
}


class AdClearance(models.Model):
    """Deletion Form / Clearance AD-WI-FM-06-11 (استمارة براءة الذمة) - 2 pages."""
    _name = 'ad.clearance'
    _description = 'براءة الذمة'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ad.approval.mixin']
    _order = 'id desc'
    _ad_seq_code = 'ad.clearance'
    _ad_form_xmlid = 'abnaa_dijlah_hr.form_tpl_clearance'

    termination_id = fields.Many2one('ad.termination.order', string='أمر انهاء خدمات', ondelete='set null')
    employee_id = fields.Many2one('hr.employee', required=True, tracking=True, string='الموظف')
    address = fields.Char('عنوان السكن', related='employee_id.ad_address')
    job_title = fields.Char('عنوان وظيفته')
    hire_date = fields.Date('تاريخ التعيين', related='employee_id.ad_start_date')
    site_id = fields.Many2one('ad.work.site', string='محل العمل')
    stop_date = fields.Date('تاريخ التوقف عن العمل', required=True)
    reason = fields.Selection(LEAVE_REASONS, required=True, default='termination', string='سبب ترك العمل')
    order_no = fields.Char('بالعدد')
    order_date = fields.Date('المؤرخ في')
    line_ids = fields.One2many('ad.clearance.line', 'clearance_id', string='توقيعات الاقسام')
    due_ids = fields.One2many('ad.clearance.due', 'clearance_id', string='مستحقات')
    hr_note = fields.Text('ملاحظة الى السيد المدير المفوض')
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    amount_paid = fields.Monetary('مبلغا وقدره', currency_field='currency_id', tracking=True)
    amount_due = fields.Monetary('مجموع المستحقات', currency_field='currency_id', compute='_compute_amount_due', store=True)
    receipt_date = fields.Date('التاريخ')
    witness1 = fields.Char('الشاهد الاول')
    witness2 = fields.Char('الشاهد الثاني')
    state = fields.Selection([
        ('draft', 'مسودة'), ('clearing', 'براءة الذمة من الاقسام'), ('settled', 'تمت تسوية المستحقات'),
        ('hr_cert', 'مصادقة الموارد البشرية'), ('done', 'معتمد من المدير المفوض'), ('cancel', 'ملغاة'),
    ], default='draft', tracking=True, copy=False, string='الحالة')
    all_signed = fields.Boolean(compute='_compute_all_signed', string='اكتملت التواقيع')

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
                raise UserError(self.env._('يجب ان يوقع كل قسم على سطره قبل تسوية المستحقات.'))
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
    _description = 'توقيع القسم على براءة الذمة'
    _order = 'sequence, id'

    clearance_id = fields.Many2one('ad.clearance', required=True, ondelete='cascade', string='براءة الذمة')
    sequence = fields.Integer(default=10, string='التسلسل')
    department = fields.Selection(DEPARTMENTS, required=True, string='القسم')
    manager_name = fields.Char('اسم مدير القسم')
    has_liability = fields.Boolean('ذمة مشغولة')
    note = fields.Char('الملاحظات')
    signed_user_id = fields.Many2one('res.users', string='وقّع بواسطة', readonly=True)
    signed_date = fields.Date('تاريخ التوقيع', readonly=True)

    def action_sign(self):
        for line in self:
            if not self.env.user.has_group(DEPT_GROUPS[line.department]):
                raise UserError(self.env._('غير مسموح لك بالتوقيع عن هذا القسم.'))
            line.write({'signed_user_id': self.env.uid, 'signed_date': fields.Date.context_today(self),
                        'manager_name': line.manager_name or self.env.user.name})
            line.clearance_id.message_post(body=self.env._(
                'تمت براءة الذمة من %(dept)s بواسطة %(user)s', dept=dict(DEPARTMENTS)[line.department], user=self.env.user.name))


class AdClearanceDue(models.Model):
    _name = 'ad.clearance.due'
    _description = 'مستحقات'
    _order = 'sequence, id'

    clearance_id = fields.Many2one('ad.clearance', required=True, ondelete='cascade', string='براءة الذمة')
    sequence = fields.Integer(default=10, string='التسلسل')
    name = fields.Char('الوصف', required=True)
    currency_id = fields.Many2one('res.currency', related='clearance_id.currency_id')
    amount = fields.Monetary(currency_field='currency_id', string='المبلغ')
