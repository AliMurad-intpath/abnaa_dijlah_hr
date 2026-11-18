from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError

# model -> when the request may be sent, which methods run once it is approved,
# and the signature slots printed on the form (the last approver takes the last slot).
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


class AdApprovalMixin(models.AbstractModel):
    _inherit = 'ad.approval.mixin'

    ad_approval_request_id = fields.Many2one('approval.request', 'طلب الموافقة', copy=False, readonly=True,
                                             ondelete='set null', index=True)
    ad_approval_status = fields.Selection(related='ad_approval_request_id.request_status',
                                          string='حالة طلب الموافقة')

    # ---- guard -----------------------------------------------------------
    def _ad_before_final(self):
        res = super()._ad_before_final()
        if (not self.env.context.get('ad_approval_sync') and self._name in PLAN
                and self.env.company.ad_use_approvals):
            raise UserError(self.env._('الموافقة النهائية تتم عبر تطبيق الموافقات. اضغط "طلب موافقة" في الاستمارة.'))
        return res

    # ---- approval type ----------------------------------------------------
    def _ad_category(self):
        Category = self.env['approval.category'].sudo()
        category = Category.search([('ad_model', '=', self._name)], limit=1)
        if not category:
            vals = {'name': 'موافقة: %s' % self._description, 'ad_model': self._name}
            if 'approver_sequence' in Category._fields:
                vals['approver_sequence'] = True
            category = Category.create(vals)
        return category

    # ---- actions ------------------------------------------------------------
    def action_ad_request_approval(self):
        self.ensure_one()
        plan = PLAN.get(self._name)
        if not plan:
            raise UserError(self.env._('هذه الاستمارة لا تدعم طلبات الموافقة.'))
        if self.state not in plan['states']:
            raise UserError(self.env._('لا يمكن ارسال طلب موافقة في الحالة الحالية.'))
        current = self.ad_approval_request_id
        if current and current.request_status in ('new', 'pending', 'approved'):
            raise UserError(self.env._('يوجد طلب موافقة قائم لهذه الاستمارة.'))
        employee = getattr(self, 'employee_id', False)
        if not employee or employee._name != 'hr.employee':
            employee = False
        request = self.env['approval.request'].sudo().create({
            'name': '%s - %s' % (self._description, self.name),
            'category_id': self._ad_category().id,
            'request_owner_id': self.env.user.id,
            'reason': escape(self.display_name),
            'ad_res_model': self._name,
            'ad_res_id': self.id,
            'ad_employee_id': employee.id if employee else False,
        })
        request.action_confirm()
        self.ad_approval_request_id = request
        request.message_post(body=Markup('الاستمارة: <a href="#" data-oe-model="%s" data-oe-id="%s">%s</a>') % (
            self._name, self.id, self.display_name))
        self.message_post(body=self.env._('تم ارسال طلب موافقة: %s', request.name))
        request._ad_sync()   # in case the request was approved right away
        return self.action_ad_open_approval()

    def action_ad_open_approval(self):
        self.ensure_one()
        if not self.ad_approval_request_id:
            return False
        return {
            'type': 'ir.actions.act_window', 'res_model': 'approval.request',
            'res_id': self.ad_approval_request_id.id, 'views': [[False, 'form']], 'target': 'current',
        }

    # ---- outcome ----------------------------------------------------------------
    def _ad_apply_approved(self, request):
        plan = PLAN[self._name]
        rec = self.sudo().with_context(ad_skip_group_check=True, ad_approval_sync=True)
        for method in plan['run']:
            getattr(rec, method)()
        approvers = request.approver_ids.filtered(lambda a: a.status == 'approved')
        approvers = approvers.sorted(lambda a: (getattr(a, 'sequence', 0) or 0, a.write_date or fields.Datetime.now(), a.id))
        mapped = {}
        for key, approver in zip(reversed(plan['keys']), reversed(list(approvers))):
            mapped[key] = approver
        Signature = self.env['ad.signature'].sudo()
        for key in plan['keys']:
            existing = rec.signature_ids.filtered(lambda s: s.step == key)
            approver = mapped.get(key)
            if not approver:
                existing.unlink()
                continue
            vals = {'user_id': approver.user_id.id, 'date': fields.Date.context_today(self)}
            if existing:
                existing.write(vals)
            else:
                Signature.create(dict(vals, res_model=self._name, res_id=self.id, step=key))
        rec.message_post(body=self.env._('تمت الموافقة على الاستمارة عبر طلب الموافقة %s.', request.name))

    def _ad_apply_refused(self, request):
        self.sudo().message_post(body=self.env._('لم تتم الموافقة على طلب الموافقة %s (الحالة: %s). يمكن تعديل الاستمارة وارسال طلب جديد.',
                                                request.name, request.request_status))
