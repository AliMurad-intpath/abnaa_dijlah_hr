import logging
import os

from lxml import etree

from odoo import SUPERUSER_ID, api, tools

_logger = logging.getLogger(__name__)
MODULE = 'abnaa_dijlah_hr'
NOUPDATE_FILES = ('data/ad_dashboard_block_data.xml', 'data/ad_violation_data.xml')


def migrate(cr, version):
    """The module source language is now English (Arabic ships as i18n/ar.po).
    Records of noupdate data files keep their old Arabic source value, so the
    English source term is written once here; Arabic is re-applied from ar.po."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for rel in NOUPDATE_FILES:
        path = tools.file_path('%s/%s' % (MODULE, rel))
        if not os.path.exists(path):
            continue
        for rec in etree.parse(path).getroot().iter('record'):
            xmlid, model = rec.get('id'), rec.get('model')
            name = rec.find("field[@name='name']")
            if not (xmlid and model and name is not None and name.text):
                continue
            record = env.ref('%s.%s' % (MODULE, xmlid), raise_if_not_found=False)
            if record and 'name' in record._fields:
                record.with_context(lang='en_US').write({'name': name.text.strip()})
    _logger.info('%s: English source terms refreshed', MODULE)
