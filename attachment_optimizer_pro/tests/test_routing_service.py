from unittest.mock import Mock, patch

from botocore.exceptions import ClientError
from psycopg2 import IntegrityError

from odoo.tests import TransactionCase


class TestRoutingService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Bucket = self.env['attachment.storage.bucket']
        self.Rule = self.env['attachment.storage.rule']
        self.bucket = self.Bucket.create({
            'name': 'test-bucket',
            'is_default': True,
        })
        self.rule = self.Rule.create({
            'name': 'pdf-to-test-bucket',
            'mime_type': 'application/pdf',
            'bucket_id': self.bucket.id,
        })

    def _make_attachment(self, name='doc.pdf', mimetype='application/pdf'):
        return self.env['ir.attachment'].create({
            'name': name,
            'type': 'binary',
            'mimetype': mimetype,
            'datas': 'aGVsbG8gd29ybGQ=',
        })

    def test_rule_matches_mime_type(self):
        att = self._make_attachment()
        self.assertTrue(self.rule._matches(att))

    def test_missing_object_head_does_not_retry(self):
        from odoo.addons.attachment_optimizer_pro.services.s3_bridge import (
            ProS3Bridge,
        )

        client = Mock()
        client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404', 'Message': 'Not Found'}},
            'HeadObject',
        )
        bridge = ProS3Bridge(self.env)
        target = (
            'odoo.addons.attachment_optimizer_pro.services.s3_bridge.'
            'ProS3Bridge._get_client'
        )
        with patch(target, return_value=client):
            self.assertFalse(bridge.head('bucket', 'missing-key', config={}))
        client.head_object.assert_called_once_with(
            Bucket='bucket', Key='missing-key',
        )
    def test_bucket_name_must_be_unique(self):
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self.Bucket.create({'name': self.bucket.name})

    def test_rule_does_not_match_wrong_mime(self):
        att = self._make_attachment(mimetype='image/png')
        self.assertFalse(self.rule._matches(att))

    def test_route_creates_draft_operation(self):
        from odoo.addons.attachment_optimizer_pro.services.routing_service \
            import RoutingService
        att = self._make_attachment()
        routed = RoutingService(self.env).route_attachments(att)
        self.assertEqual(len(routed), 1)
        op = self.env['attachment.migration.operation'].search([
            ('attachment_id', '=', att.id),
        ])
        self.assertTrue(op)
        self.assertEqual(op.state, 'draft')
        self.assertEqual(op.bucket_id, self.bucket)
        self.assertTrue(op.routed)

    def test_route_skips_already_mapped_attachment(self):
        from odoo.addons.attachment_optimizer_pro.services.routing_service \
            import RoutingService
        att = self._make_attachment()
        self.env['attachment.storage.mapping'].create({
            'attachment_id': att.id,
            's3_bucket': self.bucket.name,
            's3_key': 'objects/ab/key',
            's3_region': 'us-east-1',
            'status': 'finalized',
        })
        routed = RoutingService(self.env).route_attachments(att)
        self.assertEqual(len(routed), 0)

    def test_rule_resolution_uses_attachment_company(self):
        other_company = self.env['res.company'].create({
            'name': 'Routing Company B',
        })
        other_bucket = self.Bucket.sudo().create({
            'name': 'company-b-bucket',
            'company_ids': [(6, 0, [other_company.id])],
        })
        other_rule = self.Rule.sudo().create({
            'name': 'company-b-pdf',
            'company_id': other_company.id,
            'mime_type': 'application/pdf',
            'bucket_id': other_bucket.id,
        })
        att = self.env['ir.attachment'].sudo().create({
            'name': 'company-b.pdf',
            'type': 'binary',
            'mimetype': 'application/pdf',
            'datas': 'aGVsbG8gd29ybGQ=',
            'company_id': other_company.id,
        })
        resolved = self.Rule.sudo()._resolve_rule(att)
        self.assertEqual(resolved, other_rule)
        self.assertNotEqual(resolved, self.rule)
    def test_claim_routed_batch(self):
        att = self._make_attachment()
        self.env['attachment.migration.operation'].create({
            'attachment_id': att.id,
            'company_id': self.env.company.id,
            'state': 'draft',
            'bucket_id': self.bucket.id,
            'routed': True,
        })
        ops = self.env['attachment.migration.operation']._claim_routed_batch(
            limit=10,
        )
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops.state, 'uploading')
        self.assertTrue(ops.processing_token)
