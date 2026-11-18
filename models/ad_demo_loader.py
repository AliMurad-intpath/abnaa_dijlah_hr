import csv
import io
import re

from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools import file_path

# Files are loaded in this order (later files refer to records of earlier ones).
DEMO_FILES = [
    '01_clients_res.partner.csv',
    '02_work_sites_ad.work.site.csv',
    '03_employees_hr.employee.csv',
    '04_interviews_ad.interview.csv',
    '05_appointment_orders_ad.appointment.order.csv',
    '06_effective_date_notices_ad.onboarding.csv',
    '07_guarantees_ad.employee.guarantee.csv',
    '08_pledges_ad.employee.pledge.csv',
    '09_transfers_ad.transfer.csv',
    '10_penalties_ad.discipline.csv',
    '11_termination_orders_ad.termination.order.csv',
]


def _model_of(filename):
    return re.match(r'^\d+_[a-z_]+_(.+)\.csv$', filename).group(1)


class AdDemoLoader(models.TransientModel):
    _name = 'ad.demo.loader'
    _description = 'Demo data loader'

    log = fields.Text('نتيجة العملية', readonly=True)

    def _read_rows(self, filename):
        path = file_path('abnaa_dijlah_hr/data/demo/' + filename)
        with open(path, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(io.StringIO(fh.read())))
        return rows[0], rows[1:]

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }

    def action_import(self):
        self.ensure_one()
        lines = []
        for filename in DEMO_FILES:
            model_name = _model_of(filename)
            header, rows = self._read_rows(filename)
            Model = self.env[model_name]
            try:
                with self.env.cr.savepoint():
                    result = Model.load(header, rows)
            except Exception as exc:  # report and continue with the next file
                lines.append('✗ %s : %s' % (filename, exc))
                continue
            errors = [m for m in result.get('messages', []) if m.get('type') == 'error']
            if errors:
                lines.append('✗ %s : %s' % (filename, '; '.join(str(m.get('message')) for m in errors[:3])))
            else:
                lines.append('✓ %s : %s' % (filename, len(result.get('ids') or [])))
        self.log = '\n'.join(lines)
        return self._reopen()

    def action_remove(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(self.env._('فقط مدير النظام يمكنه حذف بيانات التجربة.'))
        lines = []
        for filename in reversed(DEMO_FILES):
            model_name = _model_of(filename)
            xmls = self.env['ir.model.data'].search([
                ('module', '=', '__import__'), ('model', '=', model_name), ('name', '=like', 'demo\\_%')])
            removed = failed = 0
            for xml in xmls:
                rec = self.env[model_name].with_context(active_test=False).browse(xml.res_id).exists()
                if not rec:
                    xml.unlink()
                    continue
                try:
                    with self.env.cr.savepoint():
                        rec.unlink()
                    removed += 1
                except Exception:
                    failed += 1
            lines.append('%s : حذف %s%s' % (filename, removed, ' / تعذر حذف %s' % failed if failed else ''))
        self.log = '\n'.join(lines)
        return self._reopen()
