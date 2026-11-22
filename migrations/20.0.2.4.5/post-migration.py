from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """One-time: put the approval dates over the printed "202 / /", centre the AM/PM marks, add supervisor names."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ad.form.template']._ad_apply_signature_layouts(force=True)
