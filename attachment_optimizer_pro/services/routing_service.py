import logging

from odoo import fields, _

_logger = logging.getLogger(__name__)


class RoutingService:

    def __init__(self, env):
        self.env = env

    def route_attachments(self, attachments):
        """Create a routed draft operation for every matching attachment.

        Routed operations stay in 'draft' with a bucket profile until the
        routing engine claims them, so the free edition queue never picks
        them up with the default bucket."""
        Rule = self.env['attachment.storage.rule']
        Operation = self.env['attachment.migration.operation']
        Mapping = self.env['attachment.storage.mapping']
        routed = self.env['ir.attachment']
        for att in attachments:
            rule = Rule._resolve_rule(att)
            if not rule:
                continue
            existing_op = Operation.search_count([
                ('attachment_id', '=', att.id),
                ('state', 'not in', ('finalized', 'failed')),
            ])
            if existing_op:
                continue
            existing_map = Mapping.search_count([
                ('attachment_id', '=', att.id),
                ('status', 'not in', ('failed', 'verification_failed')),
            ])
            if existing_map:
                continue
            Operation.create({
                'attachment_id': att.id,
                'company_id': att.company_id.id or self.env.company.id,
                'state': 'draft',
                'bucket_id': rule.bucket_id.id,
                'routed': True,
            })
            self.env['attachment.audit.log']._log(
                'route', result='success',
                attachment_id=att.id,
                attachment_name=att.name,
                res_model=att.res_model,
            )
            routed += att
        return routed

    def process_routed_batch(self, limit=None):
        from .pro_config import ProConfig
        from .pro_migration_service import ProMigrationService
        Operation = self.env['attachment.migration.operation']
        if limit is None:
            limit = ProConfig(self.env).concurrency()
        ops = Operation._claim_routed_batch(limit=limit)
        service = ProMigrationService(self.env)
        results = {'success': 0, 'failed': 0}
        for op in ops:
            try:
                service.process_operation(op)
                results['success'] += 1
            except Exception as e:
                _logger.exception('Routed migration failed for op %s', op.id)
                op.transition_state(
                    'failed',
                    error_message=str(e),
                    completed_at=fields.Datetime.now(),
                )
                if op.mapping_id:
                    op.mapping_id.action_update_status('failed', error=str(e))
                self.env['attachment.audit.log']._log(
                    'upload', result='failure',
                    attachment_id=op.attachment_id.id,
                    attachment_name=op.attachment_id.name,
                    operation_id=op.id,
                    error_message=str(e),
                )
                results['failed'] += 1
        return results
