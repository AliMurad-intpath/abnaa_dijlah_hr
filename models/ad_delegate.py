from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AdApproverDelegate(models.Model):
    """A substitute approver while someone is away: the substitute may decide everything the absent user may decide."""
    _name = 'ad.approver.delegate'
    _description = 'Substitute approver'
    _order = 'date_from desc, id desc'

    user_id = fields.Many2one('res.users', 'Absent approver', required=True, default=lambda self: self.env.user,
                              domain="[('share', '=', False)]", index=True)
    substitute_id = fields.Many2one('res.users', 'Substitute', required=True, domain="[('share', '=', False)]", index=True)
    date_from = fields.Date('From', required=True, default=fields.Date.context_today)
    date_to = fields.Date('To', required=True)
    reason = fields.Char('Reason')
    active = fields.Boolean(default=True)
    on_duty = fields.Boolean('Active today', compute='_compute_on_duty')

    @api.constrains('user_id', 'substitute_id', 'date_from', 'date_to')
    def _check_delegate(self):
        for rec in self:
            if rec.user_id == rec.substitute_id:
                raise ValidationError(self.env._('The substitute must be another user.'))
            if rec.date_to < rec.date_from:
                raise ValidationError(self.env._('The end date cannot be before the start date.'))

    @api.depends('date_from', 'date_to', 'active')
    def _compute_on_duty(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.on_duty = bool(rec.active and rec.date_from and rec.date_to and rec.date_from <= today <= rec.date_to)

    # ---------------------------------------------------------------- lookups (always sudo: the rows belong to other users)
    @api.model
    def _active_rows(self, today_only=True):
        domain = [('active', '=', True)]
        if today_only:
            today = fields.Date.context_today(self)
            domain += [('date_from', '<=', today), ('date_to', '>=', today)]
        return self.sudo().search(domain)

    @api.model
    def _acting_users(self, user):
        """The user plus everybody who is away today and named this user as the substitute."""
        rows = self._active_rows().filtered(lambda r: r.substitute_id == user)
        return user | rows.user_id

    @api.model
    def _substitutes_of(self, users, today_only=False):
        rows = self._active_rows(today_only).filtered(lambda r: r.user_id in users)
        return rows.substitute_id

    @api.model
    def _group_ids(self, users):
        ids = set()
        for user in users.sudo():
            groups = user.all_group_ids if 'all_group_ids' in user._fields else user.group_ids
            ids.update(groups.ids)
        return list(ids)

    # ---------------------------------------------------------------- keep the access lists of open forms in step
    def _ad_refresh_open_forms(self):
        from .ad_chain import FINAL_STATES
        for model in FINAL_STATES:
            if model not in self.env:
                continue
            for rec in self.env[model].sudo().search([('ad_state', '=', 'pending')]):
                rec._compute_ad_approver_user_ids()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ad_refresh_open_forms()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._ad_refresh_open_forms()
        return res

    def unlink(self):
        res = super().unlink()
        self.env['ad.approver.delegate']._ad_refresh_open_forms()
        return res
