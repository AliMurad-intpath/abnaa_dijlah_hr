import base64
import io
import json
import logging
import math
import re
import uuid
from datetime import date, datetime

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import BinaryBytes, BinaryValue, file_path

_logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 25 * 1024 * 1024
MONTHS_AR = ['كانون الثاني', 'شباط', 'آذار', 'نيسان', 'أيار', 'حزيران',
             'تموز', 'آب', 'أيلول', 'تشرين الأول', 'تشرين الثاني', 'كانون الأول']
PROBATION_AR = {1: 'شهر واحد', 2: 'شهرين', 3: 'ثلاثة اشهر', 4: 'اربعة اشهر', 6: 'ستة اشهر'}

FIELD_TYPES = [
    ('text', 'نص'), ('date', 'تاريخ'), ('money', 'مبلغ'), ('mark', 'علامة ✔ (خيار / مربع)'),
    ('mark_in', 'علامة ✔ (مخالفة محددة)'), ('selection', 'اختيار (يطبع اسم الخيار)'),
    ('month_year', 'شهر وسنة'), ('months_ar', 'فترة بالاشهر (نص)'), ('system', 'قيمة النظام'),
]
SYSTEM_SOURCES = [('request_name', 'رقم الاستمارة'), ('request_date', 'تاريخ اليوم'),
                  ('company_name', 'اسم الشركة'), ('approver_name', 'اسم المعتمد'),
                  ('approval_date', 'تاريخ الموافقة')]
DESIGNER_FIELD_KEYS = {'page', 'x', 'y', 'width', 'height', 'font_size', 'min_font_size',
                       'text_align', 'bold', 'multiline', 'sample_value', 'font_family', 'date_format'}
DESIGNER_STAGE_KEYS = {'signature_page', 'signature_x', 'signature_y',
                       'signature_width', 'signature_height', 'print_signature'}
MARK = '✔'
# model fields never offered as a printable value
SKIP_FIELDS = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', '__last_update',
               'message_ids', 'message_follower_ids', 'activity_ids', 'website_message_ids', 'signature_ids',
               'ad_step_ids', 'ad_layout_snapshot'}
EMPLOYEE_SUB = [('name', 'الاسم'), ('identification_id', 'رقم الهوية'), ('job_title', 'المسمى الوظيفي'),
                ('mobile_phone', 'الهاتف'), ('ad_employee_no', 'الرقم الوظيفي'), ('ad_work_site_id.name', 'موقع العمل'),
                ('birthday', 'تاريخ الميلاد')]


def _engine():
    from .. import pdf_engine
    return pdf_engine


def _sample_signature_png():
    from PIL import Image, ImageDraw
    image = Image.new('RGBA', (300, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.line([(10, 85), (60, 30), (100, 95), (150, 25), (200, 90), (250, 40), (290, 70)],
              fill=(20, 60, 160, 255), width=6)
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    return buffer.getvalue()


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    document_signature = fields.Binary('توقيع الموافقة', attachment=True,
                                       help='صورة PNG بخلفية شفافة تطبع على الاستمارات عند موافقة هذا الموظف.')
    document_signature_filename = fields.Char()

    @api.constrains('document_signature')
    def _check_document_signature(self):
        for rec in self.filtered('document_signature'):
            try:
                from PIL import Image
                value = rec.document_signature
                raw = value.content if isinstance(value, BinaryValue) else base64.b64decode(value)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'PNG':
                        raise ValueError('not PNG')
                    if image.width * image.height > 4_000_000 or len(raw) > 2 * 1024 * 1024:
                        raise ValueError('too large')
            except Exception:
                raise ValidationError(self.env._('توقيع الموافقة يجب ان يكون صورة PNG صالحة (حتى 2 ميغابايت).'))


class AdFormTemplate(models.Model):
    _inherit = 'ad.form.template'

    res_model = fields.Char('نموذج الاستمارة', readonly=True, copy=False,
                            help='النموذج الذي تطبع بياناته على الـ PDF.')
    template_pdf = fields.Binary('ملف PDF الفارغ', attachment=False)
    template_attachment_id = fields.Many2one('ir.attachment', string='الملف المخزن', readonly=True, copy=False,
                                             ondelete='set null')
    template_filename = fields.Char('اسم الملف')
    field_ids = fields.One2many('ad.form.field', 'template_id', string='الحقول المطبوعة', copy=True)
    stage_ids = fields.One2many('ad.form.stage', 'template_id', string='مراحل الموافقة', copy=True)
    page_count = fields.Integer('عدد الصفحات', compute='_compute_page_count')

    # ------------------------------------------------------------------ pdf storage
    @api.model
    def _decode_pdf_payload(self, payload):
        import binascii
        if not payload:
            return b''
        if isinstance(payload, BinaryValue):
            payload = payload.content
        if isinstance(payload, dict):
            if 'content' not in payload:
                raise ValidationError(self.env._('اختر ملف PDF مرة اخرى؛ محتوى الملف مفقود.'))
            payload = payload['content']
            if not payload:
                raise ValidationError(self.env._('الملف المختار فارغ.'))
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if isinstance(payload, str):
            try:
                payload = payload.encode('ascii')
            except UnicodeEncodeError:
                raise ValidationError(self.env._('الملف المرفوع ليس PDF صالحا.'))
        if not isinstance(payload, bytes):
            raise ValidationError(self.env._('قيمة PDF غير صالحة. اختر الملف مرة اخرى.'))
        if payload.startswith(b'%PDF-'):
            data = payload
        else:
            if payload.startswith(b'data:') and b';base64,' in payload:
                payload = payload.split(b';base64,', 1)[1]
            try:
                data = base64.b64decode(b''.join(payload.split()), validate=True)
            except (binascii.Error, ValueError):
                raise ValidationError(self.env._('الملف المرفوع ليس PDF صالحا.'))
            if not data.startswith(b'%PDF-'):
                raise ValidationError(self.env._('يرجى رفع ملف PDF.'))
        if len(data) > MAX_PDF_BYTES:
            raise ValidationError(self.env._('حجم ملف PDF يجب الا يتجاوز 25 ميغابايت.'))
        return data

    @api.model
    def _validate_pdf_data(self, data):
        import pymupdf
        try:
            with pymupdf.open(stream=data, filetype='pdf') as pdf:
                if len(pdf) == 0 or pdf.needs_pass:
                    raise ValueError('empty or password-protected PDF')
        except Exception as exc:
            raise ValidationError(self.env._('ملف PDF غير صالح او غير مدعوم: %s', exc))

    def _get_pdf_bytes(self):
        self.ensure_one()
        if self.template_attachment_id:
            return self._decode_pdf_payload(self.template_attachment_id.sudo().raw)
        return self._decode_pdf_payload(self.template_pdf)

    def _page_sizes(self):
        self.ensure_one()
        data = self._get_pdf_bytes()
        return _engine().page_sizes(data) if data else []

    def _store_template_attachment(self, payload):
        self.ensure_one()
        data = self._decode_pdf_payload(payload)
        self._validate_pdf_data(data)
        attachment = self.env['ir.attachment'].sudo().create({
            'name': self.template_filename or 'template.pdf',
            'type': 'binary', 'mimetype': 'application/pdf',
            'raw': BinaryBytes(data, filename=self.template_filename or 'template.pdf'),
            'res_model': self._name, 'res_id': self.id,
        })
        old = self.template_attachment_id
        super(AdFormTemplate, self).write({'template_attachment_id': attachment.id, 'template_pdf': False})
        if old:
            old.sudo().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            if isinstance(vals.get('template_pdf'), dict) and vals['template_pdf'].get('filename'):
                vals.setdefault('template_filename', vals['template_pdf']['filename'])
        payloads = [vals.pop('template_pdf', False) for vals in vals_list]
        records = super().create(vals_list)
        for rec, payload in zip(records, payloads):
            if payload:
                rec._store_template_attachment(payload)
        return records

    def write(self, vals):
        vals = dict(vals)
        payload = vals.get('template_pdf')
        if isinstance(payload, dict) and payload.get('filename'):
            vals.setdefault('template_filename', payload['filename'])
            if 'content' not in payload:
                vals.pop('template_pdf')
                payload = None
        if 'template_attachment_id' in vals and not self.env.su:
            raise AccessError(self.env._('الملف المخزن يدار تلقائيا.'))
        new_pdf = vals.pop('template_pdf', None) if vals.get('template_pdf') else None
        clear = 'template_pdf' in vals and not vals['template_pdf']
        if clear:
            vals.pop('template_pdf')
        result = super().write(vals)
        if new_pdf:
            for rec in self:
                rec._store_template_attachment(new_pdf)
            self.field_ids._check_inside_page()
            self.stage_ids._check_signature_inside_page()
        elif clear:
            old = self.mapped('template_attachment_id')
            super().write({'template_attachment_id': False})
            old.sudo().unlink()
        elif 'template_filename' in vals:
            for rec in self:
                rec.template_attachment_id.sudo().write({'name': vals['template_filename'] or 'template.pdf'})
        return result

    def unlink(self):
        attachments = self.mapped('template_attachment_id')
        result = super().unlink()
        attachments.sudo().unlink()
        return result

    @api.depends('template_attachment_id', 'template_pdf')
    def _compute_page_count(self):
        for rec in self:
            try:
                rec.page_count = len(rec._page_sizes())
            except Exception:
                rec.page_count = 0

    def action_clear_pdf(self):
        self.ensure_one()
        self.check_access('write')
        old = self.template_attachment_id
        super(AdFormTemplate, self).write({'template_attachment_id': False})
        old.sudo().unlink()
        return True

    def action_download_pdf(self):
        self.ensure_one()
        self.check_access('read')
        if not self.template_attachment_id:
            raise UserError(self.env._('لا يوجد ملف.'))
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': '/web/content/%s?download=true' % self.template_attachment_id.id}

    # ------------------------------------------------------------------ designer
    def action_open_designer(self):
        self.ensure_one()
        self.check_access('write')
        if not self._get_pdf_bytes():
            raise UserError(self.env._('ارفع ملف PDF واحفظ اولا.'))
        return {'type': 'ir.actions.client', 'tag': 'ad_pdf_designer', 'name': self.env._('مصمم الاستمارة'),
                'params': {'type_id': self.id}, 'context': {'active_id': self.id}}

    def _designer_items(self):
        self.ensure_one()
        items = [field._pdf_item(field.sample_value or field._sample_text()) for field in self.field_ids]
        sample = _sample_signature_png()
        items += [stage._pdf_signature_item(sample) for stage in self.stage_ids if stage.print_signature]
        return items

    def _source_choices(self):
        """[(path, label, field_type)] of the values of this form that can be printed."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return []
        model = self.env[self.res_model]
        out = []
        for name, fld in model._fields.items():
            if name in SKIP_FIELDS or name.startswith(('message_', 'activity_', 'website_', 'ad_approval', 'ad_state')):
                continue
            if fld.type in ('char', 'text', 'html', 'integer', 'float', 'monetary', 'date', 'datetime', 'selection', 'boolean'):
                kind = {'date': 'date', 'datetime': 'date', 'monetary': 'money', 'float': 'money',
                        'boolean': 'mark', 'selection': 'selection'}.get(fld.type, 'text')
                out.append((name, fld.string or name, kind))
            elif fld.type == 'many2one' and name not in ('company_id', 'create_uid', 'write_uid'):
                if fld.comodel_name == 'hr.employee':
                    out += [('%s.%s' % (name, sub), '%s / %s' % (fld.string or name, label),
                             'date' if sub == 'birthday' else 'text') for sub, label in EMPLOYEE_SUB]
                else:
                    out.append(('%s.name' % name, fld.string or name, 'text'))
        out += [('company_id.ad_md_name', 'اسم المدير المفوض', 'text'),
                ('company_id.ad_md_title', 'عنوان المدير المفوض', 'text')]
        return out

    def designer_load(self):
        self.ensure_one()
        self.check_access('write')
        groups = self.env['res.groups'].search([('name', 'like', 'استمارات AD')])
        return {
            'id': self.id, 'name': self.display_name, 'locked': False, 'structure_locked': False,
            'pages': [[round(w, 2), round(h, 2)] for w, h in self._page_sizes()],
            'frames': _engine().frames(self._get_pdf_bytes()),
            'fields': self.field_ids.read(['name', 'key', 'field_type', 'system_source', 'source_path', 'match_value',
                                           'sequence', 'date_format'] + sorted(DESIGNER_FIELD_KEYS - {'date_format'})),
            'rules': self.stage_ids.read(['name', 'print_signature', 'approver_id', 'group_id', 'sequence']
                                         + sorted(DESIGNER_STAGE_KEYS)),
            'sources': [list(s) for s in self._source_choices()],
            'field_types': FIELD_TYPES, 'system_sources': [list(p) for p in SYSTEM_SOURCES[:3]],
            'approvers': self.env['res.users'].search_read([('active', '=', True), ('share', '=', False)], ['name']),
            'groups': [{'id': g.id, 'name': g.name} for g in groups],
            'issues': self.layout_issues(),
        }

    def designer_save(self, changes):
        self.ensure_one()
        self.check_access('write')
        if not isinstance(changes, dict) or set(changes) - {'fields', 'rules', 'new_fields', 'new_rules'}:
            raise ValidationError(self.env._('طلب مصمم غير صالح.'))
        mapping = {'field': {}, 'rule': {}}
        with self.env.cr.savepoint():
            for model, allowed, key in (('ad.form.field', DESIGNER_FIELD_KEYS, 'fields'),
                                        ('ad.form.stage', DESIGNER_STAGE_KEYS, 'rules')):
                updates = changes.get(key) or {}
                if not isinstance(updates, dict):
                    raise ValidationError(self.env._('قائمة تغييرات غير صالحة.'))
                for record_id, vals in updates.items():
                    record = self.env[model].browse(int(record_id)).exists()
                    if not record or record.template_id != self or not isinstance(vals, dict) or set(vals) - allowed:
                        raise AccessError(self.env._('تغيير غير صالح.'))
                    record.write(vals)
            field_allowed = DESIGNER_FIELD_KEYS | {'name', 'key', 'field_type', 'source_path', 'match_value',
                                                   'system_source', 'sequence'}
            stage_allowed = DESIGNER_STAGE_KEYS | {'name', 'sequence', 'approver_id', 'group_id', 'print_signature'}
            for kind, key, model, allowed in (('field', 'new_fields', 'ad.form.field', field_allowed),
                                              ('rule', 'new_rules', 'ad.form.stage', stage_allowed)):
                new_records = changes.get(key) or []
                if not isinstance(new_records, list) or len(new_records) > 100:
                    raise ValidationError(self.env._('لا تضف اكثر من 100 عنصر في الحفظ الواحد.'))
                for entry in new_records:
                    if not isinstance(entry, dict) or not isinstance(entry.get('values'), dict):
                        raise ValidationError(self.env._('عنصر جديد غير صالح.'))
                    vals = dict(entry['values'])
                    local_id = str(entry.get('local_id', ''))
                    if not re.fullmatch(r'-[1-9][0-9]*', local_id) or local_id in mapping[kind] or set(vals) - allowed:
                        raise AccessError(self.env._('عنصر جديد غير صالح.'))
                    if not (vals.get('name') or '').strip():
                        raise ValidationError(self.env._('ادخل اسما للحقل او المرحلة.'))
                    if kind == 'rule':
                        for k in ('approver_id', 'group_id'):
                            if not vals.get(k):
                                vals.pop(k, None)
                        if not vals.get('approver_id') and not vals.get('group_id'):
                            raise ValidationError(self.env._('اختر معتمدا او مجموعة للمرحلة الجديدة.'))
                    vals['template_id'] = self.id
                    record = self.env[model].create(vals)
                    mapping[kind][local_id] = record.id
            result = self.designer_load()
            result['created_ids'] = mapping
        return result

    def layout_issues(self):
        self.ensure_one()
        data = self._get_pdf_bytes()
        if not data:
            return []
        items = self._designer_items()
        _pdf, issues = _engine().render(data, items, collect=True, output=False)
        blocked = {issue['key'] for issue in issues}
        issues += [issue for issue in _engine().overlap_issues(data, items) if issue['key'] not in blocked]
        return [dict(issue) for issue in issues]

    # ------------------------------------------------------------------ seeding
    @api.model
    def _ad_seed_engine(self):
        """Load the blank PDFs, printed fields and approval stages shipped with the module.
        Runs on install / update and only touches templates that have no PDF yet."""
        path = file_path('abnaa_dijlah_hr/data/engine_layouts.json')
        with open(path, encoding='utf-8') as fh:
            layouts = json.load(fh)
        for key, spec in layouts.items():
            tpl = self.env.ref('abnaa_dijlah_hr.' + spec['xmlid'], raise_if_not_found=False)
            if not tpl:
                continue
            if not tpl.res_model:
                tpl.sudo().write({'res_model': spec['model']})
            if tpl.template_attachment_id or tpl.field_ids or tpl.stage_ids:
                continue
            try:
                with self.env.cr.savepoint():
                    with open(file_path('abnaa_dijlah_hr/' + spec['pdf']), 'rb') as fh:
                        data = fh.read()
                    tpl = tpl.sudo().with_context(ad_engine_seed=True)
                    tpl.write({'template_filename': '%s.pdf' % key, 'template_pdf': base64.b64encode(data)})
                    Stage = self.env['ad.form.stage'].sudo().with_context(ad_engine_seed=True)
                    stage_by_key = {}
                    for st in spec['stages']:
                        group = self.env.ref('abnaa_dijlah_hr.' + st['group'], raise_if_not_found=False)
                        vals = {k: v for k, v in st.items() if k not in ('group',)}
                        vals.update(template_id=tpl.id, group_id=group.id if group else False)
                        stage_by_key[st['key']] = Stage.create(vals)
                    Field = self.env['ad.form.field'].sudo().with_context(ad_engine_seed=True)
                    Field.create([dict(f, template_id=tpl.id) for f in spec['fields']])
            except Exception:
                _logger.exception('Could not load the PDF layout of %s', key)


class AdFormField(models.Model):
    _name = 'ad.form.field'
    _description = 'حقل مطبوع على الاستمارة'
    _order = 'sequence, id'

    template_id = fields.Many2one('ad.form.template', required=True, ondelete='cascade', string='الاستمارة')
    sequence = fields.Integer(default=10)
    name = fields.Char('الاسم', required=True)
    key = fields.Char('المفتاح', required=True, help='معرف فريد بحروف انكليزية صغيرة')
    field_type = fields.Selection(FIELD_TYPES, 'نوع القيمة', required=True, default='text')
    source_path = fields.Char('مصدر القيمة', help='اسم حقل في الاستمارة، مثال: employee_id.name او score_ids.0.score')
    match_value = fields.Char('تطبع العلامة عندما تساوي', help='للعلامات: القيمة التي تفعّل العلامة (اتركه فارغا للحقل المنطقي).')
    system_source = fields.Selection(SYSTEM_SOURCES, 'قيمة النظام')
    stage_id = fields.Many2one('ad.form.stage', 'مرحلة الموافقة', ondelete='restrict',
                               domain="[('template_id', '=', template_id)]")
    date_format = fields.Char('صيغة التاريخ', default='%d / %m / %Y')
    page = fields.Integer('الصفحة', default=1, required=True)
    x = fields.Float('X (pt)', default=40, digits=(16, 2))
    y = fields.Float('Y من الاعلى (pt)', default=40, digits=(16, 2))
    width = fields.Float('العرض', default=120, digits=(16, 2))
    height = fields.Float('الارتفاع', default=16, digits=(16, 2))
    font_size = fields.Integer('حجم الخط', default=11)
    min_font_size = fields.Integer('اصغر حجم خط', default=6)
    bold = fields.Boolean('غامق')
    font_family = fields.Selection([('dejavu', 'DejaVu Sans (قابل للبحث)'), ('naskh', 'Naskh (غير قابل للبحث)')],
                                   default='dejavu', string='الخط')
    multiline = fields.Boolean('عدة اسطر')
    text_align = fields.Selection([('left', 'يسار'), ('center', 'وسط'), ('right', 'يمين')], default='right',
                                  string='المحاذاة')
    sample_value = fields.Char('قيمة تجريبية', help='نص يظهر في المصمم، مثلا اسم طويل.')

    @api.constrains('key')
    def _check_key(self):
        for rec in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', rec.key or ''):
                raise ValidationError(self.env._('مفتاح الحقل: حروف انكليزية صغيرة وارقام و _ فقط.'))

    @api.constrains('field_type', 'system_source', 'stage_id', 'source_path')
    def _check_source(self):
        for rec in self:
            if rec.field_type == 'system':
                if not rec.system_source:
                    raise ValidationError(self.env._('اختر قيمة النظام التي يطبعها "%s".', rec.name))
                if rec.system_source in ('approver_name', 'approval_date') and not rec.stage_id:
                    raise ValidationError(self.env._('اختر مرحلة الموافقة للحقل "%s".', rec.name))
            elif not rec.source_path:
                raise ValidationError(self.env._('اختر مصدر القيمة للحقل "%s".', rec.name))

    @api.constrains('page', 'x', 'y', 'width', 'height', 'font_size', 'min_font_size')
    def _check_placement(self):
        for rec in self:
            values = (rec.x, rec.y, rec.width, rec.height)
            if (not all(math.isfinite(v) for v in values) or rec.page < 1 or rec.x < 0 or rec.y < 0
                    or rec.width <= 0 or rec.height <= 0 or not 4 <= rec.font_size <= 72
                    or not 4 <= rec.min_font_size <= 72):
                raise ValidationError(self.env._('موضع غير صالح للحقل "%s".', rec.name))
        if not self.env.context.get('ad_engine_seed'):
            self._check_inside_page()

    def _check_inside_page(self):
        for tpl in self.mapped('template_id'):
            sizes = tpl._page_sizes()
            if not sizes:
                continue
            for rec in self.filtered(lambda f: f.template_id == tpl):
                if rec.page > len(sizes):
                    raise ValidationError(self.env._('الحقل "%(name)s" في الصفحة %(page)s لكن الملف %(count)s صفحة.',
                                                     name=rec.name, page=rec.page, count=len(sizes)))
                width, height = sizes[rec.page - 1]
                if rec.x + rec.width > width + 0.5 or rec.y + rec.height > height + 0.5:
                    raise ValidationError(self.env._(
                        'الحقل "%(name)s" يخرج عن الصفحة %(page)s (%(width).0f x %(height).0f pt). صغّر الصندوق او حرّكه.',
                        name=rec.name, page=rec.page, width=width, height=height))

    # -------------------------------------------------------------- printing
    def _pdf_item(self, text):
        self.ensure_one()
        return {
            'key': 'field-%s' % self.id, 'label': self.name, 'page': self.page,
            'x': self.x, 'y': self.y, 'width': self.width, 'height': self.height,
            'text': text, 'font_size': self.font_size, 'min_font_size': self.min_font_size,
            'align': self.text_align, 'bold': self.bold, 'multiline': self.multiline,
            'font': self.font_family,
        }

    def _sample_text(self):
        self.ensure_one()
        if self.field_type in ('mark', 'mark_in'):
            return MARK
        if self.field_type in ('date', 'month_year') or (self.system_source or '').endswith('date'):
            return '18 / 11 / 2026'
        if self.field_type == 'money':
            return '1,250,000'
        return self.name

    def _format_date(self, value):
        self.ensure_one()
        if not value:
            return ''
        if isinstance(value, datetime):
            value = value.date()
        try:
            return value.strftime(self.date_format or '%d / %m / %Y')
        except ValueError:
            return value.isoformat()

    def _walk(self, record):
        """Follow source_path from `record`. Returns (value, last_record, last_field_name)."""
        value, holder, fname = record, record, None
        for part in (self.source_path or '').split('.'):
            if isinstance(value, models.BaseModel):
                if part.isdigit():
                    idx = int(part)
                    value = value[idx] if idx < len(value) else value.browse()
                    continue
                value = value[:1] if len(value) > 1 else value
                if part.startswith('_') or part not in value._fields:
                    return False, value, None
                holder, fname = value, part
                value = value[part]
            else:
                return False, holder, None
        return value, holder, fname

    def _print_value(self, record):
        """The text this field prints for `record`."""
        self.ensure_one()
        if self.field_type == 'system':
            return self._system_text(record)
        value, holder, fname = self._walk(record)
        ftype = self.field_type
        if ftype == 'mark_in':
            wanted = (self.match_value or '').strip()
            if isinstance(value, models.BaseModel):
                return MARK if any(str(getattr(r, 'number', r.id)) == wanted for r in value) else ''
            return ''
        if ftype == 'mark':
            if self.match_value:
                return MARK if (value not in (False, None) and str(value) == self.match_value) else ''
            return MARK if value else ''
        if isinstance(value, models.BaseModel):
            return value.display_name or '' if len(value) else ''
        if value in (False, None):
            return ''
        if ftype == 'date':
            return self._format_date(value)
        if ftype == 'month_year':
            if isinstance(value, datetime):
                value = value.date()
            return '%s %s/' % (MONTHS_AR[value.month - 1], value.year) if isinstance(value, date) else ''
        if ftype == 'money':
            try:
                return '{:,.0f}'.format(float(value))
            except (TypeError, ValueError):
                return str(value)
        if ftype == 'months_ar':
            try:
                return PROBATION_AR.get(int(value)) or '%s اشهر' % int(value)
            except (TypeError, ValueError):
                return str(value)
        if ftype == 'selection' and holder is not None and fname:
            selection = dict(holder._fields[fname]._description_selection(holder.env))
            return selection.get(value, str(value))
        if isinstance(value, bool):
            return ''
        if isinstance(value, (date, datetime)):
            return self._format_date(value)
        return str(value)

    def _system_text(self, record):
        source = self.system_source
        if source == 'request_name':
            return record.name if getattr(record, 'name', '/') not in ('/', False) else ''
        if source == 'request_date':
            return self._format_date(fields.Date.context_today(record))
        if source == 'company_name':
            return record.company_id.name or ''
        step = record._ad_step_for_stage(self.stage_id) if self.stage_id else False
        if not step or step.state != 'approved':
            return ''
        if source == 'approver_name':
            return step.signed_by_name or step.signed_by_id.name or ''
        stamp = fields.Datetime.context_timestamp(record, step.action_date) if step.action_date else False
        return self._format_date(stamp.date()) if stamp else ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key') and vals.get('name'):
                base = re.sub(r'[^a-z0-9]+', '_', vals['name'].lower()).strip('_') or 'field'
                if not base[0].isalpha():
                    base = 'field_' + base
                vals['key'] = '%s_%s' % (base[:30], uuid.uuid4().hex[:6])
        return super().create(vals_list)


class AdFormStage(models.Model):
    _name = 'ad.form.stage'
    _description = 'مرحلة موافقة على استمارة'
    _order = 'sequence, id'

    template_id = fields.Many2one('ad.form.template', required=True, ondelete='cascade', string='الاستمارة')
    sequence = fields.Integer('الترتيب', default=10)
    name = fields.Char('المرحلة', required=True, copy=True)
    key = fields.Char('رمز التوقيع', help='يربط المرحلة بخانة التوقيع في سجل الموافقات (مثل hr, md).')
    approver_id = fields.Many2one('res.users', 'المعتمد (مستخدم محدد)', domain="[('share', '=', False)]",
                                  help='اذا حددت مستخدما فهو وحده من يوافق. اتركه فارغا ليوافق اي عضو من المجموعة.')
    group_id = fields.Many2one('res.groups', 'او اي عضو من مجموعة')
    signature_page = fields.Integer(default=1)
    signature_x = fields.Float(default=40, digits=(16, 2))
    signature_y = fields.Float(default=40, digits=(16, 2))
    signature_width = fields.Float(default=100, digits=(16, 2))
    signature_height = fields.Float(default=40, digits=(16, 2))
    print_signature = fields.Boolean('طباعة صورة التوقيع', default=True)
    approver_label = fields.Char('المعتمد', compute='_compute_approver_label')

    @api.depends('approver_id', 'group_id')
    def _compute_approver_label(self):
        for rec in self:
            rec.approver_label = rec.approver_id.name or rec.group_id.name or ''

    @api.constrains('approver_id', 'group_id')
    def _check_approver(self):
        for rec in self:
            if not rec.approver_id and not rec.group_id:
                raise ValidationError(self.env._('حدد معتمدا او مجموعة للمرحلة "%s".', rec.name))

    @api.constrains('signature_page', 'signature_x', 'signature_y', 'signature_width', 'signature_height', 'print_signature')
    def _check_signature_location(self):
        for rec in self:
            values = (rec.signature_x, rec.signature_y, rec.signature_width, rec.signature_height)
            if (not all(math.isfinite(v) for v in values) or rec.signature_page < 1
                    or min(rec.signature_x, rec.signature_y) < 0 or min(rec.signature_width, rec.signature_height) <= 0):
                raise ValidationError(self.env._('موضع توقيع غير صالح للمرحلة "%s".', rec.name))
        if not self.env.context.get('ad_engine_seed'):
            self._check_signature_inside_page()

    def _check_signature_inside_page(self):
        for rec in self.filtered('print_signature'):
            sizes = rec.template_id._page_sizes()
            if not sizes:
                continue
            if rec.signature_page > len(sizes):
                raise ValidationError(self.env._('توقيع "%(name)s" في الصفحة %(page)s لكن الملف %(count)s صفحة.',
                                                 name=rec.name, page=rec.signature_page, count=len(sizes)))
            width, height = sizes[rec.signature_page - 1]
            if (rec.signature_x + rec.signature_width > width + 0.5
                    or rec.signature_y + rec.signature_height > height + 0.5):
                raise ValidationError(self.env._('توقيع "%(name)s" يخرج عن الصفحة %(page)s.', name=rec.name,
                                                 page=rec.signature_page))

    def _eligible_check(self):
        self.ensure_one()
        if self.approver_id:
            return self.approver_id.active
        if self.group_id:
            group = self.group_id.sudo()
            users = group.all_user_ids if 'all_user_ids' in group._fields else group.user_ids
            return bool(users.filtered(lambda u: u.active and not u.share))
        return False

    def _pdf_signature_item(self, image):
        self.ensure_one()
        return {'key': 'signature-%s' % self.id, 'label': self.name, 'kind': 'image', 'image': image,
                'page': self.signature_page, 'x': self.signature_x, 'y': self.signature_y,
                'width': self.signature_width, 'height': self.signature_height}

    def action_place_on_pdf(self):
        self.ensure_one()
        self.check_access('write')
        action = self.template_id.action_open_designer()
        action['params'].update(selected_kind='rule', selected_id=self.id)
        action['target'] = 'main'
        return action

    def unlink(self):
        if self.env['ad.form.field'].sudo().search_count([('stage_id', 'in', self.ids)], limit=1):
            raise UserError(self.env._('هذه المرحلة تزود حقل نظام. غيّر المعتمد بدل حذفها.'))
        return super().unlink()
