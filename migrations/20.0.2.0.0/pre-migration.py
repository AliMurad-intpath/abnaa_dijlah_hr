def migrate(cr, version):
    """Drop views/actions of the retired Odoo Approvals integration before the
    new code loads, so they cannot fail validation against removed methods."""
    cr.execute("""
        SELECT res_id FROM ir_model_data
         WHERE module = 'abnaa_dijlah_hr' AND model = 'ir.ui.view'
           AND (name LIKE '%approvals' OR name LIKE 'ad_approval%')
    """)
    ids = [r[0] for r in cr.fetchall()]
    cr.execute("""SELECT id FROM ir_ui_view
                   WHERE arch_db::text LIKE '%action_ad_open_approvals%'""")
    ids += [r[0] for r in cr.fetchall()]
    ids = list(set(ids))
    if ids:
        cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = ANY(%s)", (ids,))
        cr.execute("DELETE FROM ir_ui_view WHERE id = ANY(%s)", (ids,))
    cr.execute("""DELETE FROM ir_model_data WHERE module='abnaa_dijlah_hr'
                  AND model='ir.ui.view' AND res_id NOT IN (SELECT id FROM ir_ui_view)""")
    cr.execute("""DELETE FROM ir_ui_menu WHERE id IN (
                    SELECT res_id FROM ir_model_data WHERE module='abnaa_dijlah_hr'
                     AND model='ir.ui.menu' AND name LIKE '%approval_category%')""")
    cr.execute("""DELETE FROM ir_act_window WHERE id IN (
                    SELECT res_id FROM ir_model_data WHERE module='abnaa_dijlah_hr'
                     AND model='ir.actions.act_window' AND name LIKE '%approval_category%')""")
