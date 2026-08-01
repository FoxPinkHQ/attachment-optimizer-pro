import base64
import hashlib
from unittest.mock import patch

from odoo import fields
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

    def test_scheduled_restore_drill_is_company_scoped(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('attachment_storage_pro.restore_drill.enabled', True)
        params.set_param('attachment_storage_pro.restore_drill.sample_size', 1)
        params.set_param('attachment_storage_pro.restore_drill.interval_days', 7)
        target = (
            'odoo.addons.attachment_optimizer_pro.services.'
            'restore_drill_service.ProS3Bridge.get_object'
        )
        before = self.env['attachment.restore.drill'].search_count([])
        with patch(target, return_value=self.data):
            created = self.env['attachment.restore.drill'].action_run_scheduled()
        scheduled = self.env['attachment.restore.drill'].search([
            ('source', '=', 'scheduled'),
        ], order='id DESC', limit=1)
        self.assertEqual(created, 1)
        self.assertEqual(
            self.env['attachment.restore.drill'].search_count([]), before + 1,
        )
        self.assertEqual(scheduled.company_id, self.env.company)
        self.assertEqual(scheduled.state, 'passed')

    def test_scheduled_restore_drill_respects_interval(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('attachment_storage_pro.restore_drill.enabled', True)
        params.set_param(
            'attachment_storage_pro.restore_drill.last_run_at',
            fields.Datetime.to_string(fields.Datetime.now()),
        )
        self.assertEqual(
            self.env['attachment.restore.drill'].action_run_scheduled(), 0,
        )

    def test_recent_restore_drill_failure_is_an_operational_issue(self):
        drill = self.env['attachment.restore.drill'].create({'sample_size': 1})
        drill.sudo().write({
            'state': 'failed',
            'run_at': fields.Datetime.now(),
            'tested': 1,
            'failed': 1,
        })
        from odoo.addons.attachment_optimizer_pro.services.alert_service import (
            AlertService,
        )
        issues = AlertService(self.env)._collect_issues()
        self.assertTrue(any('restore drill' in issue for issue in issues))