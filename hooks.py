def post_init(env):
    """Load the blank PDFs, printed fields and approval stages of the forms."""
    env['ad.form.template']._ad_seed_engine()
