import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Write the Arabic terms straight into the database (the normal import skipped the newer ones)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        from odoo.addons.abnaa_dijlah_hr.models.ad_translate import apply_arabic
        apply_arabic(env)
    except Exception:
        _logger.exception('Could not write the Arabic terms of abnaa_dijlah_hr')
