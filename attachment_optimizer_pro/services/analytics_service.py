from odoo.addons.attachment_optimizer.services.utils import human_size


class AnalyticsService:
    """Storage cost analytics: local vs migrated vs reclaimed volume."""

    def __init__(self, env):
        self.env = env

    def get_report(self):
        env = self.env

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(file_size), 0)
            FROM ir_attachment
            WHERE type = 'binary'
              AND store_fname IS NOT NULL
              AND res_model <> 'ir.ui.view'
        """)
        total_count, total_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.status = 'finalized'
        """)
        migrated_count, migrated_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.cleanup_state IN ('quarantined', 'cleaned')
        """)
        reclaimed_count, reclaimed_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT m.s3_bucket, COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.status = 'finalized'
            GROUP BY m.s3_bucket
            ORDER BY 3 DESC
        """)
        buckets = [{
            'bucket': row[0],
            'count': row[1],
            'bytes': row[2],
        } for row in env.cr.fetchall()]

        failed = env['attachment.migration.operation'].search_count([
            ('state', '=', 'failed'),
        ])

        return {
            'total_attachments': total_count,
            'total_bytes': total_bytes,
            'total_display': human_size(total_bytes),
            'migrated': migrated_count,
            'migrated_bytes': migrated_bytes,
            'migrated_display': human_size(migrated_bytes),
            'migration_pct': round(
                migrated_bytes / total_bytes * 100, 1
            ) if total_bytes else 0,
            'reclaimed': reclaimed_count,
            'reclaimed_bytes': reclaimed_bytes,
            'reclaimed_display': human_size(reclaimed_bytes),
            'failed': failed,
            'buckets': buckets,
        }
