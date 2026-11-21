import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Load the Arabic terms of this module again (new screens were not translated after the upgrade)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        codes = [c for c in env['res.lang'].search([('active', '=', True)]).mapped('code') if c.startswith('ar')]
        module = env['ir.module.module'].search([('name', '=', 'abnaa_dijlah_hr')], limit=1)
        if codes and module:
            module._update_translations(filter_lang=codes, overwrite=True)
            _logger.info('Arabic terms of abnaa_dijlah_hr reloaded for %s', codes)
    except Exception:
        _logger.exception('Could not reload the Arabic terms of abnaa_dijlah_hr')
