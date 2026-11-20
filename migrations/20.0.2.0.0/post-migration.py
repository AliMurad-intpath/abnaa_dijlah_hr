import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """1.x used the Approvals app; 2.0 uses the built-in approval chain."""
    # the old approval crons would fail now: remove them
    cr.execute("""
        DELETE FROM ir_cron WHERE id IN (
            SELECT res_id FROM ir_model_data
             WHERE module = 'abnaa_dijlah_hr' AND model = 'ir.cron'
               AND name IN ('ir_cron_ad_approval_sync', 'ir_cron_ad_approval_remind'))
    """)
    cr.execute("""DELETE FROM ir_model_data WHERE module = 'abnaa_dijlah_hr' AND model = 'ir.cron'
                   AND name IN ('ir_cron_ad_approval_sync', 'ir_cron_ad_approval_remind')""")
    # the chain is the only approval route now
    cr.execute("UPDATE res_company SET ad_use_approvals = TRUE")
