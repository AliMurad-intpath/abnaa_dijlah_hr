from odoo import api, models


class AdDashboard(models.AbstractModel):
    _inherit = 'ad.dashboard'

    @api.model
    def get_data(self, edit=False):
        res = super().get_data(edit=edit)
        if res['show'].get('kpi_approvals') and self._ok('approval.approver'):
            domain = [('user_id', '=', self.env.uid), ('status', '=', 'pending')]
            res['kpis'].append({
                'key': 'approvals', 'label': 'موافقات بانتظاري',
                'value': self.env['approval.approver'].search_count(domain),
                'icon': 'check-user', 'kind': 'kpi', 'model': 'approval.approver', 'domain': domain,
            })
        return res


class AdDashboardBlock(models.Model):
    _inherit = 'ad.dashboard.block'

    @api.model
    def _all_keys(self):
        return super()._all_keys() | {'kpi_approvals'}
