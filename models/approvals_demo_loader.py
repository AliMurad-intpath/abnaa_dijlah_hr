import logging

from odoo import models

from .ad_approval_bridge import PLAN

_logger = logging.getLogger(__name__)

# signature slot -> demo user (see DEMO_USERS in ad_demo_loader)
SLOT_USER = {'hr': 'hr_manager', 'md': 'md', 'ops': 'ops_manager', 'ops_site': 'site_supervisor',
             'site': 'site_supervisor', 'logistics': 'logistics', 'hr_manager': 'hr_manager'}


class AdDemoLoader(models.TransientModel):
    _inherit = 'ad.demo.loader'

    def action_import(self):
        res = super().action_import()
        try:
            with self.env.cr.savepoint():
                lines = self._demo_approvers()
            self.log = (self.log or '') + '\n' + '\n'.join(lines)
        except Exception as exc:
            _logger.exception('demo approvers failed')
            self.log = (self.log or '') + '\n✗ معتمدو انواع الموافقات : %s' % exc
        return res

    def _demo_approvers(self):
        users = {u.login: u for u in self.env['res.users'].sudo().search([('login', 'like', 'demo.')])}
        by_key = {'hr_manager': 'demo.hr.manager', 'md': 'demo.md', 'ops_manager': 'demo.ops.manager',
                  'site_supervisor': 'demo.site.supervisor', 'logistics': 'demo.logistics'}
        lines = []
        for model_name, plan in PLAN.items():
            cat = self.env['approval.category'].sudo().search([('ad_model', '=', model_name)], limit=1)
            if not cat or cat.approver_ids:
                continue
            vals = []
            for seq, slot in enumerate(plan['keys'], start=1):
                user = users.get(by_key.get(SLOT_USER.get(slot, '')))
                if user:
                    vals.append((0, 0, {'user_id': user.id, 'required': True}))
            if vals:
                write = {'approver_ids': vals, 'approval_minimum': len(vals)}   # all approvers are required
                if 'approver_sequence' in cat._fields:
                    write['approver_sequence'] = True                           # one after the other
                cat.write(write)
                lines.append('✓ معتمدون: %s' % cat.display_name)
        return lines
