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
        from odoo.exceptions import UserError
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
        self.assertRaises(UserError, service.restore_mapping, mp)
