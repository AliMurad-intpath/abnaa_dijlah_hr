from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Re-run the page re-flow: 2.2.0 skipped forms whose signature pages no longer existed."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ad.form.template']._ad_reflow_layouts()
