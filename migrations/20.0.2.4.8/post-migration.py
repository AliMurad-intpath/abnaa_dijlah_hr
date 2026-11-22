import base64
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

OLD = b'90.625 71.875 2300.0488 3370.8984 re'
NEW = b'0 0 2483 3512 re'


def migrate(cr, version):
    """The paper templates clipped everything at 22 pt from the right edge (the first letter of some lines and the
    right border were cut). Widen the clipping rectangle inside the stored PDFs; a template that was replaced by
    the client with another file is left alone because it does not contain that rectangle."""
    import pymupdf
    env = api.Environment(cr, SUPERUSER_ID, {})
    for tpl in env['ad.form.template'].with_context(active_test=False).search([]):
        try:
            with env.cr.savepoint():
                data = tpl._get_pdf_bytes()
                if not data:
                    continue
                changed = False
                with pymupdf.open(stream=data, filetype='pdf') as doc:
                    for page in doc:
                        for xref in page.get_contents():
                            stream = doc.xref_stream(xref)
                            if stream and OLD in stream:
                                doc.update_stream(xref, stream.replace(OLD, NEW))
                                changed = True
                    if not changed:
                        continue
                    out = doc.tobytes(garbage=3, deflate=True)
                tpl.sudo().with_context(ad_engine_seed=True).write({
                    'template_filename': tpl.template_filename or 'template.pdf',
                    'template_pdf': base64.b64encode(out)})
        except Exception:
            _logger.exception('Could not widen the clipping area of template %s', tpl.display_name)
