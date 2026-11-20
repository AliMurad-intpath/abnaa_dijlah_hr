from odoo import http
from odoo.http import request

NO_STORE = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff')]


def _engine():
    from .. import pdf_engine
    return pdf_engine


class AdFormController(http.Controller):

    @http.route('/abnaa_dijlah_hr/preview/<int:tpl_id>/<int:page>', type='http', auth='user')
    def preview(self, tpl_id, page=1, overlay=None, **kwargs):
        tpl = request.env['ad.form.template'].browse(tpl_id).exists()
        if not tpl:
            return request.not_found()
        tpl.check_access('read')
        data = tpl._get_pdf_bytes()
        if not data or not 1 <= page <= len(_engine().page_sizes(data)):
            return request.not_found()
        items = None
        if overlay:
            tpl.check_access('write')
            items = [item for item in tpl._designer_items() if item['page'] == page]
        png = _engine().render_page_png(data, page, zoom=2, items=items)
        return request.make_response(png, headers=[('Content-Type', 'image/png')] + NO_STORE)

    @http.route('/abnaa_dijlah_hr/font/naskh.ttf', type='http', auth='user')
    def naskh_font(self, **kwargs):
        return request.make_response(_engine().naskh_font_bytes(), headers=[
            ('Content-Type', 'font/ttf'), ('Cache-Control', 'private, max-age=86400')])

    @http.route('/abnaa_dijlah_hr/print/<string:model>/<string:ids>', type='http', auth='user')
    def print_form(self, model, ids, **kwargs):
        env = request.env
        if model not in env or not hasattr(env[model], 'ad_tpl') or not model.startswith('ad.'):
            return request.not_found()
        try:
            id_list = [int(i) for i in ids.split(',') if i][:50]
        except ValueError:
            return request.not_found()
        records = env[model].browse(id_list).exists()
        if not records:
            return request.not_found()
        env['ad.dashboard.block']._check_form_access(model)
        records.check_access('read')
        pdfs = [rec._ad_render_pdf() for rec in records]
        if len(pdfs) == 1:
            data = pdfs[0]
        else:
            import pymupdf
            with pymupdf.open() as merged:
                for pdf in pdfs:
                    with pymupdf.open(stream=pdf, filetype='pdf') as part:
                        merged.insert_pdf(part)
                data = merged.tobytes(garbage=3, deflate=True)
        name = (records[0].name if len(records) == 1 and records[0].name not in ('/', False) else model.replace('.', '-'))
        return request.make_response(data, headers=[
            ('Content-Type', 'application/pdf'),
            ('Content-Disposition', 'inline; filename="%s.pdf"' % name.replace('/', '-'))] + NO_STORE)
