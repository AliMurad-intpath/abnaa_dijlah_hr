from odoo import fields, models

REPORT_KEYS = [
    ('appointment', 'Appointment order'),
    ('clearance', 'Clearance'),
    ('discipline', 'Penalties'),
    ('guarantee', 'Guarantee and written pledge'),
    ('interview', 'Interview rating'),
    ('moi', 'Ministry of Interior form'),
    ('onboarding', 'Start of work'),
    ('pledge', 'Written pledges'),
    ('termination', 'Termination of services'),
    ('transfer', 'Guard transfers'),
    ('general', 'Header and shared elements'),
]


class AdPrintText(models.Model):
    """One editable line of printed text (labels, paragraphs, headings of the forms).

    Every static text of the printed forms is stored here with the shipped wording
    as 'original'. HR edits `text`; the report prints `text`. A line may contain
    line breaks. Leaving it empty prints nothing for that line."""
    _name = 'ad.print.text'
    _description = 'Text editable in print'
    _order = 'report_key, seq'

    report_key = fields.Selection(REPORT_KEYS, 'Form', required=True, readonly=True, index=True)
    seq = fields.Integer('Line number', required=True, readonly=True)
    text = fields.Text('Printed text')
    original = fields.Text('Original text', readonly=True)
    edited = fields.Boolean('Modified', compute='_compute_edited', search='_search_edited')

    def _compute_edited(self):
        for rec in self:
            rec.edited = (rec.text or '') != (rec.original or '')

    def _search_edited(self, operator, value):
        ids = [r.id for r in self.search([]) if ((r.text or '') != (r.original or '')) == bool(value)]
        return [('id', 'in', ids)]

    def action_reset(self):
        for rec in self:
            rec.text = rec.original
        return True
