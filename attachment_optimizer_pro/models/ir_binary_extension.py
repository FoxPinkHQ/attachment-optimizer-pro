import logging

from odoo import models
from odoo.http import Stream

from odoo.addons.attachment_optimizer.services.s3_bridge import S3BridgeError

from ..services.s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class IrBinaryExtension(models.AbstractModel):
    _inherit = 'ir.binary'

    def _get_stream_from(
        self, record, field_name='raw', filename=None, filename_field='name',
        mimetype=None, default_mimetype='application/octet-stream',
    ):
        if record._name == 'ir.attachment':
            try:
                record.check_access('read')
            except Exception:
                return
            mapping = self.env['attachment.storage.mapping'].sudo().search([
                ('attachment_id', '=', record.id),
                ('status', '=', 'finalized'),
                ('company_id', '=', record.company_id.id),
            ], limit=1)
            if mapping and mapping.bucket_id:
                # Routed mappings live in a bucket profile that may use its
                # own endpoint and credentials. The free edition bridge only
                # knows the global S3 config, so serve these with the
                # profile's config.
                bridge = ProS3Bridge(self.env)
                try:
                    content = bridge.get_object(
                        mapping.s3_bucket, mapping.s3_key,
                        config=mapping.bucket_id._s3_config(),
                    )
                except S3BridgeError as e:
                    _logger.error(
                        'S3 object missing for routed finalized mapping '
                        'attachment=%s bucket=%s key=%s: %s',
                        record.id, mapping.s3_bucket, mapping.s3_key, e,
                    )
                    # The original filestore data is retained. Fall back to
                    # it on S3 failures so a transient outage is not an
                    # attachment outage.
                    content = record.raw
                    if content:
                        return Stream(
                            data=content,
                            mimetype=record.mimetype or default_mimetype,
                            download_name=filename or record.name,
                            type='data',
                        )
                    return None
                return Stream(
                    data=content,
                    mimetype=record.mimetype or default_mimetype,
                    download_name=filename or record.name,
                    type='data',
                )
        return super()._get_stream_from(
            record, field_name=field_name, filename=filename,
            filename_field=filename_field, mimetype=mimetype,
            default_mimetype=default_mimetype,
        )
