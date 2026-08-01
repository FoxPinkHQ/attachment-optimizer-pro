import base64
import hashlib
import logging

from odoo import fields, _
from odoo.exceptions import UserError

from .s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class CleanupService:
    """Safe local cleanup: reclam filestore space only after the stored
    checksum matches the local binary. Nothing is deleted before
    verification. Removed copies stay in a quarantine window and can be
    restored from S3."""

    def __init__(self, env):
        self.env = env
        self._bridge = ProS3Bridge(env)

    def _mapping_age_days(self, mapping):
        ref = mapping.verification_timestamp or mapping.create_date
        if not ref:
            return 0
        seconds = (fields.Datetime.now() - ref).total_seconds()
        return max(0, int(seconds) // 86400)

    def eligible_mappings(self, mappings=None, retention_days=None,
                          company_id=False, limit=None):
        domain = [
            ('status', '=', 'finalized'),
            ('cleanup_state', 'in', ('kept',)),
            ('removed_at', '=', False),
        ]
        if mappings:
            domain.append(('id', 'in', mappings.ids))
        if company_id:
            domain.append(('company_id', '=', company_id))
        found = self.env['attachment.storage.mapping'].search(domain)
        result = self.env['attachment.storage.mapping']
        for mp in found:
            if retention_days is not None \
                    and self._mapping_age_days(mp) < retention_days:
                continue
            att = mp.attachment_id.sudo()
            if not (att.store_fname or att.db_datas):
                continue
            result |= mp
        if limit:
            result = result[:limit]
        return result

    def preview_mappings(self, mappings, retention_days=0, live=True):
        """Return a read-only safety report for the requested mappings."""
        eligible = self.env['attachment.storage.mapping']
        blocked = {}
        remote_verified = 0

        def block(reason):
            blocked[reason] = blocked.get(reason, 0) + 1

        for mapping in mappings:
            if mapping.status != 'finalized':
                block(_('Not finalized'))
                continue
            if mapping.cleanup_state != 'kept' or mapping.removed_at:
                block(_('Local copy already processed'))
                continue
            if self._mapping_age_days(mapping) < retention_days:
                block(_('Retention period not completed'))
                continue
            local = self._read_local_binary(mapping.attachment_id)
            if local is None:
                block(_('No local copy to reclaim'))
                continue
            if not mapping.checksum_sha256:
                block(_('Missing SHA-256'))
                continue
            if hashlib.sha256(local).hexdigest() != mapping.checksum_sha256:
                block(_('Local checksum mismatch'))
                continue
            if live:
                bucket = mapping.bucket_id
                config = bucket._s3_config() if bucket else None
                try:
                    verified = self._bridge.verify(
                        mapping.s3_bucket, mapping.s3_key,
                        mapping.checksum_sha256, config=config,
                    )
                except Exception:
                    _logger.exception(
                        'Dry-run remote verification failed for mapping %s',
                        mapping.id,
                    )
                    verified = False
                if not verified:
                    block(_('Remote object missing or checksum mismatch'))
                    continue
                remote_verified += 1
            eligible |= mapping

        return {
            'selected': len(mappings),
            'eligible': eligible,
            'eligible_count': len(eligible),
            'eligible_bytes': self.estimate_reclaimed(eligible),
            'blocked_count': sum(blocked.values()),
            'blocked': blocked,
            'remote_verified': remote_verified,
            'live': live,
        }
    def estimate_reclaimed(self, mappings):
        return sum(
            (mp.attachment_id.sudo().file_size or 0) for mp in mappings
        )

    def _read_local_binary(self, attachment):
        att = attachment.sudo()
        if att.datas:
            return base64.b64decode(att.datas)
        return None

    def cleanup_mapping(self, mapping):
        """Remove the local copy of a finalized mapping after verifying the
        checksum against the local binary. Returns a result dict."""
        att = mapping.attachment_id.sudo()
        local = self._read_local_binary(att)
        if local is None:
            # No local copy to reclaim; record as already cleaned.
            mapping.write({
                'cleanup_state': 'cleaned',
                'removed_at': fields.Datetime.now(),
            })
            return {'reclaimed': 0, 'changed': True, 'skipped': False}

        def skip(reason):
            self.env['attachment.audit.log']._log(
                'cleanup', result='failure', attachment_id=att.id,
                attachment_name=att.name, mapping_id=mapping.id,
                error_message=reason,
            )
            return {
                'reclaimed': 0, 'changed': False, 'skipped': True,
                'reason': reason,
            }

        if not mapping.checksum_sha256:
            return skip('Missing SHA-256; local copy preserved')

        actual = hashlib.sha256(local).hexdigest()
        if actual != mapping.checksum_sha256:
            return skip('Local checksum mismatch; local copy preserved')

        bucket = mapping.bucket_id
        config = bucket._s3_config() if bucket else None
        try:
            remote_verified = self._bridge.verify(
                mapping.s3_bucket, mapping.s3_key,
                mapping.checksum_sha256, config=config,
            )
        except Exception:
            _logger.exception(
                'Remote verification failed before cleanup for mapping %s',
                mapping.id,
            )
            remote_verified = False
        if not remote_verified:
            return skip(
                'Remote object unavailable or checksum mismatch; '
                'local copy preserved'
            )
        size = att.file_size or 0
        now = fields.Datetime.now()
        att.datas = False
        mapping.write({
            'cleanup_state': 'quarantined',
            'removed_at': now,
            'quarantined_at': now,
        })
        self.env['attachment.audit.log']._log(
            'cleanup', result='success',
            attachment_id=att.id,
            attachment_name=att.name,
            mapping_id=mapping.id,
        )
        return {'reclaimed': size, 'changed': True, 'skipped': False}

    def run_mappings(self, batch, mappings):
        if batch.state != 'draft':
            raise UserError(_(
                'Only draft cleanup batches can run. Create a new batch to '
                'clean additional local copies.'
            ))
        batch.write({
            'state': 'running',
            'started_at': fields.Datetime.now(),
            'total': len(mappings),
        })
        reclaimed = 0
        cleaned = 0
        skipped = 0
        failed = 0
        processed = self.env['attachment.storage.mapping']
        for mp in mappings:
            try:
                result = self.cleanup_mapping(mp)
                processed |= mp
                if result['changed']:
                    cleaned += 1
                    reclaimed += result['reclaimed']
                else:
                    skipped += 1
            except Exception:
                _logger.exception('Cleanup failed for mapping %s', mp.id)
                failed += 1
        batch.write({
            'state': 'done',
            'finished_at': fields.Datetime.now(),
            'cleaned': cleaned,
            'skipped': skipped,
            'failed': failed,
            'reclaimed_bytes': reclaimed,
            'mapping_ids': [(6, 0, processed.ids)],
        })

    def run_batch(self, batch):
        candidates = self.eligible_mappings(
            mappings=batch.mapping_ids if batch.mapping_ids else None,
            retention_days=batch.retention_days,
            company_id=batch.company_id.id if batch.company_id else False,
            limit=batch.limit,
        )
        self.run_mappings(batch, candidates)

    def finalize_quarantine(self, quarantine_days):
        """Move quarantined mappings past their safety window to 'cleaned'."""
        from datetime import timedelta

        Mapping = self.env['attachment.storage.mapping']
        cut_off = fields.Datetime.now() - timedelta(days=quarantine_days)
        mappings = Mapping.search([
            ('cleanup_state', '=', 'quarantined'),
            ('removed_at', '!=', False),
            ('removed_at', '<=', cut_off),
        ])
        mappings.write({'cleanup_state': 'cleaned'})
        for mp in mappings:
            self.env['attachment.audit.log']._log(
                'quarantine', result='success',
                attachment_id=mp.attachment_id.id,
                attachment_name=mp.attachment_id.name,
                mapping_id=mp.id,
            )
        return len(mappings)
