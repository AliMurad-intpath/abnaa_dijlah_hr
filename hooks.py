import logging

_logger = logging.getLogger(__name__)


def post_init(env):
    """Create one approval type per form so the approvers can be set in the Approvals app."""
    from .models.ad_approval_bridge import PLAN
    for model_name in PLAN:
        try:
            with env.cr.savepoint():
                env[model_name]._ad_category()
        except Exception:  # pragma: no cover - never block the install
            _logger.warning('Could not create the approval type for %s', model_name, exc_info=True)
