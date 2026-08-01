from datetime import timedelta

from odoo import fields
from odoo.addons.attachment_optimizer.services.utils import human_size


class AnalyticsService:
    """Storage analytics scoped to the user's allowed companies."""

    def __init__(self, env):
        self.env = env

    def get_report(self):
        env = self.env
        company_ids = env.companies.ids
        from .cleanup_service import CleanupService
        from .pro_config import ProConfig

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(file_size), 0)
            FROM ir_attachment
            WHERE type = 'binary'
              AND store_fname IS NOT NULL
              AND res_model <> 'ir.ui.view'
              AND (company_id IS NULL OR company_id = ANY(%s))
        """, (company_ids,))
        total_count, total_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.status = 'finalized'
              AND m.company_id = ANY(%s)
        """, (company_ids,))
        migrated_count, migrated_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.cleanup_state IN ('quarantined', 'cleaned')
              AND m.company_id = ANY(%s)
        """, (company_ids,))
        reclaimed_count, reclaimed_bytes = env.cr.fetchone()

        env.cr.execute("""
            SELECT m.s3_bucket, COUNT(*), COALESCE(SUM(a.file_size), 0)
            FROM attachment_storage_mapping m
            JOIN ir_attachment a ON a.id = m.attachment_id
            WHERE m.status = 'finalized'
              AND m.company_id = ANY(%s)
            GROUP BY m.s3_bucket
            ORDER BY 3 DESC
        """, (company_ids,))
        buckets = [{
            'bucket': row[0],
            'count': row[1],
            'bytes': row[2],
            'display': human_size(row[2]),
        } for row in env.cr.fetchall()]

        failed = env['attachment.migration.operation'].search_count([
            ('state', '=', 'failed'),
        ])
        cleanup = CleanupService(env)
        eligible = cleanup.eligible_mappings(
            retention_days=ProConfig(env).retention_days(),
        )
        reclaimable_bytes = cleanup.estimate_reclaimed(eligible)
        cost_per_gib = ProConfig(env).local_storage_cost_per_gib()
        gib = 1024.0 ** 3
        reclaimed_monthly = reclaimed_bytes / gib * cost_per_gib
        reclaimable_monthly = reclaimable_bytes / gib * cost_per_gib
        potential_annual = (
            reclaimed_monthly + reclaimable_monthly
        ) * 12

        def usd(value):
            return '$%s' % format(value, ',.2f')

        config = ProConfig(env)
        interval_days = config.restore_drill_interval_days()
        now = fields.Datetime.now()
        latest_drills = []
        overdue_companies = 0
        for company in env.companies:
            drill = env['attachment.restore.drill'].search([
                ('company_id', '=', company.id),
                ('state', 'in', ('passed', 'failed')),
            ], order='run_at DESC, id DESC', limit=1)
            if drill:
                latest_drills.append(drill)
                if not drill.run_at or (
                    drill.run_at + timedelta(days=interval_days) <= now
                ):
                    overdue_companies += 1
            else:
                overdue_companies += 1
        failed_drills = sum(
            1 for drill in latest_drills if drill.state == 'failed'
        )
        last_run = max(
            (drill.run_at for drill in latest_drills if drill.run_at),
            default=False,
        )
        if not config.restore_drill_enabled():
            assurance_status = 'disabled'
        elif failed_drills:
            assurance_status = 'failed'
        elif overdue_companies:
            assurance_status = 'overdue'
        else:
            assurance_status = 'healthy'
        assurance_labels = {
            'disabled': 'SCHEDULE OFF',
            'failed': 'ATTENTION',
            'overdue': 'DUE',
            'healthy': 'HEALTHY',
        }
        recovery_assurance = {
            'enabled': config.restore_drill_enabled(),
            'status': assurance_status,
            'status_label': assurance_labels[assurance_status],
            'company_count': len(env.companies),
            'covered_companies': len(latest_drills),
            'coverage_display': '%d / %d companies' % (
                len(latest_drills), len(env.companies),
            ),
            'overdue_companies': overdue_companies,
            'failed_drills': failed_drills,
            'tested': sum(drill.tested for drill in latest_drills),
            'passed': sum(drill.passed for drill in latest_drills),
            'failed': sum(drill.failed for drill in latest_drills),
            'last_run': fields.Datetime.to_string(last_run) if last_run else False,
            'interval_days': interval_days,
        }

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
            'reclaimable': len(eligible),
            'reclaimable_bytes': reclaimable_bytes,
            'reclaimable_display': human_size(reclaimable_bytes),
            'failed': failed,
            'recovery_assurance': recovery_assurance,
            'savings': {
                'cost_per_gib': cost_per_gib,
                'cost_display': '$%s/GiB/month' % format(
                    cost_per_gib, ',.4f'
                ).rstrip('0').rstrip('.'),
                'reclaimed_monthly': reclaimed_monthly,
                'reclaimed_monthly_display': usd(reclaimed_monthly),
                'reclaimable_monthly': reclaimable_monthly,
                'reclaimable_monthly_display': usd(reclaimable_monthly),
                'potential_annual': potential_annual,
                'potential_annual_display': usd(potential_annual),
            },
            'buckets': buckets,
        }
