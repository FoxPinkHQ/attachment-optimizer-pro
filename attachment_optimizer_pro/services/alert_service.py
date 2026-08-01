import logging

from odoo import _, fields

_logger = logging.getLogger(__name__)


class AlertService:
    """Operational alerts: notifies administrators about failed queues,
    stuck operations and storage health problems via email."""

    def __init__(self, env):
        self.env = env

    def _collect_issues(self):
        issues = []
        env = self.env

        failed = env['attachment.migration.operation'].search_count([
            ('state', '=', 'failed'),
        ])
        if failed:
            issues.append(_('%d failed migration operation(s)') % failed)

        env.cr.execute("""
            SELECT COUNT(*) FROM attachment_migration_operation
            WHERE state = 'uploading'
              AND heartbeat_at < %s::timestamp - INTERVAL '30 minutes'
        """, (fields.Datetime.now().isoformat(),))
        stuck = env.cr.fetchone()[0]
        if stuck:
            issues.append(_('%d operation(s) stuck in uploading') % stuck)

        env.cr.execute("""
            SELECT COUNT(*) FROM attachment_storage_mapping
            WHERE status = 'verification_failed'
        """)
        verify_failed = env.cr.fetchone()[0]
        if verify_failed:
            issues.append(_(
                '%d mapping(s) with failed checksum verification'
            ) % verify_failed)
        return issues

    def send_alert(self):
        from .pro_config import ProConfig
        cfg = ProConfig(self.env)
        if not cfg.alert_enabled():
            return False
        recipient = cfg.alert_email()
        if not recipient:
            return False
        issues = self._collect_issues()
        if not issues:
            return False

        email_from = (
            self.env.company.email
            or self.env.user.email
            or 'odoo@localhost'
        )
        body = '<ul>%s</ul>' % ''.join(
            '<li>%s</li>' % issue for issue in issues
        )
        self.env['mail.mail'].sudo().create({
            'subject': _('Attachment Optimizer Pro - Operational Alert'),
            'body_html': body,
            'email_from': email_from,
            'email_to': recipient,
            'auto_delete': True,
        })
        self.env['attachment.audit.log']._log(
            'alert', result='success',
            attachment_name=', '.join(issues)[:200],
        )
        return True
