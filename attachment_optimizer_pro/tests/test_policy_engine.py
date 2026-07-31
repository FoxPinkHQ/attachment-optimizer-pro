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
