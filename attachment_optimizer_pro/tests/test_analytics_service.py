from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestAnalyticsService(TransactionCase):

    def test_get_report_structure(self):
        from odoo.addons.attachment_optimizer_pro.services.analytics_service \
            import AnalyticsService
        report = AnalyticsService(self.env).get_report()
        for key in (
            'total_attachments', 'total_bytes', 'total_display',
            'migrated', 'migrated_bytes', 'migrated_display',
            'migration_pct', 'reclaimed', 'reclaimed_bytes',
            'reclaimed_display', 'reclaimable', 'reclaimable_bytes',
            'reclaimable_display', 'failed', 'buckets', 'savings',
            'recovery_assurance',
        ):
            self.assertIn(key, report)
        self.assertEqual(report['migration_pct'], 0)
        for key in (
            'status', 'status_label', 'company_count', 'covered_companies',
            'coverage_display', 'overdue_companies', 'failed_drills',
            'tested', 'passed', 'failed', 'last_run', 'interval_days',
        ):
            self.assertIn(key, report['recovery_assurance'])
        for key in (
            'cost_per_gib', 'cost_display', 'reclaimed_monthly',
            'reclaimed_monthly_display', 'reclaimable_monthly',
            'reclaimable_monthly_display', 'potential_annual',
            'potential_annual_display',
        ):
            self.assertIn(key, report['savings'])

    def test_recovery_assurance_reports_current_evidence(self):
        from odoo.addons.attachment_optimizer_pro.services.analytics_service \
            import AnalyticsService
        self.env['ir.config_parameter'].sudo().set_param(
            'attachment_storage_pro.restore_drill.enabled', True,
        )
        drill = self.env['attachment.restore.drill'].create({
            'company_id': self.env.company.id,
            'sample_size': 3,
        })
        drill.sudo().write({
            'state': 'passed',
            'run_at': fields.Datetime.now(),
            'tested': 3,
            'passed': 3,
            'failed': 0,
        })
        assurance = AnalyticsService(self.env).get_report()[
            'recovery_assurance'
        ]
        self.assertEqual(assurance['status'], 'healthy')
        self.assertEqual(assurance['covered_companies'], 1)
        self.assertEqual(assurance['tested'], 3)
        self.assertEqual(assurance['failed'], 0)

    def test_report_tracks_migrated_and_reclaimed(self):
        from odoo.addons.attachment_optimizer_pro.services.analytics_service \
            import AnalyticsService
        self.env['ir.config_parameter'].sudo().set_param(
            'attachment_storage_pro.cost.local_usd_per_gib_month', '2.0',
        )
        before = AnalyticsService(self.env).get_report()
        bucket = self.env['attachment.storage.bucket'].create({
            'name': 'analytics-bucket',
            'is_default': True,
        })
        att = self.env['ir.attachment'].create({
            'name': 'analytics.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': 'YW5hbHl0aWNz',
        })
        self.env['attachment.storage.mapping'].create({
            'attachment_id': att.id,
            's3_bucket': bucket.name,
            's3_key': 'objects/ab/key',
            's3_region': 'us-east-1',
            'status': 'finalized',
            'cleanup_state': 'cleaned',
            'bucket_id': bucket.id,
        })
        report = AnalyticsService(self.env).get_report()
        self.assertEqual(report['reclaimed'] - before['reclaimed'], 1)
        self.assertEqual(report['migrated'] - before['migrated'], 1)
        self.assertEqual(
            report['migration_pct'],
            round(report['migrated_bytes'] / report['total_bytes'] * 100, 1),
        )
        bucket_rows = [
            row for row in report['buckets']
            if row['bucket'] == bucket.name
        ]
        self.assertEqual(len(bucket_rows), 1)
        self.assertEqual(bucket_rows[0]['count'], 1)
        expected_monthly = report['reclaimed_bytes'] / (1024.0 ** 3) * 2.0
        self.assertAlmostEqual(
            report['savings']['reclaimed_monthly'], expected_monthly,
        )
        self.assertAlmostEqual(
            report['savings']['potential_annual'],
            (
                report['reclaimed_bytes'] + report['reclaimable_bytes']
            ) / (1024.0 ** 3) * 2.0 * 12,
        )

    def test_local_storage_cost_cannot_be_negative(self):
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'pro_local_storage_cost_per_gib': -1,
            })

    def test_report_excludes_disallowed_company(self):
        from odoo.addons.attachment_optimizer_pro.services.analytics_service \
            import AnalyticsService
        other_company = self.env['res.company'].create({
            'name': 'Analytics Company B',
        })
        bucket = self.env['attachment.storage.bucket'].sudo().create({
            'name': 'analytics-company-b',
            'company_ids': [(6, 0, [other_company.id])],
        })
        manager_group = self.env.ref(
            'attachment_optimizer.group_storage_optimization_manager',
        )
        user = self.env['res.users'].create({
            'name': 'Analytics Company A Manager',
            'login': 'analytics_company_a_manager',
            'notification_type': 'email',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                manager_group.id,
            ])],
        })
        user_env = self.env(user=user)
        before = AnalyticsService(user_env).get_report()
        att = self.env['ir.attachment'].sudo().create({
            'name': 'company-b.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': 'YW5hbHl0aWNz',
            'company_id': other_company.id,
        })
        self.env['attachment.storage.mapping'].sudo().create({
            'attachment_id': att.id,
            'company_id': other_company.id,
            's3_bucket': bucket.name,
            's3_key': 'objects/company-b/key',
            's3_region': 'us-east-1',
            'status': 'finalized',
            'cleanup_state': 'cleaned',
            'bucket_id': bucket.id,
        })
        report = AnalyticsService(user_env).get_report()
        self.assertEqual(report['total_attachments'], before['total_attachments'])
        self.assertEqual(report['migrated'], before['migrated'])
        self.assertEqual(report['reclaimed'], before['reclaimed'])
        self.assertNotIn(
            bucket.name, [row['bucket'] for row in report['buckets']],
        )