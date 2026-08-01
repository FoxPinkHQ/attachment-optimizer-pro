import base64
import hashlib
from unittest.mock import patch

from odoo import fields
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
        verify_target = (
            'odoo.addons.attachment_optimizer_pro.services.cleanup_service.'
            'ProS3Bridge.verify'
        )
        self.verify_patch = patch(verify_target, return_value=True)
        self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)

    def test_auto_cleanup_pauses_without_current_restore_evidence(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('attachment_storage_pro.cleanup.enabled', True)
        params.set_param('attachment_storage_pro.restore_drill.enabled', True)
        before = self.env['attachment.cleanup.batch'].search_count([])
        result = self.env['attachment.cleanup.batch'].action_run_auto_cleanup()
        self.assertFalse(result)
        self.assertEqual(
            self.env['attachment.cleanup.batch'].search_count([]), before,
        )
        audit = self.env['attachment.audit.log'].search([
            ('action', '=', 'cleanup'),
            ('result', '=', 'failure'),
        ], order='id DESC', limit=1)
        self.assertIn('recovery assurance', audit.error_message)

    def test_auto_cleanup_runs_with_healthy_restore_evidence(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('attachment_storage_pro.cleanup.enabled', True)
        params.set_param('attachment_storage_pro.cleanup.retention_days', 365)
        params.set_param('attachment_storage_pro.restore_drill.enabled', True)
        drill = self.env['attachment.restore.drill'].create({
            'company_id': self.env.company.id,
        })
        drill.sudo().write({
            'state': 'passed', 'run_at': fields.Datetime.now(),
            'tested': 1, 'passed': 1,
        })
        self.assertTrue(
            self.env['attachment.cleanup.batch'].action_run_auto_cleanup()
        )
    def test_cleanup_wizard_requires_safety_preview(self):
        wizard = self.env['attachment.cleanup.confirm'].create({
            'candidate_ids': [(6, 0, self.mapping.ids)],
        })
        with self.assertRaisesRegex(UserError, 'Run Safety Preview'):
            wizard.action_confirm()

    def test_cleanup_preview_reports_safe_reclaim(self):
        wizard = self.env['attachment.cleanup.confirm'].create({
            'candidate_ids': [(6, 0, self.mapping.ids)],
            'retention_days': 0,
        })
        action = wizard.action_preview()
        self.assertTrue(wizard.safety_previewed)
        self.assertEqual(wizard.count, 1)
        self.assertEqual(wizard.blocked_count, 0)
        self.assertEqual(wizard.remote_verified_count, 1)
        self.assertEqual(wizard.estimated_bytes, len(b'cleanup me now'))
        self.assertEqual(action['res_id'], wizard.id)

    def test_cleanup_preview_explains_remote_failure(self):
        wizard = self.env['attachment.cleanup.confirm'].create({
            'candidate_ids': [(6, 0, self.mapping.ids)],
            'retention_days': 0,
        })
        with patch(
            'odoo.addons.attachment_optimizer_pro.services.cleanup_service.'
            'ProS3Bridge.verify', return_value=False,
        ):
            wizard.action_preview()
        self.assertEqual(wizard.count, 0)
        self.assertEqual(wizard.blocked_count, 1)
        self.assertIn('Remote object missing', wizard.blocked_summary)
        self.assertTrue(self.mapping.attachment_id.sudo().datas)
    def test_cleanup_action_warns_when_a_mapping_fails(self):
        batch = self.env['attachment.cleanup.batch'].create({
            'retention_days': 0,
            'quarantine_days': 7,
            'mapping_ids': [(6, 0, self.mapping.ids)],
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
        self.assertEqual(batch.failed_mapping_ids, self.mapping)
        self.assertIn('simulated failure', batch.issue_details)
        retry_action = batch.action_retry_failed()
        retry = self.env['attachment.cleanup.batch'].browse(
            retry_action['res_id']
        )
        self.assertEqual(retry.retry_of_id, batch)
        self.assertEqual(retry.failed, 0)
        self.assertEqual(retry.cleaned, 1)
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

    def test_cleanup_preserves_local_copy_without_checksum(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        self.mapping.checksum_sha256 = False
        result = CleanupService(self.env).cleanup_mapping(self.mapping)
        self.assertFalse(result['changed'])
        self.assertTrue(result['skipped'])
        self.assertIn('Missing SHA-256', result['reason'])
        self.assertTrue(self.mapping.attachment_id.sudo().datas)

    def test_cleanup_preserves_local_copy_when_remote_verification_fails(self):
        from odoo.addons.attachment_optimizer_pro.services.cleanup_service \
            import CleanupService
        service = CleanupService(self.env)
        with patch.object(service._bridge, 'verify', return_value=False):
            result = service.cleanup_mapping(self.mapping)
        self.assertFalse(result['changed'])
        self.assertTrue(result['skipped'])
        self.assertIn('Remote object unavailable', result['reason'])
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
