"""The ONE translation path: i18n/ar.po is the only dictionary, and apply_arabic() writes it into the database.

It runs on every install and upgrade (data function ad.form.template._ad_apply_arabic), and the dashboard
reads the same file at run time. Add a new Arabic term to i18n/ar.po and nowhere else.

Writes the Arabic terms of i18n/ar.po straight into the database.

The normal translation import did not pick up the terms added after the first install on some servers,
so the upgrade (and, if needed, the Odoo shell) calls apply_arabic() to be sure every label is translated:

    from odoo.addons.abnaa_dijlah_hr.models.ad_translate import apply_arabic
    apply_arabic(env); env.cr.commit()
"""
import logging

from .ad_dashboard import _arabic_terms

_logger = logging.getLogger(__name__)

MODULE = 'abnaa_dijlah_hr'
# model -> translated field, written as one value per language
PLAIN = {
    'ir.ui.menu': 'name', 'ir.actions.act_window': 'name', 'ir.actions.server': 'name', 'ir.model': 'name',
    'ir.model.fields': 'field_description', 'ir.model.fields.selection': 'name',
}
# model -> field made of terms (XML / HTML): translated term by term
TERMS = {'ir.ui.view': ['arch_db'], 'ir.actions.act_window': ['help']}


def _langs(env):
    return [c for c in env['res.lang'].search([('active', '=', True)]).mapped('code') if c.startswith('ar')]


def apply_arabic(env):
    terms = _arabic_terms()
    langs = _langs(env)
    if not terms or not langs:
        return 0
    done = 0
    data = env['ir.model.data'].sudo().search([('module', '=', MODULE), ('model', 'in', sorted(set(PLAIN) | set(TERMS)))])
    for d in data:
        rec = env[d.model].sudo().browse(d.res_id).exists()
        if not rec:
            continue
        field = PLAIN.get(d.model)
        if field:
            try:
                source = rec.with_context(lang='en_US')[field]
                value = terms.get(source)
                if value:
                    for lang in langs:
                        rec.with_context(lang=lang).write({field: value})
                    done += 1
            except Exception:
                _logger.exception('Arabic term of %s.%s (%s) not written', d.model, field, d.name)
        for tfield in TERMS.get(d.model, ()):
            try:
                found, _ctx = rec.get_field_translations(tfield, langs)
                update = {}
                for item in found:
                    value = terms.get(' '.join((item.get('source') or '').split())) or terms.get(item.get('source'))
                    if value and not item.get('value'):
                        update.setdefault(item['lang'], {})[item['source']] = value
                if update:
                    rec.update_field_translations(tfield, update)
                    done += 1
            except Exception:
                _logger.exception('Arabic terms of %s.%s (%s) not written', d.model, tfield, d.name)
    _logger.info('abnaa_dijlah_hr: %s Arabic terms written for %s', done, langs)
    return done
