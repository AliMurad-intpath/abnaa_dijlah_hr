from odoo import api, fields, models
from odoo.exceptions import UserError


class AdApprovalMixin(models.AbstractModel):
    _name = 'ad.approval.mixin'
    _description = 'موافقات الاستمارات'

    _ad_seq_code = None
    _ad_form_xmlid = None

    name = fields.Char('الرقم', copy=False, readonly=True, default='/', index=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True, string='الشركة')
    signature_ids = fields.One2many(
        'ad.signature', 'res_id', string='الموافقات', copy=False,
        domain=lambda self: [('res_model', '=', self._name)])

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self._ad_seq_code and vals.get('name', '/') in ('/', False, ''):
                vals['name'] = self.env['ir.sequence'].next_by_code(self._ad_seq_code) or '/'
        return super().create(vals_list)

    def _ad_before_final(self):
        """Hook called by every final (managing director) action. The Enterprise
        Approvals add-on overrides it to force the final approval through the
        approval request."""
        return True

    def ad_require_group(self, xmlid):
        if self.env.context.get('ad_skip_group_check'):
            return
        if not self.env.user.has_group(xmlid):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            raise UserError(self.env._('هذه الخطوة متاحة فقط لأعضاء المجموعة "%s".',
                                       group.name if group else xmlid))

    def ad_sign(self, step, note=False):
        today = fields.Date.context_today(self)
        for rec in self:
            existing = rec.signature_ids.filtered(lambda s: s.step == step)
            vals = {'user_id': self.env.uid, 'date': today, 'note': note}
            if existing:
                existing.write(vals)
            else:
                self.env['ad.signature'].create(dict(vals, res_model=rec._name, res_id=rec.id, step=step))
        return True

    def ad_sig(self, step):
        self.ensure_one()
        return self.signature_ids.filtered(lambda s: s.step == step)[:1]

    def ad_tpl(self):
        self.ensure_one()
        return self.env.ref(self._ad_form_xmlid, raise_if_not_found=False) or self.env['ad.form.template']
