import base64
import logging

from odoo import fields, _
from odoo.exceptions import UserError

from .s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class RestoreService:
    """One-click restore: re-download a verified object from S3 back into the
    Odoo filestore (or DB for small files) via the standard binary writer."""

    def __init__(self, env):
        self.env = env
        self._bridge = ProS3Bridge(env)

    def restore_mapping(self, mapping):
        mp = mapping
        if mp.status != 'finalized':
            raise UserError(_(
                'This attachment is not ready to restore. Wait until its '
                'storage mapping is finalized, then try again.'
            ))
        bucket = mp.bucket_id
        config = bucket._s3_config() if bucket else None
        data = self._bridge.get_object(
            mp.s3_bucket, mp.s3_key, config=config,
        )
        att = mp.attachment_id.sudo()
        att.datas = base64.b64encode(data)
        now = fields.Datetime.now()
        mp.write({
            'cleanup_state': 'kept',
            'removed_at': False,
            'restored': True,
            'restored_at': now,
        })
        self.env['attachment.audit.log']._log(
            'restore', result='success',
            attachment_id=att.id,
            attachment_name=att.name,
            mapping_id=mp.id,
        )
        return {'restored_bytes': len(data)}

    def find_restore_candidates(self, company_id=False, limit=None):
        domain = [
            ('status', '=', 'finalized'),
            ('cleanup_state', 'in', ('quarantined', 'cleaned')),
        ]
        if company_id:
            domain.append(('company_id', '=', company_id))
        return self.env['attachment.storage.mapping'].search(
            domain, limit=limit, order='id',
        )

    def run_batch(self, batch):
        if batch.state != 'draft':
            raise UserError(_(
                'Only draft restore batches can run. Create a new batch to '
                'restore additional attachments.'
            ))
        if batch.mapping_ids:
            candidates = batch.mapping_ids
        else:
            candidates = self.find_restore_candidates(
                company_id=(
                    batch.company_id.id if batch.company_id else False
                ),
                limit=batch.limit,
            )
        batch.write({
            'state': 'running',
            'started_at': fields.Datetime.now(),
            'total': len(candidates),
        })
        restored = 0
        failed = 0
        restored_bytes = 0
        processed = self.env['attachment.storage.mapping']
        for mp in candidates:
            try:
                result = self.restore_mapping(mp)
                processed |= mp
                restored += 1
                restored_bytes += result['restored_bytes']
            except Exception:
                _logger.exception('Restore failed for mapping %s', mp.id)
                failed += 1
        batch.write({
            'state': 'done',
            'finished_at': fields.Datetime.now(),
            'restored': restored,
            'failed': failed,
            'restored_bytes': restored_bytes,
            'mapping_ids': [(6, 0, processed.ids)],
        })
