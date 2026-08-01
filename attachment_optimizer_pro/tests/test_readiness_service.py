from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase


class TestCleanupReadinessService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.bucket = self.env['attachment.storage.bucket'].create({
            'name': 'readiness-bucket',
            'is_default': True,
        })
        self.attachment = self.env['ir.attachment'].create({
            'name': 'readiness.pdf',
            'type': 'binary',
            'mimetype': 'application/pdf',
            'datas': 'cmVhZGluZXNz',
            'company_id': self.env.company.id,
        })
        self.mapping = self.env['attachment.storage.mapping'].create({
            'attachment_id': self.attachment.id,
            'company_id': self.env.company.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/readiness/key',
            's3_region': 'us-east-1',
            'status': 'finalized',
            'checksum_sha256': 'a' * 64,
            'verification_timestamp': fields.Datetime.now() - timedelta(days=31),
            'bucket_id': self.bucket.id,
        })
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage_pro.cleanup.retention_days', '30')
        ICP.set_param('attachment_storage_pro.cleanup.enabled', 'True')

    def test_local_readiness_reports_reclaimable_volume(self):
        from odoo.addons.attachment_optimizer_pro.services.readiness_service \
            import CleanupReadinessService
        result = CleanupReadinessService(self.env).check(live=False)
        self.assertTrue(result['ready'])
        self.assertEqual(result['eligible_count'], 1)
        self.assertGreater(result['eligible_bytes'], 0)
        self.assertIn('eligible_display', result)

    def test_missing_checksum_blocks_readiness(self):
        from odoo.addons.attachment_optimizer_pro.services.readiness_service \
            import CleanupReadinessService
        self.mapping.checksum_sha256 = False
        result = CleanupReadinessService(self.env).check(live=False)
        self.assertFalse(result['ready'])
        integrity = next(
            check for check in result['checks']
            if check['code'] == 'integrity'
        )
        self.assertEqual(integrity['status'], 'fail')

    def test_live_readiness_checks_bucket_and_sample_object(self):
        from odoo.addons.attachment_optimizer_pro.services.readiness_service \
            import CleanupReadinessService
        target = (
            'odoo.addons.attachment_optimizer_pro.services.'
            'readiness_service.ProS3Bridge'
        )
        with patch(target) as Bridge:
            Bridge.return_value.test_connection.return_value = {'status': 'ok'}
            Bridge.return_value.head.return_value = True
            result = CleanupReadinessService(self.env).check(live=True)
        self.assertTrue(result['ready'])
        statuses = {check['code']: check['status'] for check in result['checks']}
        self.assertEqual(statuses['live_connections'], 'pass')
        self.assertEqual(statuses['sample_objects'], 'pass')
