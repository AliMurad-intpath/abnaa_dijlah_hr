import base64
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Transfer form: the HR signature sat on the empty second page. Put it in the HR block of page 1 and
    remove the empty page from the stored template (and from steps that are still running)."""
    import pymupdf
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ad.form.template']._ad_apply_signature_layouts()
    # steps that are still running keep their own copy of the signature box: move them too
    Step = env['ad.form.step'].sudo()
    for step in Step.search([('state', 'in', ('pending', 'waiting')), ('signature_y', '>', 771)]):
        stage = step.stage_id
        if stage and abs(stage.signature_y - 771.89) > 0.6:
            step.write({'signature_page': stage.signature_page, 'signature_x': stage.signature_x,
                        'signature_y': stage.signature_y, 'signature_width': stage.signature_width,
                        'signature_height': stage.signature_height})

    tpl = env['ad.form.template'].sudo().search([('res_model', '=', 'ad.transfer')], limit=1)
    if not tpl:
        return
    try:
        with env.cr.savepoint():
            stage_hr = tpl.stage_ids.filtered(lambda s: s.key == 'hr')
            if stage_hr:
                steps = env['ad.form.step'].sudo().search([
                    ('res_model', '=', 'ad.transfer'), ('key', '=', 'hr'), ('signature_page', '=', 2)])
                steps.write({'signature_page': stage_hr.signature_page, 'signature_x': stage_hr.signature_x,
                             'signature_y': stage_hr.signature_y, 'signature_width': stage_hr.signature_width,
                             'signature_height': stage_hr.signature_height})
            data = tpl._get_pdf_bytes()
            on_page_2 = tpl.field_ids.filtered(lambda f: f.page == 2) or tpl.stage_ids.filtered(
                lambda s: s.print_signature and s.signature_page == 2)
            still_used = env['ad.form.step'].sudo().search_count([
                ('res_model', '=', 'ad.transfer'), ('signature_page', '=', 2), ('state', 'in', ('pending', 'waiting'))])
            if data and not on_page_2 and not still_used:
                with pymupdf.open(stream=data, filetype='pdf') as doc:
                    if len(doc) == 2:
                        doc.delete_page(1)
                        out = doc.tobytes(garbage=3, deflate=True)
                        tpl.with_context(ad_engine_seed=True).write({
                            'template_filename': tpl.template_filename or 'transfer.pdf',
                            'template_pdf': base64.b64encode(out)})
    except Exception:
        _logger.exception('Could not tidy the transfer form template')
