import hashlib
import logging
import random

from odoo import _, fields

from .s3_bridge import ProS3Bridge

_logger = logging.getLogger(__name__)


class RestoreDrillService:
    """Prove that sampled remote objects are recoverable without mutation."""

    def __init__(self, env):
        self.env = env
        self._bridge = ProS3Bridge(env)

    def candidates(self, company_id, sample_size):
        pool_limit = max(sample_size * 10, 100)
        pool = self.env['attachment.storage.mapping'].search([
            ('company_id', '=', company_id),
            ('status', '=', 'finalized'),
            ('cleanup_state', 'in', ('quarantined', 'cleaned')),
            ('checksum_sha256', '!=', False),
        ], order='id DESC', limit=pool_limit)
        if len(pool) <= sample_size:
            return pool
        ids = random.SystemRandom().sample(pool.ids, sample_size)
        return self.env['attachment.storage.mapping'].browse(ids)

    def run(self, drill):
        if drill.state != 'draft':
            raise ValueError(_('Only draft restore drills can run.'))
        mappings = self.candidates(drill.company_id.id, drill.sample_size)
        drill.sudo().write({
            'state': 'running',
            'run_at': fields.Datetime.now(),
            'tested': len(mappings),
        })
        passed = failed = verified_bytes = 0
        lines = []
        for mapping in mappings:
            actual = False
            size = 0
            error = False
            result = 'fail'
            try:
                bucket = mapping.bucket_id
                config = bucket._s3_config() if bucket else None
                data = self._bridge.get_object(
                    mapping.s3_bucket, mapping.s3_key, config=config,
                )
                size = len(data)
                actual = hashlib.sha256(data).hexdigest()
                if actual == mapping.checksum_sha256:
                    result = 'pass'
                    passed += 1
                    verified_bytes += size
                else:
                    failed += 1
                    error = _('Downloaded object checksum does not match.')
            except Exception as exc:
                _logger.exception(
                    'Restore drill failed for mapping %s', mapping.id,
                )
                failed += 1
                error = str(exc)[:500]
            lines.append((0, 0, {
                'mapping_id': mapping.id,
                'result': result,
                'expected_checksum': mapping.checksum_sha256,
                'actual_checksum': actual,
                'verified_bytes': size,
                'error_message': error,
            }))
            self.env['attachment.audit.log']._log(
                'restore_drill',
                result='success' if result == 'pass' else 'failure',
                attachment_id=mapping.attachment_id.id,
                attachment_name=mapping.attachment_id.name,
                mapping_id=mapping.id,
                error_message=error,
            )
        drill.sudo().write({
            'state': 'passed' if mappings and not failed else 'failed',
            'passed': passed,
            'failed': failed,
            'verified_bytes': verified_bytes,
        })
        if lines:
            values = [dict(command[2], drill_id=drill.id) for command in lines]
            self.env['attachment.restore.drill.line'].sudo().create(values)
        return drill.state == 'passed'