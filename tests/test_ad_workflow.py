from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestAdWorkflow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site_a = cls.env['ad.work.site'].create({'name': 'Test site A'})
        cls.site_b = cls.env['ad.work.site'].create({'name': 'Test site B'})
        cls.guard = cls.env['hr.employee'].create({'name': 'Test Guard 1', 'ad_work_site_id': cls.site_a.id})
        cls.guard2 = cls.env['hr.employee'].create({'name': 'Test Guard 2', 'ad_work_site_id': cls.site_a.id})
        group = cls.env.ref('base.group_user')
        cls.u1 = cls.env['res.users'].create({'name': 'Approver one', 'login': 'ad_t_one', 'group_ids': [(6, 0, [group.id])]})
        cls.u2 = cls.env['res.users'].create({'name': 'Approver two', 'login': 'ad_t_two', 'group_ids': [(6, 0, [group.id])]})
        cls.u3 = cls.env['res.users'].create({'name': 'Substitute', 'login': 'ad_t_three', 'group_ids': [(6, 0, [group.id])]})

    def _transfer(self, employee=None):
        return self.env['ad.transfer'].create({'employee_id': (employee or self.guard).id, 'new_site_id': self.site_b.id})

    # -------------------------------------------------------------- numbering and status
    def test_number_and_status(self):
        rec = self._transfer()
        self.assertRegex(rec.name, r'^AD/\d{4}/\d{5}$')
        self.assertEqual(rec.ad_status, 'draft')

    # -------------------------------------------------------------- duplicate protection
    def test_duplicate_open_transfer_is_blocked(self):
        self._transfer()
        with self.assertRaises(ValidationError):
            self._transfer()
        # another employee is fine
        self._transfer(self.guard2)

    # -------------------------------------------------------------- employee first
    def test_employee_fill_values(self):
        values = self.env['ad.transfer']._ad_employee_fill_values(self.guard)
        self.assertEqual(values.get('old_site_id'), self.site_a.id)

    # -------------------------------------------------------------- substitutes
    def test_substitute_acts_for_absent_user(self):
        today = fields.Date.context_today(self.env['ad.approver.delegate'])
        self.env['ad.approver.delegate'].create({
            'user_id': self.u1.id, 'substitute_id': self.u3.id, 'date_from': today, 'date_to': today + timedelta(days=2)})
        acting = self.env['ad.approver.delegate']._acting_users(self.u3)
        self.assertIn(self.u1, acting)
        step = self.env['ad.form.step'].new({'approver_id': self.u1.id, 'state': 'pending'})
        self.assertTrue(step._user_may_act(self.u3))
        self.assertFalse(step._user_may_act(self.u2))

    def test_expired_substitute_does_not_act(self):
        today = fields.Date.context_today(self.env['ad.approver.delegate'])
        self.env['ad.approver.delegate'].create({
            'user_id': self.u1.id, 'substitute_id': self.u3.id,
            'date_from': today - timedelta(days=5), 'date_to': today - timedelta(days=1)})
        self.assertNotIn(self.u1, self.env['ad.approver.delegate']._acting_users(self.u3))

    # -------------------------------------------------------------- Requests list
    def test_requests_list_search(self):
        rec = self._transfer()
        Request = self.env['ad.request']
        self.assertTrue(Request.search_count([('res_model', '=', 'ad.transfer'), ('res_id', '=', rec.id)]))
        self.assertTrue(Request.with_user(self.env.ref('base.user_admin')).search([]) is not None)
        Request.search([('awaiting_me', '=', True)])

    # -------------------------------------------------------------- site visibility
    def test_site_visibility(self):
        rec = self._transfer()   # old site A -> new site B
        self.site_a.visibility_user_ids = self.u1
        self.assertEqual(self.u1.ad_site_ids, self.site_a)
        other_site = self.env['ad.work.site'].create({'name': 'Other site'})
        outsider = self.env['hr.employee'].create({'name': 'Outsider', 'ad_work_site_id': other_site.id})
        hidden = self.env['ad.transfer'].create({'employee_id': outsider.id, 'old_site_id': other_site.id,
                                                 'new_site_id': other_site.id})
        hr_group = self.env.ref('hr.group_hr_user')
        self.u1.group_ids = [(4, hr_group.id)]
        visible = self.env['ad.transfer'].with_user(self.u1).search([('id', 'in', (rec | hidden).ids)])
        self.assertIn(rec, visible)
        self.assertNotIn(hidden, visible)

    # -------------------------------------------------------------- bulk creation
    def test_bulk_create_transfers(self):
        wizard = self.env['ad.bulk.create'].create({
            'form_type': 'ad.transfer', 'site_id': self.site_a.id, 'new_site_id': self.site_b.id})
        self.assertEqual(wizard.employee_count, 2)
        wizard.action_create()
        self.assertEqual(self.env['ad.transfer'].search_count([('new_site_id', '=', self.site_b.id),
                                                               ('employee_id', 'in', (self.guard | self.guard2).ids)]), 2)
        # a second run creates nothing new: both guards already have an open transfer
        wizard.action_create()
        self.assertEqual(self.env['ad.transfer'].search_count([('employee_id', 'in', (self.guard | self.guard2).ids)]), 2)

    # -------------------------------------------------------------- chain: send back, escalation, frozen PDF
    def _chain_request(self):
        tpl = self.env.ref('abnaa_dijlah_hr.form_tpl_transfer')
        stages = tpl.stage_ids.sorted(lambda s: (s.sequence, s.id))
        self.assertGreaterEqual(len(stages), 2)
        stages[0].write({'approver_id': self.u1.id, 'group_id': False, 'deadline_hours': 1})
        stages[1:].write({'approver_id': self.u2.id, 'group_id': False})
        rec = self._transfer()
        rec.action_ad_submit()
        return rec

    def test_send_back_to_previous_stage(self):
        rec = self._chain_request()
        rec.with_user(self.u1).action_ad_approve()
        self.assertEqual(rec._ad_pending_step().approver_id, self.u2)
        with self.assertRaises(UserError):
            self._chain_request_first_stage_send_back()
        rec.with_user(self.u2)._ad_do_send_back('please fix the date')
        self.assertEqual(rec._ad_pending_step().approver_id, self.u1)
        self.assertEqual(rec.ad_state, 'pending')

    def _chain_request_first_stage_send_back(self):
        rec = self._transfer(self.guard2)
        rec.action_ad_submit()
        rec.with_user(self.u1)._ad_do_send_back('x')

    def test_deadline_escalation(self):
        rec = self._chain_request()
        step = rec._ad_pending_step()
        step.pending_since = fields.Datetime.now() - timedelta(hours=3)
        self.env['ad.form.step']._ad_escalate_overdue(fields.Datetime.now())
        step.invalidate_recordset()
        self.assertTrue(step.escalated)
        self.assertTrue(step._user_may_act(self.u2))

    def test_full_approval_freezes_pdf(self):
        rec = self._chain_request()
        for user in (self.u1, self.u2, self.u2, self.u2):
            if rec.ad_state != 'pending':
                break
            rec.with_user(user).action_ad_approve()
        self.assertEqual(rec.ad_state, 'approved')
        self.assertTrue(rec.ad_frozen_attachment_id)
        self.assertEqual(rec._ad_pdf_for_print()[:4], b'%PDF')
