import base64
import io

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import BinaryValue


class ResUsers(models.Model):
    _inherit = 'res.users'

    ad_site_ids = fields.Many2many('ad.work.site', 'ad_work_site_user_rel', 'user_id', 'site_id', string='Visible work sites',
                                   help='Empty = the user sees the forms of every site.')
    ad_signature = fields.Binary('Approval signature', attachment=True, copy=False,
                                 help='PNG image with a transparent background, printed on the forms this user approves.')
    ad_signature_filename = fields.Char(copy=False)

    @api.constrains('ad_signature')
    def _check_ad_signature(self):
        for rec in self.filtered('ad_signature'):
            try:
                from PIL import Image
                value = rec.ad_signature
                raw = value.content if isinstance(value, BinaryValue) else base64.b64decode(value)
                with Image.open(io.BytesIO(raw)) as image:
                    if image.format != 'PNG':
                        raise ValueError('not PNG')
                    if image.width * image.height > 4_000_000 or len(raw) > 2 * 1024 * 1024:
                        raise ValueError('too large')
            except Exception:
                raise ValidationError(self.env._('The approval signature must be a valid PNG image (up to 2 MB).'))

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ['ad_signature', 'ad_signature_filename']
