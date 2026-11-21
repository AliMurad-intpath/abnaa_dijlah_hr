import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

FORMS = ('ad.appointment.order', 'ad.onboarding', 'ad.transfer', 'ad.discipline', 'ad.termination.order',
         'ad.clearance', 'ad.interview', 'ad.employee.guarantee', 'ad.employee.pledge')


def migrate(cr, version):
    """Fill the single status (draft / pending / approved / rejected / cancelled) of the forms that already exist."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for name in FORMS:
        try:
            records = env[name].with_context(active_test=False).search([])
            records.modified(['state', 'ad_state'])
            records.flush_recordset()
        except Exception:
            _logger.exception('Could not compute the status of %s', name)
