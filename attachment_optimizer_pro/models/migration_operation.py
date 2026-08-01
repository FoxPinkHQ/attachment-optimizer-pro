from odoo import api, fields, models


class MigrationOperation(models.Model):
    _inherit = 'attachment.migration.operation'

    bucket_id = fields.Many2one(
        'attachment.storage.bucket', string='Bucket Profile',
        ondelete='set null',
    )
    routed = fields.Boolean(string='Routed by Rule', default=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('retry_of') and 'bucket_id' not in vals:
                src = self.browse(vals['retry_of'])
                if src:
                    vals['bucket_id'] = src.bucket_id.id
                    vals['routed'] = src.routed
        return super().create(vals_list)

    @api.model
    def _claim_routed_batch(self, limit=10, worker_id=None):
        """Claim routed (draft) operations atomically. Never touched by the
        free edition queue because they are not in 'queued' state."""
        import uuid
        token = str(uuid.uuid4())
        worker = worker_id or ('pro-worker-%s' % token[:8])
        self.env.cr.execute("""
            WITH claimed AS (
                SELECT id
                FROM attachment_migration_operation
                WHERE state = 'draft' AND bucket_id IS NOT NULL AND routed = TRUE
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE attachment_migration_operation
            SET
                state = 'uploading',
                processing_token = %s,
                worker_id = %s,
                claimed_at = NOW(),
                heartbeat_at = NOW(),
                started_at = NOW()
            WHERE id IN (SELECT id FROM claimed)
            RETURNING id
        """, (limit, token, worker))
        ids = [r[0] for r in self.env.cr.fetchall()]
        claimed = self.browse(ids)
        claimed.invalidate_cache()
        for op in claimed:
            self.env['attachment.audit.log']._log(
                'claim', result='success',
                attachment_id=op.attachment_id.id,
                operation_id=op.id,
            )
        return claimed
