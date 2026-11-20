from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Printed values default to the Times New Roman look-alike (Liberation Serif),
    and the blank forms are re-flowed so content fills each page."""
    cr.execute("UPDATE ad_form_field SET font_family = 'times' WHERE font_family IS NULL OR font_family = 'dejavu'")
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ad.form.template']._ad_reflow_layouts()
