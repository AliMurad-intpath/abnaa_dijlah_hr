from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """The 'My pending approvals' menu action must run for every internal user, not only for HR managers."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    action = env.ref('abnaa_dijlah_hr.ad_form_step_my_action', raise_if_not_found=False)
    if action:
        action.group_ids = [(4, env.ref('base.group_user').id)]
