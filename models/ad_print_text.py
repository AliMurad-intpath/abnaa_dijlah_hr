from odoo import fields, models

REPORT_KEYS = [
    ('appointment', 'أمر تعيين'),
    ('clearance', 'براءة الذمة'),
    ('discipline', 'العقوبات'),
    ('guarantee', 'الكفالة والتعهد الخطي'),
    ('interview', 'تقييم المقابلة'),
    ('moi', 'نموذج وزارة الداخلية'),
    ('onboarding', 'مباشرة العمل'),
    ('pledge', 'التعهدات الخطية'),
    ('termination', 'انهاء الخدمات'),
    ('transfer', 'تنقلات الحراس'),
    ('general', 'ترويسة وعناصر مشتركة'),
]


class AdPrintText(models.Model):
    """One editable line of printed text (labels, paragraphs, headings of the forms).

    Every static text of the printed forms is stored here with the shipped wording
    as 'original'. HR edits `text`; the report prints `text`. A line may contain
    line breaks. Leaving it empty prints nothing for that line."""
    _name = 'ad.print.text'
    _description = 'نص قابل للتعديل في الطباعة'
    _order = 'report_key, seq'

    report_key = fields.Selection(REPORT_KEYS, 'الاستمارة', required=True, readonly=True, index=True)
    seq = fields.Integer('رقم السطر', required=True, readonly=True)
    text = fields.Text('النص المطبوع')
    original = fields.Text('النص الأصلي', readonly=True)
    edited = fields.Boolean('معدل', compute='_compute_edited', search='_search_edited')

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
