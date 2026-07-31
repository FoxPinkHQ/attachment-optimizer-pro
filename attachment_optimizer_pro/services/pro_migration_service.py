import base64
import hashlib
import logging

from odoo import fields, _

from .s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class ProMigrationService:
    """Full migration pipeline for routed operations targeting a specific
    bucket profile. Mirrors the free edition flow but uses per-operation
    bucket credentials instead of the global default bucket."""

    def __init__(self, env):
        self.env = env
        self._bridge = ProS3Bridge(env)

    def process_operation(self, operation):
        op = operation
        bucket = op.bucket_id
        if not bucket:
            raise ValueError(_('Operation has no target bucket profile'))
        config = bucket._s3_config()
        Mapping = self.env['attachment.storage.mapping']
        attachment = op.attachment_id.sudo()

        binary = self._read_binary(attachment)
        checksum = hashlib.sha256(binary).hexdigest()
        s3_key = 'objects/%s/%s' % (checksum[:2], checksum)

        if not self._bridge.head(bucket.name, s3_key, config=config):
            self._bridge.upload(bucket.name, s3_key, binary, config=config)

        mapping = Mapping.create_mapping(
            attachment_id=attachment.id,
            s3_bucket=bucket.name,
            s3_key=s3_key,
            s3_region=bucket.region,
        )
        mapping.write({'bucket_id': bucket.id})
        mapping.action_update_status('uploading')
        mapping.action_update_status('uploaded')
        op.transition_state('uploaded', mapping_id=mapping.id)

        verified = self._bridge.verify(
            bucket.name, s3_key, checksum, config=config,
        )
        if not verified:
            mapping.action_update_status(
                'verification_failed', error='Checksum mismatch after upload',
            )
            op.transition_state(
                'failed',
                error_message='Checksum mismatch',
                completed_at=fields.Datetime.now(),
            )
            self.env['attachment.audit.log']._log(
                'verify', result='failure',
                attachment_id=attachment.id,
                attachment_name=attachment.name,
                operation_id=op.id,
                mapping_id=mapping.id,
                error_message='Checksum mismatch after upload',
            )
            return

        mapping.action_update_status('verified', checksum=checksum)
        op.transition_state('verified')
        mapping.action_update_status('finalized')
        op.transition_state('finalized', completed_at=fields.Datetime.now())
        self.env['attachment.audit.log']._log(
            'verify_finalize', result='success',
            attachment_id=attachment.id,
            attachment_name=attachment.name,
            operation_id=op.id,
            mapping_id=mapping.id,
        )

    def _read_binary(self, attachment):
        att = attachment.sudo()
        if att.datas:
            return base64.b64decode(att.datas)
        raise ValueError(_('Attachment %s has no binary data') % att.id)
