from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RestoreBatch(models.Model):
    _name = 'attachment.restore.batch'
    _description = 'Storage Restore Batch'
    _order = 'create_date DESC, id DESC'

    name = fields.Char(
        string='Name', required=True,
        default=lambda self: _('Restore %s') % fields.Datetime.now().strftime(
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
    limit = fields.Integer(string='Batch Limit', default=200)
    total = fields.Integer(string='Total', readonly=True, default=0)
    restored = fields.Integer(string='Restored', readonly=True, default=0)
    failed = fields.Integer(string='Failed', readonly=True, default=0)
    restored_bytes = fields.Integer(
        string='Restored Bytes', readonly=True, default=0,
    )
    restored_display = fields.Char(
        string='Restored Space', compute='_compute_restored_display',
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
        'attachment_restore_batch_failed_mapping_rel',
        string='Failed Mappings', readonly=True,
    )
    issue_details = fields.Text(string='Failure Details', readonly=True)
    retry_of_id = fields.Many2one(
        'attachment.restore.batch', string='Retry Of', readonly=True,
        ondelete='set null',
    )

    @api.depends('restored_bytes')
    def _compute_restored_display(self):
        from odoo.addons.attachment_optimizer.services.utils import human_size
        for rec in self:
            rec.restored_display = human_size(rec.restored_bytes)

    def action_run(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                'Only draft restore batches can run. Create a new batch to '
                'restore additional attachments.'
            ))
        from ..services.restore_service import RestoreService
        RestoreService(self.env).run_batch(self)
        has_failures = bool(self.failed)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _(
                    'Restore Completed with Errors'
                    if has_failures else 'Restore Complete'
                ),
                'message': _(
                    '%(restored)d restored, %(failed)d failed. Review the '
                    'batch details and retry failed attachments.'
                ) % {
                    'restored': self.restored,
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
            raise UserError(_('This restore batch has no failed mappings to retry.'))
        retry = self.create({
            'company_id': self.company_id.id,
            'limit': len(self.failed_mapping_ids),
            'mapping_ids': [(6, 0, self.failed_mapping_ids.ids)],
            'retry_of_id': self.id,
        })
        from ..services.restore_service import RestoreService
        RestoreService(self.env).run_batch(retry)
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
