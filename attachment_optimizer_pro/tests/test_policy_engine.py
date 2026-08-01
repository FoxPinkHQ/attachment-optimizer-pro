from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestPolicyEngine(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Bucket = self.env['attachment.storage.bucket']
        self.bucket = self.Bucket.create({
            'name': 'policy-bucket',
            'is_default': True,
        })
        self.att = self.env['ir.attachment'].create({
            'name': 'policy-target.txt',
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': 'cG9saWN5IHRhcmdldA==',
        })

    def test_schedule_due_respects_enabled_and_interval(self):
        policy = self.env['attachment.storage.policy'].create({
            'name': 'Daily Scheduled Policy',
            'action': 'migrate',
            'bucket_id': self.bucket.id,
            'schedule_enabled': True,
            'interval_number': 1,
            'interval_type': 'days',
        })
        now = fields.Datetime.now()
        self.assertTrue(policy._is_due(now=now))
        policy.last_run = now - timedelta(hours=23)
        self.assertFalse(policy._is_due(now=now))
        policy.last_run = now - timedelta(days=1, minutes=1)
        self.assertTrue(policy._is_due(now=now))
        policy.schedule_enabled = False
        self.assertFalse(policy._is_due(now=now))

    def test_schedule_interval_must_be_positive(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.env['attachment.storage.policy'].create({
                'name': 'Invalid Schedule',
                'action': 'migrate',
                'interval_number': 0,
            })

    def test_cron_runs_only_due_scheduled_policies(self):
        due = self.env['attachment.storage.policy'].create({
            'name': 'Due Policy',
            'action': 'migrate',
            'bucket_id': self.bucket.id,
            'schedule_enabled': True,
        })
        self.env['attachment.storage.policy'].create({
            'name': 'Manual Only Policy',
            'action': 'migrate',
            'bucket_id': self.bucket.id,
            'schedule_enabled': False,
        })
        target = (
            'odoo.addons.attachment_optimizer_pro.services.policy_engine.'
            'PolicyEngine.run_policy'
        )
        from odoo.addons.attachment_optimizer_pro.services.policy_engine \
            import PolicyEngine
        with patch(target, return_value={'summary': 'ok'}) as run_policy:
            PolicyEngine(self.env).run_all()
        run_policy.assert_called_once_with(due)
    def test_migrate_policy_queues_attachment(self):
        policy = self.env['attachment.storage.policy'].create({
            'name': 'Migrate Text Files',
            'action': 'migrate',
            'mime_type': 'text/plain',
            'bucket_id': self.bucket.id,
        })
        from odoo.addons.attachment_optimizer_pro.services.policy_engine \
            import PolicyEngine
        PolicyEngine(self.env).run_policy(policy)
        op = self.env['attachment.migration.operation'].search([
            ('attachment_id', '=', self.att.id),
        ])
        self.assertTrue(op)
        self.assertEqual(op.bucket_id, self.bucket)
        self.assertTrue(op.routed)
        self.assertTrue(policy.last_run)

    def test_migrate_policy_skips_mapped_attachment(self):
        policy = self.env['attachment.storage.policy'].create({
            'name': 'Migrate All',
            'action': 'migrate',
        })
        self.env['attachment.storage.mapping'].create({
            'attachment_id': self.att.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/ab/key',
            's3_region': 'us-east-1',
            'status': 'finalized',
        })
        from odoo.addons.attachment_optimizer_pro.services.policy_engine \
            import PolicyEngine
        PolicyEngine(self.env).run_policy(policy)
        self.assertFalse(self.env['attachment.migration.operation'].search([
            ('attachment_id', '=', self.att.id),
        ]))

    def test_archive_policy_runs_migrate(self):
        policy = self.env['attachment.storage.policy'].create({
            'name': 'Archive',
            'action': 'archive',
            'bucket_id': self.bucket.id,
        })
        from odoo.addons.attachment_optimizer_pro.services.policy_engine \
            import PolicyEngine
        PolicyEngine(self.env).run_policy(policy)
        op = self.env['attachment.migration.operation'].search([
            ('attachment_id', '=', self.att.id),
        ])
        self.assertTrue(op)
        self.assertTrue(op.routed)
        self.assertEqual(op.bucket_id, self.bucket)
