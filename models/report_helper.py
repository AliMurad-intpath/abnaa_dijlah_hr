from markupsafe import Markup, escape

from odoo import api, models

from . import tools


class AdReportHelper(models.AbstractModel):
    """Formatting helpers called from the QWeb forms: env['ad.report.helper'].d3(date)"""
    _name = 'ad.report.helper'
    _description = 'مساعدات طباعة الاستمارات'

    @api.model
    def d3(self, value):
        return tools.d3(value)

    @api.model
    def month_year_ar(self, value):
        return tools.month_year_ar(value)

    @api.model
    def box(self, flag):
        return tools.box(flag)

    @api.model
    def money(self, value):
        return tools.money(value)

    @api.model
    def dots(self, value, mm=40):
        return tools.dots(value, mm)

    @api.model
    def txt(self, value):
        return tools.txt(value)

    @api.model
    def get(self, rec, *names):
        return tools.get(rec, *names)

    @api.model
    def t(self, key, n, default=''):
        """Printed text line `n` of form `key`: the edited text if any, else `default`."""
        cache = getattr(self.env.cr, 'cache', None)
        if cache is None:
            cache = {}
        ck = ('ad_print_text', key)
        if ck not in cache:
            rows = self.env['ad.print.text'].sudo().search_read([('report_key', '=', key)], ['seq', 'text'])
            cache[ck] = {r['seq']: r['text'] for r in rows}
        text = cache[ck].get(n, default)
        if not text:
            return ''
        if '\n' in text:
            return Markup('<br/>').join(escape(line) for line in text.split('\n'))
        return text

    @api.model
    def logo(self, full=False, tpl=None):
        """Logo for the printed header: form template logo > company logo > shipped logo."""
        image = (tpl and tpl.logo) or self.env.company.ad_logo
        if image:
            raw = image.decode() if isinstance(image, bytes) else image
            mime = 'image/jpeg' if raw.startswith('/9j') else 'image/svg+xml' if raw.startswith(('PHN2', 'PD94')) else 'image/png'
            return 'data:%s;base64,%s' % (mime, raw)
        return tools.logo_data_uri(full)
