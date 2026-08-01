from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CleanupBatch(models.Model):
    _name = 'attachment.cleanup.batch'
    _description = 'Storage Cleanup Batch'
    _order = 'create_date DESC, id DESC'

    name = fields.Char(
        string='Name', required=True,
        default=lambda self: _('Cleanup %s') % fields.Datetime.now().strftime(
            '%Y-%m-%d %H:%M:%S'
        ),
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', required=True)
    retention_days = fields.Integer(string='Retention (days)', default=30)
    quarantine_days = fields.Integer(string='Quarantine (days)', default=7)
    limit = fields.Integer(string='Batch Limit', default=200)
    total = fields.Integer(string='Total', readonly=True, default=0)
    cleaned = fields.Integer(string='Cleaned', readonly=True, default=0)
    skipped = fields.Integer(string='Skipped', readonly=True, default=0)
    failed = fields.Integer(string='Failed', readonly=True, default=0)
    reclaimed_bytes = fields.Integer(
        string='Reclaimed Bytes', readonly=True, default=0,
    )
    reclaimed_display = fields.Char(
        string='Reclaimed Space', compute='_compute_reclaimed_display',
        readonly=True,
    )
    started_at = fields.Datetime(string='Started At', readonly=True)
    finished_at = fields.Datetime(string='Finished At', readonly=True)
    mapping_ids = fields.Many2many(
        'attachment.storage.mapping', string='Processed Mappings',
        readonly=True,
    )
    failed_mapping_ids = fields.Many2many(
        'attachment.storage.mapping',
        'attachment_cleanup_batch_failed_mapping_rel',
        string='Failed Mappings', readonly=True,
    )
    issue_details = fields.Text(string='Issue Details', readonly=True)
    retry_of_id = fields.Many2one(
        'attachment.cleanup.batch', string='Retry Of', readonly=True,
        ondelete='set null',
    )

    @api.depends('reclaimed_bytes')
    def _compute_reclaimed_display(self):
        from odoo.addons.attachment_optimizer.services.utils import human_size
        for rec in self:
            rec.reclaimed_display = human_size(rec.reclaimed_bytes)

    def action_run(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Only draft cleanup batches can run. Create a new batch to '
                'clean additional local copies.'
            ))
        from ..services.cleanup_service import CleanupService
        CleanupService(self.env).run_batch(self)
        has_failures = bool(self.failed)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(
                    'Cleanup Completed with Errors'
                    if has_failures else 'Cleanup Complete'
                ),
                'message': _(
                    '%(cleaned)d cleaned, %(skipped)d skipped, %(failed)d '
                    'failed. Review the batch details before continuing.'
                ) % {
                    'cleaned': self.cleaned,
                    'skipped': self.skipped,
                    'failed': self.failed,
                },
                'type': 'warning' if has_failures else 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_retry_failed(self):
        self.ensure_one()
        if self.state != 'done' or not self.failed_mapping_ids:
            raise UserError(_('This cleanup batch has no failed mappings to retry.'))
        retry = self.create({
            'company_id': self.company_id.id,
            'retention_days': self.retention_days,
            'quarantine_days': self.quarantine_days,
            'limit': len(self.failed_mapping_ids),
            'retry_of_id': self.id,
        })
        from ..services.cleanup_service import CleanupService
        CleanupService(self.env).run_mappings(retry, self.failed_mapping_ids)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': retry.id,
            'view_mode': 'form',
            'target': 'current',
        }
    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    @api.model
    def action_run_auto_cleanup(self):
        from ..services.cleanup_service import CleanupService
        from ..services.pro_config import ProConfig
        cfg = ProConfig(self.env)
        if not cfg.cleanup_enabled():
            return False
        if cfg.restore_drill_enabled():
            from ..services.recovery_assurance_service import (
                RecoveryAssuranceService,
            )
            assurance = RecoveryAssuranceService(self.env).assess(
                self.env.company,
            )
            if assurance['status'] != 'healthy':
                reason = _(
                    'Automatic cleanup paused: recovery assurance is %(status)s.'
                ) % {'status': assurance['status_label']}
                self.env['attachment.audit.log']._log(
                    'cleanup', result='failure',
                    attachment_name=_('Automatic cleanup paused'),
                    error_message=reason,
                )
                return False
        batch = self.create({
            'retention_days': cfg.retention_days(),
            'quarantine_days': cfg.quarantine_days(),
            'state': 'draft',
        })
        service = CleanupService(self.env)
        service.run_batch(batch)
        service.finalize_quarantine(cfg.quarantine_days())
        return True
