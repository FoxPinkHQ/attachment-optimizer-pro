import base64
import hashlib
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestRestoreDrill(TransactionCase):

    def setUp(self):
        super().setUp()
        self.data = b'restore drill evidence'
        self.checksum = hashlib.sha256(self.data).hexdigest()
        self.bucket = self.env['attachment.storage.bucket'].create({
            'name': 'restore-drill-bucket',
            'is_default': True,
        })
        self.attachment = self.env['ir.attachment'].create({
            'name': 'restore-drill.txt',
            'type': 'binary',
            'datas': base64.b64encode(self.data).decode(),
        })
        self.mapping = self.env['attachment.storage.mapping'].create({
            'attachment_id': self.attachment.id,
            'company_id': self.env.company.id,
            's3_bucket': self.bucket.name,
            's3_key': 'restore/drill',
            's3_region': 'us-east-1',
            'status': 'finalized',
            'checksum_sha256': self.checksum,
            'bucket_id': self.bucket.id,
            'cleanup_state': 'cleaned',
        })

    def test_restore_drill_passes_without_mutating_mapping(self):
        drill = self.env['attachment.restore.drill'].create({
            'sample_size': 1,
        })
        target = (
            'odoo.addons.attachment_optimizer_pro.services.'
            'restore_drill_service.ProS3Bridge.get_object'
        )
        with patch(target, return_value=self.data):
            action = drill.action_run()
        self.assertEqual(drill.state, 'passed')
        self.assertEqual(drill.tested, 1)
        self.assertEqual(drill.passed, 1)
        self.assertEqual(drill.failed, 0)
        self.assertEqual(drill.verified_bytes, len(self.data))
        self.assertEqual(drill.line_ids.result, 'pass')
        self.assertEqual(self.mapping.cleanup_state, 'cleaned')
        self.assertEqual(action['params']['type'], 'success')

    def test_restore_drill_records_checksum_failure(self):
        drill = self.env['attachment.restore.drill'].create({
            'sample_size': 1,
        })
        target = (
            'odoo.addons.attachment_optimizer_pro.services.'
            'restore_drill_service.ProS3Bridge.get_object'
        )
        with patch(target, return_value=b'corrupt remote object'):
            drill.action_run()
        self.assertEqual(drill.state, 'failed')
        self.assertEqual(drill.failed, 1)
        self.assertEqual(drill.line_ids.result, 'fail')
        self.assertIn('checksum does not match',
                      drill.line_ids.error_message)
        self.assertEqual(self.mapping.cleanup_state, 'cleaned')

    def test_restore_drill_evidence_is_read_only(self):
        drill = self.env['attachment.restore.drill'].create({
            'sample_size': 1,
        })
        manager = self.env.ref('base.user_admin')
        with self.assertRaisesRegex(UserError, 'evidence is read-only'):
            drill.with_user(manager).write({'passed': 99})

    def test_restore_drill_sample_size_is_bounded(self):
        with self.assertRaises(UserError):
            self.env['attachment.restore.drill'].create({'sample_size': 101})