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
    ('text', 'Text'), ('date', 'Date'), ('money', 'Amount'), ('mark', '✔ mark (option / box)'),
    ('mark_in', '✔ mark (specific violation)'), ('selection', 'Choice (prints the option name)'),
    ('month_year', 'Month and year'), ('months_ar', 'Period in months (text)'), ('system', 'System value'),
]
SYSTEM_SOURCES = [('request_name', 'Form number'), ('request_date', "Today's date"),
                  ('company_name', 'Company name'), ('approver_name', 'Approver name'),
                  ('approval_date', 'Approval date')]
DESIGNER_FIELD_KEYS = {'page', 'x', 'y', 'width', 'height', 'font_size', 'min_font_size',
                       'text_align', 'bold', 'multiline', 'sample_value', 'font_family', 'date_format'}
DESIGNER_STAGE_KEYS = {'signature_page', 'signature_x', 'signature_y',
                       'signature_width', 'signature_height', 'print_signature'}
MARK = '✔'
# Paper forms are always printed in Arabic, whatever the user's language
PRINT_SELECTION_AR = {'start_shift': {'am': 'ق.ظ', 'pm': 'ب.ظ'}, 'leave_shift': {'am': 'ق.ظ', 'pm': 'ب.ظ'}}
# model fields never offered as a printable value
SKIP_FIELDS = {'id', 'create_uid', 'create_date', 'write_uid', 'write_date', 'display_name', '__last_update',
               'message_ids', 'message_follower_ids', 'activity_ids', 'website_message_ids', 'signature_ids',
               'ad_step_ids', 'ad_layout_snapshot'}
EMPLOYEE_SUB = [('name', 'Name'), ('identification_id', 'ID number'), ('job_title', 'Job title'),
                ('mobile_phone', 'Phone'), ('ad_employee_no', 'Employee number'), ('ad_work_site_id.name', 'Work site'),
                ('birthday', 'Date of birth')]


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

    document_signature = fields.Binary('Approval signature', attachment=True,
                                       help='PNG image with a transparent background, printed on forms when this employee approves.')
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
                raise ValidationError(self.env._('The approval signature must be a valid PNG image (up to 2 MB).'))


class AdFormTemplate(models.Model):
    _inherit = 'ad.form.template'

    res_model = fields.Char('Form template', readonly=True, copy=False,
                            help='The model whose data is printed on the PDF.')
    template_pdf = fields.Binary('Blank PDF file', attachment=False)
    template_attachment_id = fields.Many2one('ir.attachment', string='Stored file', readonly=True, copy=False,
                                             ondelete='set null')
    template_filename = fields.Char('File name')
    field_ids = fields.One2many('ad.form.field', 'template_id', string='Printed fields', copy=True)
    stage_ids = fields.One2many('ad.form.stage', 'template_id', string='Approval stages', copy=True)
    page_count = fields.Integer('Page count', compute='_compute_page_count')

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
                raise ValidationError(self.env._('Choose the PDF file again; the file content is missing.'))
            payload = payload['content']
            if not payload:
                raise ValidationError(self.env._('The selected file is empty.'))
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if isinstance(payload, str):
            try:
                payload = payload.encode('ascii')
            except UnicodeEncodeError:
                raise ValidationError(self.env._('The uploaded file is not a valid PDF.'))
        if not isinstance(payload, bytes):
            raise ValidationError(self.env._('Invalid PDF value. Choose the file again.'))
        if payload.startswith(b'%PDF-'):
            data = payload
        else:
            if payload.startswith(b'data:') and b';base64,' in payload:
                payload = payload.split(b';base64,', 1)[1]
            try:
                data = base64.b64decode(b''.join(payload.split()), validate=True)
            except (binascii.Error, ValueError):
                raise ValidationError(self.env._('The uploaded file is not a valid PDF.'))
            if not data.startswith(b'%PDF-'):
                raise ValidationError(self.env._('Please upload a PDF file.'))
        if len(data) > MAX_PDF_BYTES:
            raise ValidationError(self.env._('The PDF file must not exceed 25 MB.'))
        return data

    @api.model
    def _validate_pdf_data(self, data):
        import pymupdf
        try:
            with pymupdf.open(stream=data, filetype='pdf') as pdf:
                if len(pdf) == 0 or pdf.needs_pass:
                    raise ValueError('empty or password-protected PDF')
        except Exception as exc:
            raise ValidationError(self.env._('Invalid or unsupported PDF file: %s', exc))

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
            raise AccessError(self.env._('The stored file is managed automatically.'))
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
            raise UserError(self.env._('There is no file.'))
        return {'type': 'ir.actions.act_url', 'target': 'self',
                'url': '/web/content/%s?download=true' % self.template_attachment_id.id}

    # ------------------------------------------------------------------ designer
    def action_open_designer(self):
        self.ensure_one()
        self.check_access('write')
        if not self._get_pdf_bytes():
            raise UserError(self.env._('Upload a PDF file and save first.'))
        return {'type': 'ir.actions.client', 'tag': 'ad_pdf_designer', 'name': self.env._('Form designer'),
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
                    out += [('%s.%s' % (name, sub), '%s / %s' % (fld.string or name, self.env._(label)),
                             'date' if sub == 'birthday' else 'text') for sub, label in EMPLOYEE_SUB]
                else:
                    out.append(('%s.name' % name, fld.string or name, 'text'))
        out += [('company_id.ad_md_name', self.env._('Managing director name'), 'text'),
                ('company_id.ad_md_title', self.env._('Managing director title'), 'text')]
        return out

    def designer_load(self):
        self.ensure_one()
        self.check_access('write')
        group_ids = self.env['ir.model.data'].sudo().search([
            ('module', '=', 'abnaa_dijlah_hr'), ('model', '=', 'res.groups'), ('name', '=like', 'group\\_ad\\_%')]).mapped('res_id')
        groups = self.env['res.groups'].browse(group_ids).exists()
        return {
            'id': self.id, 'name': self.display_name, 'locked': False, 'structure_locked': False,
            'pages': [[round(w, 2), round(h, 2)] for w, h in self._page_sizes()],
            'frames': _engine().frames(self._get_pdf_bytes()),
            'fields': self.field_ids.read(['name', 'key', 'field_type', 'system_source', 'source_path', 'match_value',
                                           'sequence', 'date_format'] + sorted(DESIGNER_FIELD_KEYS - {'date_format'})),
            'rules': self.stage_ids.read(['name', 'print_signature', 'approver_id', 'group_id', 'sequence']
                                         + sorted(DESIGNER_STAGE_KEYS)),
            'sources': [[s[0], self.env._(s[1]), *s[2:]] for s in self._source_choices()],
            'field_types': [[k, self.env._(v)] for k, v in FIELD_TYPES],
            'system_sources': [[k, self.env._(v)] for k, v in SYSTEM_SOURCES[:3]],
            'approvers': self.env['res.users'].search_read([('active', '=', True), ('share', '=', False)], ['name']),
            'groups': [{'id': g.id, 'name': g.name} for g in groups],
            'issues': self.layout_issues(),
        }

    def designer_save(self, changes):
        self.ensure_one()
        self.check_access('write')
        if not isinstance(changes, dict) or set(changes) - {'fields', 'rules', 'new_fields', 'new_rules'}:
            raise ValidationError(self.env._('Invalid designer request.'))
        mapping = {'field': {}, 'rule': {}}
        with self.env.cr.savepoint():
            for model, allowed, key in (('ad.form.field', DESIGNER_FIELD_KEYS, 'fields'),
                                        ('ad.form.stage', DESIGNER_STAGE_KEYS, 'rules')):
                updates = changes.get(key) or {}
                if not isinstance(updates, dict):
                    raise ValidationError(self.env._('Invalid change list.'))
                for record_id, vals in updates.items():
                    record = self.env[model].browse(int(record_id)).exists()
                    if not record or record.template_id != self or not isinstance(vals, dict) or set(vals) - allowed:
                        raise AccessError(self.env._('Invalid change.'))
                    record.write(vals)
            field_allowed = DESIGNER_FIELD_KEYS | {'name', 'key', 'field_type', 'source_path', 'match_value',
                                                   'system_source', 'sequence'}
            stage_allowed = DESIGNER_STAGE_KEYS | {'name', 'sequence', 'approver_id', 'group_id', 'print_signature'}
            for kind, key, model, allowed in (('field', 'new_fields', 'ad.form.field', field_allowed),
                                              ('rule', 'new_rules', 'ad.form.stage', stage_allowed)):
                new_records = changes.get(key) or []
                if not isinstance(new_records, list) or len(new_records) > 100:
                    raise ValidationError(self.env._('Do not add more than 100 items in one save.'))
                for entry in new_records:
                    if not isinstance(entry, dict) or not isinstance(entry.get('values'), dict):
                        raise ValidationError(self.env._('Invalid new item.'))
                    vals = dict(entry['values'])
                    local_id = str(entry.get('local_id', ''))
                    if not re.fullmatch(r'-[1-9][0-9]*', local_id) or local_id in mapping[kind] or set(vals) - allowed:
                        raise AccessError(self.env._('Invalid new item.'))
                    if not (vals.get('name') or '').strip():
                        raise ValidationError(self.env._('Enter a name for the field or stage.'))
                    if kind == 'rule':
                        for k in ('approver_id', 'group_id'):
                            if not vals.get(k):
                                vals.pop(k, None)
                        if not vals.get('approver_id') and not vals.get('group_id'):
                            raise ValidationError(self.env._('Select an approver or a group for the new stage.'))
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

    @api.model
    def _ad_reflow_layouts(self):
        """Replace the blank PDFs and field positions with the continuous-flow versions
        (no half-empty pages). Field keys, fonts and stages of existing records are kept."""
        path = file_path('abnaa_dijlah_hr/data/engine_layouts.json')
        with open(path, encoding='utf-8') as fh:
            layouts = json.load(fh)
        geometry = ('page', 'x', 'y', 'width', 'height')
        for key, spec in layouts.items():
            tpl = self.env.ref('abnaa_dijlah_hr.' + spec['xmlid'], raise_if_not_found=False)
            if not tpl or not tpl.field_ids:
                continue
            try:
                with self.env.cr.savepoint():
                    with open(file_path('abnaa_dijlah_hr/' + spec['pdf']), 'rb') as fh:
                        data = fh.read()
                    tpl = tpl.sudo().with_context(ad_engine_seed=True)
                    # signatures first: they must fit both the old and the new page count
                    Stage = self.env['ad.form.stage'].sudo().with_context(ad_engine_seed=True)
                    stage_by_key = {st.key: st for st in tpl.stage_ids}
                    for st in spec['stages']:
                        rec = stage_by_key.get(st['key'])
                        if rec:
                            rec.with_context(ad_engine_seed=True).write({k: st[k] for k in (
                                'signature_page', 'signature_x', 'signature_y', 'signature_width', 'signature_height')})
                    by_key = {f.key: f for f in tpl.field_ids}
                    for new in spec['fields']:
                        rec = by_key.get(new['key'])
                        if rec:
                            rec.with_context(ad_engine_seed=True).write({k: new[k] for k in geometry})
                    tpl.write({'template_filename': '%s.pdf' % key, 'template_pdf': base64.b64encode(data)})
            except Exception:
                _logger.exception('Could not reflow the PDF layout of %s', key)

    # ------------------------------------------------------------------ seeding
    @api.model
    def _ad_apply_arabic(self):
        """Single translation path: push i18n/ar.po into the database on every install and upgrade."""
        try:
            from .ad_translate import apply_arabic
            apply_arabic(self.env)
        except Exception:
            _logger.exception('Could not write the Arabic terms of abnaa_dijlah_hr')

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
    _description = 'Printed form field'
    _order = 'sequence, id'

    template_id = fields.Many2one('ad.form.template', required=True, ondelete='cascade', string='Form')
    sequence = fields.Integer(default=10)
    name = fields.Char('Name', required=True)
    key = fields.Char('Key', required=True, help='Unique identifier in lowercase English letters')
    field_type = fields.Selection(FIELD_TYPES, 'Value type', required=True, default='text')
    source_path = fields.Char('Value source', help='A field name on the form, e.g. employee_id.name or score_ids.0.score')
    match_value = fields.Char('Mark prints when equal to', help='For marks: the value that activates the mark (leave empty for a boolean field).')
    system_source = fields.Selection(SYSTEM_SOURCES, 'System value')
    stage_id = fields.Many2one('ad.form.stage', 'Approval stage', ondelete='restrict',
                               domain="[('template_id', '=', template_id)]")
    date_format = fields.Char('Date format', default='%d / %m / %Y')
    page = fields.Integer('Page', default=1, required=True)
    x = fields.Float('X (pt)', default=40, digits=(16, 2))
    y = fields.Float('Y from top (pt)', default=40, digits=(16, 2))
    width = fields.Float('Width', default=120, digits=(16, 2))
    height = fields.Float('Height', default=16, digits=(16, 2))
    font_size = fields.Integer('Font size', default=11)
    min_font_size = fields.Integer('Minimum font size', default=6)
    bold = fields.Boolean('Bold')
    font_family = fields.Selection([('dejavu', 'DejaVu Sans (searchable)'), ('times', 'Times New Roman (searchable)'),
                                    ('naskh', 'Naskh (not searchable)')],
                                   default='times', string='Font')
    multiline = fields.Boolean('Multiple lines')
    text_align = fields.Selection([('left', 'Left'), ('center', 'Center'), ('right', 'Right')], default='right',
                                  string='Alignment')
    sample_value = fields.Char('Sample value', help='Text shown in the designer, e.g. a long name.')

    @api.constrains('key')
    def _check_key(self):
        for rec in self:
            if not re.fullmatch(r'[a-z][a-z0-9_]*', rec.key or ''):
                raise ValidationError(self.env._('Field key: lowercase English letters, digits and _ only.'))

    @api.constrains('field_type', 'system_source', 'stage_id', 'source_path')
    def _check_source(self):
        for rec in self:
            if rec.field_type == 'system':
                if not rec.system_source:
                    raise ValidationError(self.env._('Select the system value printed by "%s".', rec.name))
                if rec.system_source in ('approver_name', 'approval_date') and not rec.stage_id:
                    raise ValidationError(self.env._('Select the approval stage for the field "%s".', rec.name))
            elif not rec.source_path:
                raise ValidationError(self.env._('Select the value source for the field "%s".', rec.name))

    @api.constrains('page', 'x', 'y', 'width', 'height', 'font_size', 'min_font_size')
    def _check_placement(self):
        for rec in self:
            values = (rec.x, rec.y, rec.width, rec.height)
            if (not all(math.isfinite(v) for v in values) or rec.page < 1 or rec.x < 0 or rec.y < 0
                    or rec.width <= 0 or rec.height <= 0 or not 4 <= rec.font_size <= 72
                    or not 4 <= rec.min_font_size <= 72):
                raise ValidationError(self.env._('Invalid position for field "%s".', rec.name))
        if not self.env.context.get('ad_engine_seed'):
            self._check_inside_page()

    def _check_inside_page(self):
        for tpl in self.mapped('template_id'):
            sizes = tpl._page_sizes()
            if not sizes:
                continue
            for rec in self.filtered(lambda f: f.template_id == tpl):
                if rec.page > len(sizes):
                    raise ValidationError(self.env._('The field "%(name)s" is on page %(page)s but the file has %(count)s pages.',
                                                     name=rec.name, page=rec.page, count=len(sizes)))
                width, height = sizes[rec.page - 1]
                if rec.x + rec.width > width + 0.5 or rec.y + rec.height > height + 0.5:
                    raise ValidationError(self.env._(
                        'The field "%(name)s" falls outside page %(page)s (%(width).0f x %(height).0f pt). Make the box smaller or move it.',
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
            if value in PRINT_SELECTION_AR.get(fname, {}):
                return PRINT_SELECTION_AR[fname][value]
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
    _description = 'Form approval stage'
    _order = 'sequence, id'

    template_id = fields.Many2one('ad.form.template', required=True, ondelete='cascade', string='Form')
    sequence = fields.Integer('Order', default=10)
    name = fields.Char('Stage', required=True, copy=True)
    key = fields.Char('Signature code', help='Links the stage to the signature slot in the approval record (e.g. hr, md).')
    approver_id = fields.Many2one('res.users', 'Approver (specific user)', domain="[('share', '=', False)]",
                                  help='If you select a user, only that user approves. Leave empty to let any member of the group approve.')
    group_id = fields.Many2one('res.groups', 'Or any member of a group')
    signature_page = fields.Integer(default=1)
    signature_x = fields.Float(default=40, digits=(16, 2))
    signature_y = fields.Float(default=40, digits=(16, 2))
    signature_width = fields.Float(default=100, digits=(16, 2))
    signature_height = fields.Float(default=40, digits=(16, 2))
    print_signature = fields.Boolean('Print signature image', default=True)
    deadline_hours = fields.Integer('Deadline (hours)', help='Hours the approver has before the step goes to the next person. 0 = no deadline.')
    approver_label = fields.Char('Approver', compute='_compute_approver_label')

    @api.depends('approver_id', 'group_id')
    def _compute_approver_label(self):
        for rec in self:
            rec.approver_label = rec.approver_id.name or rec.group_id.name or ''

    @api.constrains('approver_id', 'group_id')
    def _check_approver(self):
        for rec in self:
            if not rec.approver_id and not rec.group_id:
                raise ValidationError(self.env._('Select an approver or a group for the stage "%s".', rec.name))

    @api.constrains('signature_page', 'signature_x', 'signature_y', 'signature_width', 'signature_height', 'print_signature')
    def _check_signature_location(self):
        for rec in self:
            values = (rec.signature_x, rec.signature_y, rec.signature_width, rec.signature_height)
            if (not all(math.isfinite(v) for v in values) or rec.signature_page < 1
                    or min(rec.signature_x, rec.signature_y) < 0 or min(rec.signature_width, rec.signature_height) <= 0):
                raise ValidationError(self.env._('Invalid signature position for the stage "%s".', rec.name))
        if not self.env.context.get('ad_engine_seed'):
            self._check_signature_inside_page()

    def _check_signature_inside_page(self):
        for rec in self.filtered('print_signature'):
            sizes = rec.template_id._page_sizes()
            if not sizes:
                continue
            if rec.signature_page > len(sizes):
                raise ValidationError(self.env._('Signature "%(name)s" is on page %(page)s but the file has %(count)s pages.',
                                                 name=rec.name, page=rec.signature_page, count=len(sizes)))
            width, height = sizes[rec.signature_page - 1]
            if (rec.signature_x + rec.signature_width > width + 0.5
                    or rec.signature_y + rec.signature_height > height + 0.5):
                raise ValidationError(self.env._('Signature "%(name)s" falls outside page %(page)s.', name=rec.name,
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
            raise UserError(self.env._('This stage supplies a system field. Change the approver instead of deleting it.'))
        return super().unlink()
