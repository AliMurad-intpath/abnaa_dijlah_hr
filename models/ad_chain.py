import copy
import logging
from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import BinaryBytes

_logger = logging.getLogger(__name__)


def _engine():
    from .. import pdf_engine
    return pdf_engine


# model -> state(s) in which the request may be sent, the methods that run once the
# whole chain approved the request, and the signature slots recorded for the form.
PLAN = {
    'ad.appointment.order': {'states': ('draft',), 'run': ['action_submit', 'action_approve'], 'keys': ['hr', 'md']},
    'ad.onboarding': {'states': ('draft',), 'run': ['action_hr', 'action_logistics', 'action_site', 'action_ops', 'action_done'],
                      'keys': ['hr', 'logistics', 'site', 'ops', 'md']},
    'ad.transfer': {'states': ('draft',), 'run': ['action_ops', 'action_site', 'action_hr', 'action_done'],
                    'keys': ['ops', 'ops_site', 'hr', 'md']},
    'ad.discipline': {'states': ('draft',), 'run': ['action_hr', 'action_ops', 'action_approve'], 'keys': ['hr', 'ops', 'md']},
    'ad.termination.order': {'states': ('draft',), 'run': ['action_submit', 'action_approve'], 'keys': ['hr', 'md']},
    'ad.clearance': {'states': ('hr_cert',), 'run': ['action_md_approve'], 'keys': ['md']},
    'ad.interview': {'states': ('draft',), 'run': ['action_hr', 'action_ops', 'action_done'], 'keys': ['hr', 'ops', 'hr_manager']},
}


class AdFormStep(models.Model):
    """One approval step of one form (a copy of the stage taken when the request was sent)."""
    _name = 'ad.form.step'
    _description = 'خطوة موافقة على استمارة'
    _order = 'res_model, res_id, sequence, id'

    res_model = fields.Char(required=True, index=True, string='نموذج السجل')
    res_id = fields.Many2oneReference(model_field='res_model', required=True, index=True, string='معرف السجل')
    record_name = fields.Char('الاستمارة', compute='_compute_record_name')
    stage_id = fields.Many2one('ad.form.stage', readonly=True, ondelete='set null', string='المرحلة')
    key = fields.Char('رمز التوقيع')
    sequence = fields.Integer('الترتيب')
    name = fields.Char('الخطوة', required=True)
    approver_id = fields.Many2one('res.users', 'المعتمد', ondelete='restrict')
    group_id = fields.Many2one('res.groups', 'مجموعة المعتمدين', ondelete='restrict')
    state = fields.Selection([('waiting', 'بانتظار الدور'), ('pending', 'بانتظار الموافقة'),
                              ('approved', 'تمت الموافقة'), ('rejected', 'مرفوضة')], default='waiting',
                             required=True, string='الحالة', index=True)
    action_date = fields.Datetime('تاريخ القرار', readonly=True)
    signed_by_id = fields.Many2one('res.users', 'اعتمد بواسطة', readonly=True)
    signed_by_name = fields.Char('اسم المعتمد', readonly=True)
    note = fields.Text('ملاحظة / سبب الرفض', readonly=True)
    signature_snapshot = fields.Binary(attachment=True, readonly=True)
    print_signature = fields.Boolean()
    signature_page = fields.Integer()
    signature_x = fields.Float()
    signature_y = fields.Float()
    signature_width = fields.Float()
    signature_height = fields.Float()
    pending_since = fields.Datetime('بانتظار منذ', readonly=True)
    last_reminder = fields.Datetime('اخر تذكير', readonly=True)
    approver_label = fields.Char('المعتمد', compute='_compute_approver_label')

    @api.depends('approver_id', 'group_id', 'signed_by_name')
    def _compute_approver_label(self):
        for step in self:
            step.approver_label = step.signed_by_name or step.approver_id.name or step.group_id.name or ''

    def _compute_record_name(self):
        for step in self:
            rec = self.env[step.res_model].sudo().browse(step.res_id).exists() if step.res_model in self.env else False
            step.record_name = rec.display_name if rec else ''

    def action_open_record(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': self.res_model, 'res_id': self.res_id,
                'views': [[False, 'form']], 'target': 'current'}

    def _eligible_users(self):
        self.ensure_one()
        if self.approver_id:
            return self.approver_id
        if self.group_id:
            group = self.group_id.sudo()
            users = group.all_user_ids if 'all_user_ids' in group._fields else group.user_ids
            return users.filtered(lambda u: u.active and not u.share)
        return self.env['res.users']

    def _user_may_act(self, user):
        self.ensure_one()
        if self.approver_id:
            return self.approver_id == user
        return bool(self.group_id) and self.group_id in (user.all_group_ids if 'all_group_ids' in user._fields else user.group_ids)

    @api.model
    def _pending_domain(self, user=None):
        user = user or self.env.user
        groups = (user.all_group_ids if 'all_group_ids' in user._fields else user.group_ids).ids
        return [('state', '=', 'pending'), '|', ('approver_id', '=', user.id),
                '&', ('approver_id', '=', False), ('group_id', 'in', groups)]

    # -------------------------------------------------------------- reminders
    @api.model
    def _cron_ad_remind(self):
        """First reminder after N days, then every M days until the step is answered (set on the company).
        One daily summary goes to the HR managers."""
        now = fields.Datetime.now()
        for step in self.sudo().search([('state', '=', 'pending')]):
            rec = self.env[step.res_model].sudo().browse(step.res_id).exists() if step.res_model in self.env else False
            if not rec or rec.ad_state != 'pending':
                continue
            company = rec.company_id or self.env.company
            if not company.ad_reminder_enabled:
                continue
            after = max(company.ad_reminder_after_days, 1)
            repeat = max(company.ad_reminder_repeat_days, 1)
            base = step.pending_since or step.create_date or now
            due = (step.last_reminder + timedelta(days=repeat)) if step.last_reminder else (base + timedelta(days=after))
            if now < due:
                continue
            days = max((now - base).days, 1)
            try:
                partners = step._eligible_users().partner_id
                if partners:
                    rec.message_notify(
                        partner_ids=partners.ids, subject=self.env._('تذكير: استمارة بانتظار موافقتك'),
                        body=Markup('%s <a href="#" data-oe-model="%s" data-oe-id="%s">%s</a> (%s)') % (
                            self.env._('الاستمارة بانتظار قرارك منذ %s يوم:', days), rec._name, rec.id,
                            rec.display_name, step.name))
                step.last_reminder = now
            except Exception:
                _logger.exception('approval reminder failed for %s,%s', step.res_model, step.res_id)
        self._ad_send_daily_summary(now)

    @api.model
    def _ad_send_daily_summary(self, now):
        today = fields.Date.to_date(now)
        steps = self.sudo().search([('state', '=', 'pending')])
        if not steps:
            return
        by_company = {}
        for step in steps:
            rec = self.env[step.res_model].sudo().browse(step.res_id).exists() if step.res_model in self.env else False
            if not rec:
                continue
            company = rec.company_id or self.env.company
            if not (company.ad_reminder_enabled and company.ad_reminder_summary):
                continue
            if company.sudo().ad_last_summary == today:
                continue
            by_company.setdefault(company, []).append(
                Markup('<li><a href="#" data-oe-model="%s" data-oe-id="%s">%s</a> — %s (%s)</li>') % (
                    rec._name, rec.id, rec.display_name, step.name, step.approver_label or '-'))
        managers = self.env.ref('hr.group_hr_manager').sudo()
        users = managers.all_user_ids if 'all_user_ids' in managers._fields else managers.user_ids
        for company, rows in by_company.items():
            partners = users.filtered(lambda u: company in u.company_ids).partner_id
            if not partners:
                continue
            body = Markup('<p>%s</p><ul>%s</ul>') % (
                self.env._('استمارات ما زالت بانتظار المعتمدين: %s', len(rows)), Markup('').join(rows))
            self.env['res.partner'].sudo().browse(partners.ids[:1]).message_notify(
                partner_ids=partners.ids, subject=self.env._('ملخص يومي: موافقات معلقة'), body=body)
            company.sudo().ad_last_summary = today


class AdApprovalMixin(models.AbstractModel):
    _inherit = 'ad.approval.mixin'

    ad_state = fields.Selection([('none', 'لم ترسل'), ('pending', 'بانتظار الموافقة'),
                                 ('approved', 'تمت الموافقة'), ('rejected', 'مرفوضة')],
                                default='none', copy=False, readonly=True, string='سلسلة الموافقات', index=True)
    ad_step_ids = fields.One2many('ad.form.step', 'res_id', string='خطوات الموافقة', copy=False,
                                  domain=lambda self: [('res_model', '=', self._name)])
    ad_layout_snapshot = fields.Json(copy=False, readonly=True)
    ad_reject_note = fields.Text('سبب الرفض', copy=False, readonly=True)
    ad_approver_user_ids = fields.Many2many('res.users', string='المعتمدون المعنيون', compute='_compute_ad_approver_user_ids',
                                            store=True, copy=False, compute_sudo=True)
    ad_can_approve = fields.Boolean(compute='_compute_ad_can_approve')
    ad_waiting_for = fields.Char('بانتظار', compute='_compute_ad_can_approve')

    @api.depends('ad_state', 'ad_step_ids.state', 'ad_step_ids.approver_id', 'ad_step_ids.group_id')
    @api.depends_context('uid')
    def _compute_ad_can_approve(self):
        for rec in self:
            step = rec._ad_pending_step()
            rec.ad_can_approve = bool(step and rec.ad_state == 'pending' and step._user_may_act(self.env.user))
            rec.ad_waiting_for = (step.approver_label or step.name) if step and rec.ad_state == 'pending' else False

    @api.depends('ad_step_ids.approver_id', 'ad_step_ids.group_id', 'ad_step_ids.state')
    def _compute_ad_approver_user_ids(self):
        for rec in self:
            users = self.env['res.users']
            for step in rec.sudo().ad_step_ids.filtered(lambda s: s.state in ('waiting', 'pending')):
                users |= step._eligible_users()
            rec.ad_approver_user_ids = users

    # ------------------------------------------------------------------ helpers
    def _ad_pending_step(self):
        self.ensure_one()
        return self.sudo().ad_step_ids.filtered(lambda s: s.state == 'pending')[:1]

    def _ad_step_for_stage(self, stage):
        self.ensure_one()
        return self.sudo().ad_step_ids.filtered(lambda s: s.stage_id == stage)[:1]

    def _ad_chain_active(self):
        """True when this form goes through the approval chain."""
        return bool(self._name in PLAN and self.env.company.ad_use_approvals and self.ad_tpl().sudo().stage_ids)

    def _ad_before_final(self):
        res = super()._ad_before_final()
        if not self.env.context.get('ad_approval_sync') and self._name in PLAN:
            for rec in self:
                if rec._ad_chain_active():
                    raise UserError(self.env._('الموافقة النهائية تتم عبر سلسلة الموافقات. اضغط "ارسال للموافقة" في الاستمارة.'))
        return res

    # ------------------------------------------------------------------ printing data
    def _ad_layout_defs(self):
        """Printed fields as plain dicts (taken from the template, or the frozen snapshot)."""
        self.ensure_one()
        if self.ad_layout_snapshot and self.ad_state != 'none':
            return copy.deepcopy(self.ad_layout_snapshot['fields'])
        defs = []
        for f in self.ad_tpl().sudo().field_ids:
            defs.append({'id': f.id, 'item': f._pdf_item('')})
        return defs

    def _ad_pdf_items(self, check=False):
        self.ensure_one()
        tpl = self.ad_tpl().sudo()
        rec = self.with_context(lang=self.env.user.lang)
        fields_by_id = {f.id: f for f in tpl.field_ids}
        items = []
        for entry in self._ad_layout_defs():
            item = dict(entry['item'])
            field = fields_by_id.get(entry['id'])
            if field:
                item['text'] = field._print_value(rec)
            items.append(item)
        if check:
            for stage in tpl.stage_ids.filtered('print_signature'):
                items.append(stage._pdf_signature_item(False))
        else:
            for step in self.sudo().ad_step_ids:
                if step.state == 'approved' and step.print_signature and step.signature_snapshot:
                    items.append({'key': 'step-%s' % step.id, 'label': step.name, 'kind': 'image',
                                  'image': step.signature_snapshot.content, 'page': step.signature_page,
                                  'x': step.signature_x, 'y': step.signature_y, 'width': step.signature_width,
                                  'height': step.signature_height})
        return items

    def _ad_layout_error(self, issues):
        lines = ['• %s: %s' % (issue['label'], issue['message']) for issue in issues]
        return UserError(self.env._('لا يمكن للقالب استيعاب هذه القيم. عدّل الصناديق في مصمم الاستمارة '
                                    '(صندوق اكبر او خط اصغر او عدة اسطر) او اختصر القيمة:\n%s', '\n'.join(lines)))

    def _ad_render_pdf(self):
        self.ensure_one()
        self.check_access('read')
        tpl = self.ad_tpl().sudo()
        data = tpl._get_pdf_bytes()
        if not data:
            raise UserError(self.env._('لا يوجد ملف PDF لهذه الاستمارة. ارفعه من: الاعداد > قوالب الاستمارات.'))
        pdf, _issues = _engine().render(data, self._ad_pdf_items(), collect=True)
        return pdf

    def action_ad_print(self):
        self.env['ad.dashboard.block']._check_form_access(self._name)
        ids = ','.join(str(i) for i in self.ids)
        return {'type': 'ir.actions.act_url', 'url': '/abnaa_dijlah_hr/print/%s/%s' % (self._name, ids), 'target': 'new'}

    # ------------------------------------------------------------------ chain
    def _ad_notify_step(self, step):
        """Todo activity for the user(s) who must decide (specific user only; groups get a notification)."""
        self.ensure_one()
        rec = self.sudo()
        summary = self.env._('موافقة: %s', step.name)
        users = step._eligible_users()
        if not users:
            return
        if 'activity_schedule' in rec._fields or hasattr(rec, 'activity_schedule'):
            for user in users[:10]:
                try:
                    rec.activity_schedule('mail.mail_activity_data_todo', user_id=user.id, summary=summary,
                                          note=self.env._('راجع الاستمارة ووافق عليها او ارفضها.'),
                                          date_deadline=fields.Date.context_today(self))
                except Exception:
                    _logger.exception('could not schedule the approval activity')
        if hasattr(rec, 'message_notify') and not step.approver_id:
            rec.message_notify(partner_ids=users.partner_id.ids, subject=summary,
                               body=Markup('%s <a href="#" data-oe-model="%s" data-oe-id="%s">%s</a>') % (
                                   self.env._('استمارة بانتظار موافقتك:'), rec._name, rec.id, rec.display_name))

    def _ad_close_activities(self, step, feedback=None):
        self.ensure_one()
        summary = self.env._('موافقة: %s', step.name)
        rec = self.sudo()
        if not hasattr(rec, 'activity_ids'):
            return
        acts = rec.activity_ids.filtered(lambda a: a.summary == summary)
        if feedback:
            for act in acts:
                act.sudo().action_feedback(feedback=feedback)
        else:
            acts.sudo().unlink()

    def _ad_post(self, body):
        rec = self.sudo()
        if hasattr(rec, 'message_post'):
            rec.message_post(body=body)

    def action_ad_submit(self):
        for rec in self:
            plan = PLAN.get(rec._name)
            if not plan:
                raise UserError(self.env._('هذه الاستمارة لا تدعم سلسلة الموافقات.'))
            if rec.state not in plan['states']:
                raise UserError(self.env._('لا يمكن ارسال الاستمارة للموافقة في حالتها الحالية.'))
            if rec.ad_state == 'pending' or rec.ad_state == 'approved':
                raise UserError(self.env._('الاستمارة مرسلة مسبقا للموافقة.'))
            tpl = rec.ad_tpl().sudo()
            stages = tpl.stage_ids.sorted(lambda s: (s.sequence, s.id))
            if not stages:
                raise UserError(self.env._('لم تضبط مراحل الموافقة لهذه الاستمارة. افتح: الاعداد > قوالب الاستمارات.'))
            for stage in stages:
                if not stage._eligible_check():
                    raise UserError(self.env._('المرحلة "%s" ليس فيها اي مستخدم فعال. حدد المعتمد من قوالب الاستمارات.', stage.name))
            data = tpl._get_pdf_bytes()
            if not data:
                raise UserError(self.env._('لا يوجد ملف PDF لهذه الاستمارة. ارفعه من قوالب الاستمارات.'))
            _pdf, issues = _engine().render(data, rec._ad_pdf_items(check=True), collect=True, output=False)
            if issues:
                raise rec._ad_layout_error(issues)
            now = fields.Datetime.now()
            snapshot = {'version': 1, 'fields': [{'id': f.id, 'item': f._pdf_item('')} for f in tpl.field_ids]}
            old = rec.sudo().ad_step_ids
            for step in old.filtered(lambda s: s.state == 'pending'):
                rec._ad_close_activities(step)
            old.unlink()
            Step = self.env['ad.form.step'].sudo()
            for i, stage in enumerate(stages):
                Step.create({
                    'res_model': rec._name, 'res_id': rec.id, 'stage_id': stage.id, 'key': stage.key,
                    'sequence': stage.sequence, 'name': stage.name, 'approver_id': stage.approver_id.id,
                    'group_id': stage.group_id.id, 'print_signature': stage.print_signature,
                    'signature_page': stage.signature_page, 'signature_x': stage.signature_x,
                    'signature_y': stage.signature_y, 'signature_width': stage.signature_width,
                    'signature_height': stage.signature_height,
                    'state': 'pending' if i == 0 else 'waiting', 'pending_since': now if i == 0 else False,
                })
            rec.sudo().write({'ad_state': 'pending', 'ad_layout_snapshot': snapshot, 'ad_reject_note': False})
            rec.invalidate_recordset(['ad_step_ids'])
            rec._ad_notify_step(rec._ad_pending_step())
            rec._ad_post(self.env._('تم ارسال الاستمارة للموافقة (%s مراحل).', len(stages)))
        return True

    def _ad_current_step_for_user(self):
        self.ensure_one()
        if self.ad_state != 'pending':
            raise UserError(self.env._('الاستمارة ليست بانتظار الموافقة (قد تكون عولجت مسبقا).'))
        step = self._ad_pending_step()
        if not step or not step._user_may_act(self.env.user):
            if self.sudo().ad_step_ids.filtered(lambda s: s.state == 'approved' and s.signed_by_id == self.env.user):
                raise UserError(self.env._('وافقت على هذه الاستمارة مسبقا.'))
            raise AccessError(self.env._('لست المعتمد الحالي لهذه الاستمارة.'))
        return step

    def _ad_lock(self):
        if self.ids:
            self.env.cr.execute('SELECT id FROM %s WHERE id IN %%s ORDER BY id FOR UPDATE' % self._table, (tuple(self.ids),))
            self.invalidate_recordset(['ad_state', 'ad_step_ids'])
            self.mapped('ad_step_ids').invalidate_recordset(['state'])

    def action_ad_approve(self):
        self._ad_lock()
        for rec in self:
            step = rec._ad_current_step_for_user()
            employee = self.env['hr.employee'].sudo().search(
                [('user_id', '=', self.env.uid), ('company_id', '=', rec.company_id.id)], limit=1)
            signature = employee.document_signature if step.print_signature else False
            step.sudo().write({
                'state': 'approved', 'action_date': fields.Datetime.now(), 'signed_by_id': self.env.uid,
                'signed_by_name': employee.name or self.env.user.name,
                'signature_snapshot': BinaryBytes(signature.content, filename='signature.png') if signature else False,
            })
            rec._ad_close_activities(step, self.env._('تمت الموافقة.'))
            rec._ad_record_signature(step)
            following = rec.sudo().ad_step_ids.filtered(lambda s: s.state == 'waiting').sorted(lambda s: (s.sequence, s.id))[:1]
            if following:
                following.sudo().write({'state': 'pending', 'pending_since': fields.Datetime.now(), 'last_reminder': False})
                rec._ad_notify_step(following)
                rec._ad_post(self.env._('وافق %(user)s على مرحلة "%(step)s". الدور الان: %(next)s.',
                                        user=self.env.user.name, step=step.name, next=following.name))
            else:
                rec._ad_apply_approved()
                rec.sudo().write({'ad_state': 'approved'})
                rec._ad_post(self.env._('اكتملت جميع مراحل الموافقة بموافقة %s.', self.env.user.name))
        return True

    def action_ad_reject(self):
        self.ensure_one()
        step = self._ad_current_step_for_user()
        return {'type': 'ir.actions.act_window', 'res_model': 'ad.form.reject.wizard', 'view_mode': 'form', 'target': 'new',
                'context': {'default_res_model': self._name, 'default_res_id': self.id, 'default_step_name': step.name}}

    def _ad_do_reject(self, note):
        self._ad_lock()
        for rec in self:
            step = rec._ad_current_step_for_user()
            step.sudo().write({'state': 'rejected', 'action_date': fields.Datetime.now(), 'note': note,
                               'signed_by_id': self.env.uid, 'signed_by_name': self.env.user.name})
            rec._ad_close_activities(step, self.env._('رُفضت الاستمارة.'))
            rec.sudo().write({'ad_state': 'rejected', 'ad_reject_note': note})
            rec._ad_post(Markup('%s <b>%s</b>: %s') % (self.env._('رفض %s الاستمارة في مرحلة', self.env.user.name),
                                                       escape(step.name), escape(note or '')))
            owner = rec.create_uid
            if owner and hasattr(rec.sudo(), 'message_notify') and owner != self.env.user:
                rec.sudo().message_notify(partner_ids=owner.partner_id.ids,
                                          subject=self.env._('رُفضت الاستمارة %s', rec.display_name),
                                          body=Markup('%s %s') % (self.env._('سبب الرفض:'), escape(note or '-')))
        return True

    def action_ad_cancel_request(self):
        self._ad_lock()
        for rec in self:
            if rec.ad_state != 'pending':
                raise UserError(self.env._('لا يوجد طلب موافقة قائم لسحبه.'))
            if not (self.env.user == rec.create_uid or self.env.user.has_group('abnaa_dijlah_hr.group_ad_hr_manager')
                    or self.env.is_superuser()):
                raise AccessError(self.env._('يسحب الطلب من انشأ الاستمارة او مدير الموارد البشرية فقط.'))
            for step in rec.sudo().ad_step_ids:
                rec._ad_close_activities(step)
            rec.sudo().ad_step_ids.unlink()
            rec.sudo().write({'ad_state': 'none', 'ad_layout_snapshot': False})
            rec._ad_post(self.env._('سحب %s طلب الموافقة.', self.env.user.name))
        return True

    # ------------------------------------------------------------------ outcome
    def _ad_record_signature(self, step):
        """Keep the approvals tab (ad.signature) in step with the chain."""
        self.ensure_one()
        if not step.key:
            return
        Signature = self.env['ad.signature'].sudo()
        existing = self.sudo().signature_ids.filtered(lambda s: s.step == step.key)
        vals = {'user_id': step.signed_by_id.id or self.env.uid,
                'date': fields.Datetime.context_timestamp(self, step.action_date).date() if step.action_date
                else fields.Date.context_today(self)}
        if existing:
            existing.write(vals)
        else:
            Signature.create(dict(vals, res_model=self._name, res_id=self.id, step=step.key))

    def _ad_apply_approved(self):
        """Run the form's own workflow steps once the chain has approved it."""
        self.ensure_one()
        plan = PLAN[self._name]
        rec = self.sudo().with_context(ad_skip_group_check=True, ad_approval_sync=True)
        for method in plan['run']:
            getattr(rec, method)()
        for step in self.sudo().ad_step_ids.filtered(lambda s: s.state == 'approved'):
            self._ad_record_signature(step)
