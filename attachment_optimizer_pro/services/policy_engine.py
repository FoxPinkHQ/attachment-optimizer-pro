import logging

from odoo import fields, _

from .cleanup_service import CleanupService
from .restore_service import RestoreService

_logger = logging.getLogger(__name__)


class PolicyEngine:
    """Runs lifecycle policies: migrate, restore, cleanup and archive."""

    def __init__(self, env):
        self.env = env

    def run_policy(self, policy):
        report = {
            'migrate': 0,
            'restore': 0,
            'cleanup': 0,
            'skipped': 0,
            'failed': 0,
        }
        if policy.action in ('migrate', 'archive'):
            report['migrate'] = self._migrate(policy)
        if policy.action == 'restore':
            report['restore'] = self._restore(policy)
        if policy.action in ('cleanup', 'archive'):
            report['cleanup'] = self._cleanup(policy)
        report['summary'] = ', '.join(
            '%s=%d' % (key, val)
            for key, val in report.items() if key != 'summary'
        )
        policy.write({'last_run': fields.Datetime.now()})
        return report

    def _migrate(self, policy):
        Attachment = self.env['ir.attachment'].sudo()
        domain = [
            ('type', '=', 'binary'),
            ('store_fname', '!=', False),
            ('res_model', '!=', 'ir.ui.view'),
        ]
        if policy.company_id:
            domain.extend([
                '|',
                ('company_id', '=', False),
                ('company_id', '=', policy.company_id.id),
            ])
        attachments = Attachment.search(
            domain, limit=policy.batch_limit, order='create_date',
        )
        Operation = self.env['attachment.migration.operation']
        Mapping = self.env['attachment.storage.mapping']
        count = 0
        for att in attachments:
            if not policy._matches(att):
                continue
            if Operation.search_count([
                ('attachment_id', '=', att.id),
                ('state', 'not in', ('finalized', 'failed')),
            ]):
                continue
            if Mapping.search_count([
                ('attachment_id', '=', att.id),
                ('status', 'not in', ('failed', 'verification_failed')),
            ]):
                continue
            if policy.bucket_id:
                Operation.create({
                    'attachment_id': att.id,
                    'company_id': att.company_id.id or self.env.company.id,
                    'state': 'draft',
                    'bucket_id': policy.bucket_id.id,
                    'routed': True,
                })
            else:
                Operation.create_queue([att.id])
            self.env['attachment.audit.log']._log(
                'policy', result='success',
                attachment_id=att.id,
                attachment_name=att.name,
                res_model=att.res_model,
            )
            count += 1
        return count

    def _restore(self, policy):
        service = RestoreService(self.env)
        candidates = service.find_restore_candidates(
            company_id=policy.company_id.id if policy.company_id else False,
            limit=policy.batch_limit,
        )
        count = 0
        for mp in candidates:
            if not policy._matches(mp.attachment_id.sudo()):
                continue
            try:
                service.restore_mapping(mp)
                count += 1
            except Exception:
                _logger.exception('Policy restore failed for mapping %s', mp.id)
        return count

    def _cleanup(self, policy):
        service = CleanupService(self.env)
        candidates = service.eligible_mappings(
            retention_days=policy.retention_days,
            company_id=policy.company_id.id if policy.company_id else False,
            limit=policy.batch_limit,
        )
        count = 0
        for mp in candidates:
            try:
                result = service.cleanup_mapping(mp)
                if result['changed']:
                    count += 1
            except Exception:
                _logger.exception('Policy cleanup failed for mapping %s', mp.id)
        return count

    def run_all(self):
        policies = self.env['attachment.storage.policy'].search([
            ('active', '=', True),
        ])
        for policy in policies:
            try:
                report = self.run_policy(policy)
                policy.write({'last_result': report['summary']})
            except Exception as e:
                _logger.exception('Policy %s failed', policy.name)
                policy.write({'last_result': _('failed: %s') % e})
        return True
