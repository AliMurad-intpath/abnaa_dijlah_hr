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

# Demo internal users: (key, name, login, role groups). Password is shown in the import log.
DEMO_PASSWORD = 'Demo@2026'
DEMO_USERS = [
    ('hr_manager', 'HR manager (demo)', 'demo.hr.manager',
     ['abnaa_dijlah_hr.group_ad_hr_manager']),
    ('hr_user', 'HR officer (demo)', 'demo.hr.user', ['abnaa_dijlah_hr.group_ad_hr_user']),
    ('ops_manager', 'Operations manager (demo)', 'demo.ops.manager', ['abnaa_dijlah_hr.group_ad_ops_manager']),
    ('site_supervisor', 'Site supervisor (demo)', 'demo.site.supervisor', ['abnaa_dijlah_hr.group_ad_site_supervisor']),
    ('logistics', 'Logistics department (demo)', 'demo.logistics', ['abnaa_dijlah_hr.group_ad_logistics']),
    ('admin_aa', 'Administration AA department (demo)', 'demo.admin.aa', ['abnaa_dijlah_hr.group_ad_admin']),
    ('motor', 'Vehicles MD department (demo)', 'demo.motor', ['abnaa_dijlah_hr.group_ad_motor']),
    ('finance', 'Finance department (demo)', 'demo.finance', ['abnaa_dijlah_hr.group_ad_finance']),
    ('md', 'Managing director (demo)', 'demo.md', ['abnaa_dijlah_hr.group_ad_md']),
    ('plain', 'User without form access (demo)', 'demo.plain', []),
]
# Forms limited to chosen demo users, to show the per-user access of the dashboard.
DEMO_RESTRICTED_FORMS = {'form_ad_termination_order': ['hr_manager', 'md']}


def _model_of(filename):
    return re.match(r'^\d+_[a-z_]+_(.+)\.csv$', filename).group(1)


class AdDemoLoader(models.TransientModel):
    _name = 'ad.demo.loader'
    _description = 'Demo data loader'

    log = fields.Text('Operation result', readonly=True)

    def _read_rows(self, filename):
        path = file_path('abnaa_dijlah_hr/data/demo/' + filename)
        with open(path, newline='', encoding='utf-8') as fh:
            rows = list(csv.reader(io.StringIO(fh.read())))
        return rows[0], rows[1:]

    def _demo_users(self):
        """Create (or find) the demo users with their roles. Returns ({key: user}, log lines)."""
        Users = self.env['res.users'].sudo().with_context(no_reset_password=True, mail_create_nosubscribe=True)
        gfield = 'group_ids' if 'group_ids' in Users._fields else 'groups_id'
        users, lines = {}, []
        for key, name, login, groups in DEMO_USERS:
            user = Users.with_context(active_test=False).search([('login', '=', login)], limit=1)
            if not user:
                gids = [self.env.ref('base.group_user').id]
                for xmlid in groups:
                    group = self.env.ref(xmlid, raise_if_not_found=False)
                    if group:
                        gids.append(group.id)
                user = Users.create({'name': self.env._(name), 'login': login, 'email': login + '@abnaa-demo.example',
                                     'password': DEMO_PASSWORD, gfield: [(6, 0, gids)]})
                lines.append(self.env._('✓ User: %s  (%s)', name, login))
            else:
                user.active = True
                lines.append(self.env._('= Exists: %s', login))
            users[key] = user
        # who may open which restricted form
        Block = self.env['ad.dashboard.block'].sudo()
        ids = Block._ids_by_key()
        for bkey, ukeys in DEMO_RESTRICTED_FORMS.items():
            if bkey in ids:
                Block.browse(ids[bkey]).write({'user_ids': [(4, users[k].id) for k in ukeys]})
        lines.append(self.env._('Password for all demo users: %s', DEMO_PASSWORD))
        return users, lines

    def _demo_remove_users(self):
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        demo = Users.search([('login', 'in', [u[2] for u in DEMO_USERS])])
        Block = self.env['ad.dashboard.block'].sudo()
        for blk in Block.search([('user_ids', 'in', demo.ids)]):
            blk.user_ids = [(3, u.id) for u in demo]
        done = 0
        for user in demo:
            try:
                with self.env.cr.savepoint():
                    user.unlink()
                done += 1
            except Exception:
                user.active = False      # cannot be deleted (has history): archive instead
                done += 1
        return self.env._('Demo users: delete/archive %s', done)

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
        try:
            with self.env.cr.savepoint():
                _users, user_lines = self._demo_users()
            lines.extend(user_lines)
        except Exception as exc:
            lines.append(self.env._('✗ Demo users : %s', exc))
        self.log = '\n'.join(lines)
        return self._reopen()

    def action_remove(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(self.env._('Only the system administrator can delete demo data.'))
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
            lines.append(self.env._('%s : deleted %s%s', filename, removed, self.env._(' / Could not delete %s', failed) if failed else ''))
        lines.append(self._demo_remove_users())
        self.log = '\n'.join(lines)
        return self._reopen()
