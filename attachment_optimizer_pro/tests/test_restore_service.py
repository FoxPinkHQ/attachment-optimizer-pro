from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestRestoreService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Bucket = self.env['attachment.storage.bucket']
        self.bucket = self.Bucket.create({
            'name': 'restore-bucket',
            'is_default': True,
        })

    def _make_mapping(self, cleanup_state='cleaned'):
        att = self.env['ir.attachment'].create({
            'name': 'restore-me.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': 'cmVzdG9yZSBtZQ==',
        })
        return self.env['attachment.storage.mapping'].create({
            'attachment_id': att.id,
            'company_id': self.env.company.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/ab/restore-key',
            's3_region': 'us-east-1',
            'status': 'finalized',
            'cleanup_state': cleanup_state,
            'bucket_id': self.bucket.id,
        })

    def test_restore_wizard_rejects_empty_selection(self):
        wizard = self.env['attachment.restore.confirm'].new({
            'mapping_ids': [(6, 0, [])],
        })
        with self.assertRaisesRegex(UserError, 'No attachments are ready'):
            wizard.action_confirm()
    def test_restore_action_warns_when_a_mapping_fails(self):
        mapping = self._make_mapping(cleanup_state='cleaned')
        batch = self.env['attachment.restore.batch'].create({
            'mapping_ids': [(6, 0, mapping.ids)],
        })
        target = (
            'odoo.addons.attachment_optimizer_pro.services.restore_service.'
            'RestoreService.restore_mapping'
        )
        with patch(target, side_effect=RuntimeError('simulated failure')):
            action = batch.action_run()
        self.assertEqual(batch.failed, 1)
        self.assertEqual(action['params']['type'], 'warning')
        self.assertIn('retry failed attachments', action['params']['message'])
    def test_find_restore_candidates(self):
        from odoo.addons.attachment_optimizer_pro.services.restore_service \
            import RestoreService
        mp = self._make_mapping(cleanup_state='quarantined')
        candidates = RestoreService(self.env).find_restore_candidates()
        self.assertIn(mp, candidates)

    def test_kept_mappings_are_not_restore_candidates(self):
        from odoo.addons.attachment_optimizer_pro.services.restore_service \
            import RestoreService
        mp = self._make_mapping(cleanup_state='kept')
        candidates = RestoreService(self.env).find_restore_candidates()
        self.assertNotIn(mp, candidates)

    def test_restore_requires_finalized_mapping(self):
        from odoo.tests.common import tagged
        from odoo.addons.attachment_optimizer_pro.services.restore_service \
            import RestoreService
        att = self.env['ir.attachment'].create({
            'name': 'pending.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': 'cGVuZGluZw==',
        })
        mp = self.env['attachment.storage.mapping'].create({
            'attachment_id': att.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/ab/pending',
            's3_region': 'us-east-1',
            'status': 'uploaded',
        })
        service = RestoreService(self.env)
        with self.assertRaisesRegex(
            UserError, 'Wait until its storage mapping is finalized'
        ):
            service.restore_mapping(mp)
