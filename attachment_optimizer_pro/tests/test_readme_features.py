import base64
import hashlib

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase

from odoo.addons.attachment_optimizer.models.migration_operation import (
    UPLOAD_BATCH_LIMIT,
)
from odoo.addons.attachment_optimizer.services.migration_service import (
    MigrationService,
)
from odoo.addons.attachment_optimizer.services.s3_bridge import S3Bridge


class TestReadmeFeatures(TransactionCase):
    """Proves every feature documented in the free edition README keeps
    working when Attachment Optimizer Pro is installed."""

    def setUp(self):
        super().setUp()
        self.test_bucket = 'readme-test-bucket'
        self.test_data = b'readme feature coverage payload'
        self.checksum = hashlib.sha256(self.test_data).hexdigest()
        self.s3_key = 'objects/%s/%s' % (self.checksum[:2], self.checksum)
        self._setup_s3_params()
        self._start_moto()

    def tearDown(self):
        if getattr(self, '_mock_aws', None):
            self._mock_aws.stop()
            self._mock_aws = None
        super().tearDown()

    def _setup_s3_params(self, bucket=None):
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage.s3.endpoint_url', '')
        ICP.set_param('attachment_storage.s3.region', 'us-east-1')
        ICP.set_param('attachment_storage.s3.access_key_id', 'testing')
        ICP.set_param('attachment_storage.s3.secret_access_key', 'testing')
        ICP.set_param(
            'attachment_storage.s3.bucket', bucket or self.test_bucket,
        )

    def _start_moto(self):
        try:
            import boto3
            from moto import mock_aws
        except ImportError:
            self.skipTest('moto or boto3 not available')
        mock = mock_aws()
        mock.start()
        self._mock_aws = mock
        self._client = boto3.client('s3', region_name='us-east-1')
        self._client.create_bucket(Bucket=self.test_bucket)

    def _create_attachment(self, name='readme.txt', data=None, **kwargs):
        return self.env['ir.attachment'].create({
            'name': name,
            'type': 'binary',
            'mimetype': 'text/plain',
            'datas': base64.b64encode(data or self.test_data).decode(),
            **kwargs,
        })

    def test_01_analyze_storage(self):
        """Analyze attachment storage usage across all models."""
        att = self._create_attachment()
        candidates = MigrationService(self.env).analyze_candidates()
        self.assertIn(att, candidates)
        self.env['attachment.migration.operation'].action_analyze_storage()
        ICP = self.env['ir.config_parameter'].sudo()
        self.assertTrue(
            ICP.get_param('attachment_storage.last_analysis'),
            'Analyze must record last_analysis timestamp',
        )

    def test_02_queue_migration(self):
        """Queue attachments for migration."""
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        self.assertTrue(ops)
        self.assertEqual(ops[0].state, 'queued')

    def test_03_upload_verify_finalize(self):
        """Upload, verify (SHA-256) and finalize per attachment."""
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        results = MigrationService(self.env).process_queue(
            batch_size=10, operation_ids=ops.ids,
        )
        self.assertEqual(results['success'], 1)
        self.assertEqual(results['failed'], 0)
        ops.invalidate_cache()
        self.assertEqual(ops[0].state, 'finalized')
        mapping = self.env['attachment.storage.mapping'].lookup_by_attachment(
            att.id,
        )
        self.assertTrue(mapping)
        self.assertEqual(mapping.status, 'finalized')
        self.assertEqual(mapping.s3_key, self.s3_key)
        self.assertEqual(mapping.checksum_sha256, self.checksum)
        self.assertTrue(mapping.verification_timestamp)

    def test_04_transparent_s3_serving_and_fallback(self):
        """Finalized attachments are served from S3 with filestore fallback."""
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        MigrationService(self.env).process_queue(
            batch_size=10, operation_ids=ops.ids,
        )

        binary = self.env['ir.binary']
        stream = binary._get_stream_from(att, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(stream.data, self.test_data)
        self.assertEqual(stream.mimetype, 'text/plain')

        # Object deleted from S3 â†’ fall back to the retained filestore copy.
        S3Bridge(self.env).delete(self.test_bucket, self.s3_key)
        stream = binary._get_stream_from(att, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(stream.data, self.test_data)

    def test_05_audit_trail_immutable(self):
        """Full audit trail with immutable logs."""
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        MigrationService(self.env).process_queue(
            batch_size=10, operation_ids=ops.ids,
        )

        logs = self.env['attachment.audit.log'].search([
            ('attachment_id', '=', att.id),
        ], order='create_date ASC')
        actions = logs.mapped('action')
        for expected in ('queue', 'upload', 'verify_finalize'):
            self.assertIn(expected, actions)
        for log in logs:
            self.assertEqual(log.result, 'success')
        log = logs[0]
        with self.assertRaises(AccessError):
            log.write({'result': 'failure'})
        with self.assertRaises(AccessError):
            log.unlink()

    def test_06_dashboard_kpis(self):
        """Dashboard KPI overview: total, migrated, saved bytes, failed."""
        before_kpi = (
            self.env['attachment.storage.mapping']
            .action_get_dashboard_data()
        )
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        MigrationService(self.env).process_queue(
            batch_size=10, operation_ids=ops.ids,
        )

        kpi = self.env['attachment.storage.mapping'].action_get_dashboard_data()
        for key in (
            'total_attachments', 'migrated', 'saved_bytes',
            'saved_display', 'failed',
        ):
            self.assertIn(key, kpi)
        self.assertGreaterEqual(kpi['migrated'], 1)
        self.assertEqual(kpi['failed'], before_kpi['failed'])
        self.assertGreaterEqual(kpi['saved_bytes'], len(self.test_data))

    def test_07_batch_upload_limit(self):
        """Batch upload with configurable limit (100 per request)."""
        self.assertEqual(UPLOAD_BATCH_LIMIT, 100)
        for i in range(3):
            self._create_attachment(name='batch-%d.txt' % i)
        attachments = self.env['ir.attachment'].search([
            ('name', 'like', 'batch-'),
        ])
        MigrationService(self.env).create_migration_operations(
            attachments.ids,
        )
        ops = self.env['attachment.migration.operation'].search([
            ('state', '=', 'queued'),
            ('attachment_id', 'in', attachments.ids),
        ])
        result = ops.action_upload()
        self.assertIn('3 success', result['params']['message'])
        finalized = self.env['attachment.migration.operation'].search_count([
            ('state', '=', 'finalized'),
            ('attachment_id', 'in', attachments.ids),
        ])
        self.assertEqual(finalized, 3)

        # claim_batch honours a configurable limit.
        for i in range(2):
            self._create_attachment(name='claim-%d.txt' % i)
        claims = self.env['ir.attachment'].search([
            ('name', 'like', 'claim-'),
        ])
        MigrationService(self.env).create_migration_operations(claims.ids)
        claimed = self.env['attachment.migration.operation'].claim_batch(
            limit=1,
        )
        self.assertEqual(len(claimed), 1)

    def test_08_retry_failed_operations(self):
        """Retry failed operations individually and in bulk."""
        Operation = self.env['attachment.migration.operation']
        att = self._create_attachment()
        op = Operation.create_queue([att.id])
        op.transition_state('failed', error_message='simulated failure')
        retry_result = op.action_retry()
        new_op = Operation.search([
            ('retry_of', '=', op.id),
        ])
        self.assertTrue(new_op)
        self.assertEqual(new_op.state, 'queued')
        self.assertEqual(new_op.attempt, 2)
        self.assertIn('res_id', retry_result)

        att2 = self._create_attachment(name='bulk.txt')
        op2 = Operation.create_queue([att2.id])
        op2.transition_state('failed', error_message='simulated failure')
        bulk = Operation.action_retry_all_failed()
        self.assertIn('re-queued', bulk['params']['message'])

    def test_09_multi_company_isolation(self):
        """Multi-company isolation via record rules."""
        company_b = self.env['res.company'].create({'name': 'Company B'})
        att_b = self._create_attachment(name='company-b.txt')
        att_b.company_id = company_b.id
        op_b = self.env['attachment.migration.operation'].create({
            'attachment_id': att_b.id,
            'company_id': company_b.id,
            'state': 'queued',
        })

        manager_grp = self.env.ref(
            'attachment_optimizer.group_storage_optimization_manager',
        )
        user_a = self.env['res.users'].create({
            'name': 'Manager A',
            'login': 'manager_a_%s' % att_b.id,
            'notification_type': 'email',
            'company_id': self.env.company.id,
            'company_ids': [(6, 0, [self.env.company.id])],
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
                manager_grp.id,
            ])],
        })
        visible = self.env['attachment.migration.operation'].with_user(
            user_a,
        ).search([('id', '=', op_b.id)])
        self.assertFalse(
            visible,
            'Company A manager must not see company B operations',
        )

    def test_10_role_based_access(self):
        """Role-based access: manager group is required."""
        manager_grp = self.env.ref(
            'attachment_optimizer.group_storage_optimization_manager',
        )
        self.assertTrue(manager_grp)
        plain_user = self.env['res.users'].create({
            'name': 'Plain User',
            'login': 'plain_user_%s' % self.env.user.id,
            'notification_type': 'email',
            'groups_id': [(6, 0, [
                self.env.ref('base.group_user').id,
            ])],
        })
        with self.assertRaises(AccessError):
            self.env['attachment.migration.operation'].with_user(
                plain_user,
            ).search_count([])

    def test_11_config_system_params(self):
        """S3 connection is configured and verified via system parameters."""
        result = S3Bridge(self.env).test_connection()
        self.assertEqual(result['status'], 'ok', result.get('error'))
        fingerprint = S3Bridge(self.env).get_config_fingerprint()
        self.assertTrue(fingerprint)

    def test_12_filestore_retained(self):
        """Migration does not delete the original filestore data."""
        att = self._create_attachment()
        ops = MigrationService(self.env).create_migration_operations([att.id])
        MigrationService(self.env).process_queue(
            batch_size=10, operation_ids=ops.ids,
        )
        att.invalidate_cache()
        self.assertTrue(att.store_fname)
        self.assertTrue(att.datas)

    def test_13_routed_pipeline_serves_from_bucket(self):
        """Pro multi-bucket routing finalizes and serves from its own config."""
        from odoo.addons.attachment_optimizer_pro.services.routing_service \
            import RoutingService

        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('attachment_storage_pro.routing_enabled', 'True')

        self._client.create_bucket(Bucket='routed-bucket')
        bucket = self.env['attachment.storage.bucket'].create({
            'name': 'routed-bucket',
            'provider': 'minio',
            'endpoint_url': '',
            'region': 'us-east-1',
            'access_key_id': 'testing',
            'secret_access_key': 'testing',
        })
        rule = self.env['attachment.storage.rule'].create({
            'name': 'Route text files',
            'mime_type': 'text/plain',
            'bucket_id': bucket.id,
        })

        att = self._create_attachment(name='routed.txt')
        op = self.env['attachment.migration.operation'].search([
            ('attachment_id', '=', att.id),
        ])
        self.assertTrue(op, 'Routing on create must build a draft operation')
        self.assertEqual(op.state, 'draft')
        self.assertTrue(op.routed)
        self.assertEqual(op.bucket_id, bucket)

        results = RoutingService(self.env).process_routed_batch()
        self.assertEqual(results['success'], 1)
        op.invalidate_cache()
        self.assertEqual(op.state, 'finalized')
        mapping = self.env['attachment.storage.mapping'].lookup_by_attachment(
            att.id,
        )
        self.assertEqual(mapping.status, 'finalized')
        self.assertEqual(mapping.bucket_id, bucket)

        stream = self.env['ir.binary']._get_stream_from(att, 'datas')
        self.assertIsNotNone(stream)
        self.assertEqual(stream.data, self.test_data)
