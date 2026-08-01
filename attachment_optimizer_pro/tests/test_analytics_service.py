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
            'reclaimed_display', 'failed', 'buckets',
        ):
            self.assertIn(key, report)
        self.assertEqual(report['migration_pct'], 0)

    def test_report_tracks_migrated_and_reclaimed(self):
        from odoo.addons.attachment_optimizer_pro.services.analytics_service \
            import AnalyticsService
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
