from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StoragePolicy(models.Model):
    _name = 'attachment.storage.policy'
    _description = 'Storage Lifecycle Policy'
    _order = 'name'

    name = fields.Char(string='Policy Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    action = fields.Selection([
        ('migrate', 'Migrate to S3'),
        ('restore', 'Restore to Filestore'),
        ('cleanup', 'Clean Local Copy'),
        ('archive', 'Archive (Migrate + Cleanup)'),
    ], string='Action', required=True, default='migrate')
    res_model_id = fields.Many2one(
        'ir.model', string='Model',
        ondelete='set null',
        help='Restrict the policy to attachments linked to this model.',
    )
    mime_type = fields.Char(
        string='MIME Type',
        help='Exact MIME type to match, e.g. application/pdf. '
             'Leave empty to match any.',
    )
    min_size_kb = fields.Integer(string='Min Size (KB)', default=0)
    max_size_kb = fields.Integer(string='Max Size (KB)', default=0)
    age_days = fields.Integer(
        string='Minimum Age (days)', default=0,
        help='Only process attachments older than this many days.',
    )
    bucket_id = fields.Many2one(
        'attachment.storage.bucket', string='Target Bucket',
        ondelete='set null',
        help='Bucket used for the migrate/archive action. Leave empty to use '
             'the default bucket.',
    )
    retention_days = fields.Integer(string='Retention (days)', default=30)
    quarantine_days = fields.Integer(string='Quarantine (days)', default=7)
    batch_limit = fields.Integer(string='Batch Limit', default=100)
    schedule_enabled = fields.Boolean(
        string='Scheduled Execution', default=False,
        help='Process this policy automatically on a schedule.',
    )
    interval_number = fields.Integer(string='Repeat Every', default=1)
    interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
    ], string='Interval Unit', default='days')
    last_run = fields.Datetime(string='Last Run', readonly=True)
    last_result = fields.Char(string='Last Result', readonly=True)

    @api.constrains('interval_number')
    def _check_interval_number(self):
        for policy in self:
            if policy.interval_number < 1:
                raise ValidationError(_(
                    'Repeat Every must be at least 1. Enter a positive '
                    'schedule interval.'
                ))

    def _is_due(self, now=None):
        self.ensure_one()
        if not self.schedule_enabled:
            return False
        if not self.last_run:
            return True
        now = now or fields.Datetime.now()
        interval = max(1, self.interval_number)
        due_at = self.last_run + relativedelta(**{
            self.interval_type or 'days': interval,
        })
        return due_at <= now
    def _matches(self, attachment):
        self.ensure_one()
        if self.res_model_id and attachment.res_model != self.res_model_id.model:
            return False
        if self.mime_type and (
            (attachment.mimetype or '').lower()
            != self.mime_type.strip().lower()
        ):
            return False
        size_kb = (attachment.file_size or 0) / 1024.0
        if self.min_size_kb and size_kb < self.min_size_kb:
            return False
        if self.max_size_kb and size_kb > self.max_size_kb:
            return False
        if self.age_days:
            ref = attachment.create_date or attachment.write_date
            if ref:
                age = (fields.Datetime.now() - ref).days
                if age < self.age_days:
                    return False
        return True

    @api.model
    def action_run_policies(self):
        from ..services.policy_engine import PolicyEngine
        return PolicyEngine(self.env).run_all()

    def action_run(self):
        self.ensure_one()
        from ..services.policy_engine import PolicyEngine
        report = PolicyEngine(self.env).run_policy(self)
        processed = report['migrate'] + report['restore'] + report['cleanup']
        notification_type = (
            'warning' if report['failed'] else
            'success' if processed else 'info'
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(
                    'Policy Completed with Errors'
                    if report['failed'] else 'Policy Complete'
                ),
                'message': report['summary'],
                'type': notification_type,
                'sticky': False,
            },
        }
