import base64
import hashlib
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestCleanupService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Bucket = self.env['attachment.storage.bucket']
        self.bucket = self.Bucket.create({
            'name': 'cleanup-bucket',
            'is_default': True,
        })
        self.att = self.env['ir.attachment'].create({
            'name': 'cleanup-me.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': base64.b64encode(b'cleanup me now').decode(),
        })
        checksum = hashlib.sha256(b'cleanup me now').hexdigest()
        self.mapping = self.env['attachment.storage.mapping'].create({
            'attachment_id': self.att.id,
            'company_id': self.env.company.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/%s/%s' % (checksum[:2], checksum),
            's3_region': 'us-east-1',
            'status': 'finalized',
            'checksum_sha256': checksum,
            'bucket_id': self.bucket.id,
        })

    def test_cleanup_wizard_rejects_empty_selection(self):
        wizard = self.env['attachment.cleanup.confirm'].new({
            'mapping_ids': [(6, 0, [])],
        })
        with self.assertRaisesRegex(UserError, 'No local copies are eligible'):
            wizard.action_confirm()
    def test_cleanup_action_warns_when_a_mapping_fails(self):
        batch = self.env['attachment.cleanup.batch'].create({
            'retention_days': 0,
            'quarantine_days': 7,
        })
        target = (
            'odoo.addons.attachment_optimizer_pro.services.cleanup_service.'
            'CleanupService.cleanup_mapping'
        )
        with patch(target, side_effect=RuntimeError('simulated failure')):
            action = batch.action_run()
        self.assertEqual(batch.failed, 1)
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('Review the batch details', action['params']['message'])
    def test_cleanup_removes_local_copy_after_verification(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        service = CleanupService(self.env)
        result = service.cleanup_mapping(self.mapping)
        self.assertTrue(result['changed'])
        self.assertEqual(result['reclaimed'], len(b'cleanup me now'))
        self.assertEqual(self.mapping.cleanup_state, 'quarantined')
        self.assertTrue(self.mapping.removed_at)
        self.assertFalse(self.mapping.attachment_id.sudo().datas)

    def test_cleanup_skips_on_checksum_mismatch(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        self.mapping.checksum_sha256 = '0' * 64
        service = CleanupService(self.env)
        result = service.cleanup_mapping(self.mapping)
        self.assertFalse(result['changed'])
        self.assertTrue(result['skipped'])
        self.assertEqual(self.mapping.cleanup_state, 'kept')
        self.assertTrue(self.mapping.attachment_id.sudo().datas)

    def test_cleanup_is_idempotent(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        service = CleanupService(self.env)
        service.cleanup_mapping(self.mapping)
        # Second call: no local copy present, recorded as cleaned.
        result = service.cleanup_mapping(self.mapping)
        self.assertTrue(result['changed'])
        self.assertEqual(self.mapping.cleanup_state, 'cleaned')

    def test_eligible_mappings_respect_retention(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        service = CleanupService(self.env)
        # retention 0 → eligible (mapping created now)
        eligible = service.eligible_mappings(retention_days=0)
        self.assertIn(self.mapping, eligible)
        # retention 365 → not eligible
        eligible = service.eligible_mappings(retention_days=365)
        self.assertNotIn(self.mapping, eligible)

    def test_finalize_quarantine(self):
        from datetime import timedelta

        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        from odoo import fields
        service = CleanupService(self.env)
        service.cleanup_mapping(self.mapping)
        # Force removed_at into the past beyond the quarantine window.
        self.mapping.write({
            'removed_at': fields.Datetime.now() - timedelta(days=30),
        })
        count = service.finalize_quarantine(quarantine_days=7)
        self.assertEqual(count, 1)
        self.assertEqual(self.mapping.cleanup_state, 'cleaned')
