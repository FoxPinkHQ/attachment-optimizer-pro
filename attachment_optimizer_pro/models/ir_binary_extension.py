import base64
import logging

from odoo import models

try:
    from odoo.http import Stream
    HAS_NATIVE_STREAM = True
except ImportError:  # Odoo 15
    HAS_NATIVE_STREAM = False

    class Stream:
        """Small compatibility value object matching the Odoo 16 Stream API."""

        def __init__(self, data, mimetype, download_name, type='data'):
            self.data = data
            self.mimetype = mimetype
            self.download_name = download_name
            self.type = type

from odoo.addons.attachment_optimizer.services.s3_bridge import (
    S3Bridge, S3BridgeError,
)

from ..services.s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class MissingExternalObjectError(Exception):
    """Raised when a finalized storage mapping points to a non-existent S3 object."""


class IrBinaryExtension(models.AbstractModel):
    if HAS_NATIVE_STREAM:
        _inherit = 'ir.binary'
    else:
        _name = 'ir.binary'
        _description = 'Binary Content Compatibility Service'

    def _get_stream_from(
        self, record, field_name='raw', filename=None, filename_field='name',
        mimetype=None, default_mimetype='application/octet-stream',
    ):
        if record._name == 'ir.attachment':
            try:
                check_access = getattr(record, 'check_access', None)
                if check_access:
                    check_access('read')
                else:
                    record.check('read')
            except Exception:
                return None
            mapping = self.env['attachment.storage.mapping'].sudo().search([
                ('attachment_id', '=', record.id),
                ('status', '=', 'finalized'),
                ('company_id', '=', record.company_id.id),
            ], limit=1)
            if mapping:
                bridge = (
                    ProS3Bridge(self.env)
                    if mapping.bucket_id else S3Bridge(self.env)
                )
                try:
                    get_kwargs = (
                        {'config': mapping.bucket_id._s3_config()}
                        if mapping.bucket_id else {}
                    )
                    content = bridge.get_object(
                        mapping.s3_bucket, mapping.s3_key, **get_kwargs
                    )
                except S3BridgeError as exc:
                    _logger.error(
                        'S3 object missing for finalized mapping '
                        'attachment=%s bucket=%s key=%s: %s',
                        record.id, mapping.s3_bucket, mapping.s3_key, exc,
                    )
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
        try:
            return super()._get_stream_from(
                record, field_name=field_name, filename=filename,
                filename_field=filename_field, mimetype=mimetype,
                default_mimetype=default_mimetype,
            )
        except (AttributeError, RuntimeError):
            return None


if not HAS_NATIVE_STREAM:
    class IrHttpBinaryExtension(models.AbstractModel):
        _inherit = 'ir.http'

        def binary_content(self, xmlid=None, model='ir.attachment', id=None, field='datas',
                           unique=False, filename=None, filename_field='name', download=False,
                           mimetype=None, default_mimetype='application/octet-stream',
                           access_token=None):
            """Serve finalized S3 objects through the legacy Odoo 15 binary API."""
            result = super().binary_content(
                xmlid=xmlid, model=model, id=id, field=field, unique=unique,
                filename=filename, filename_field=filename_field, download=download,
                mimetype=mimetype, default_mimetype=default_mimetype,
                access_token=access_token,
            )
            if model != 'ir.attachment' or not id:
                return result

            record = self.env['ir.attachment'].browse(int(id)).exists()
            if not record:
                return result
            mapping = self.env['attachment.storage.mapping'].sudo().search([
                ('attachment_id', '=', record.id),
                ('status', '=', 'finalized'),
                ('company_id', '=', record.company_id.id),
            ], limit=1)
            if not mapping or not mapping.bucket_id:
                return result
            try:
                content = ProS3Bridge(self.env).get_object(
                    mapping.s3_bucket, mapping.s3_key,
                    config=mapping.bucket_id._s3_config(),
                )
            except S3BridgeError as exc:
                _logger.error(
                    'S3 object unavailable; using retained filestore attachment=%s: %s',
                    record.id, exc,
                )
                return result

            status, headers, _content = result
            return status, headers, base64.b64encode(content)