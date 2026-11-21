from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Re-apply the blank forms with exact tick-box and field positions."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ad.form.template']._ad_reflow_layouts()
