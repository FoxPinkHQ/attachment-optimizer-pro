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
        self.assertEqual(report['reclaimed'], 1)
        self.assertEqual(report['migrated'], 1)
        self.assertEqual(
            report['migration_pct'],
            round(report['migrated_bytes'] / report['total_bytes'] * 100, 1),
        )
        self.assertEqual(len(report['buckets']), 1)
        self.assertEqual(report['buckets'][0]['bucket'], bucket.name)
