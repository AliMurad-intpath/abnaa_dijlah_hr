import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import BinaryBytes

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Move the signature PNGs from the employees to their users (a user keeps the one he already has)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    moved = 0
    employees = env['hr.employee'].with_context(active_test=False).search([('user_id', '!=', False), ('document_signature', '!=', False)])
    for emp in employees:
        user = emp.user_id
        if not user.ad_signature:
            try:
                user.ad_signature = BinaryBytes(emp.document_signature.content, filename='signature.png')
                user.ad_signature_filename = emp.document_signature_filename
                moved += 1
            except Exception:
                _logger.exception('signature of %s was not moved to the user', emp.name)
    _logger.info('abnaa_dijlah_hr: %s signatures moved from employees to users', moved)
