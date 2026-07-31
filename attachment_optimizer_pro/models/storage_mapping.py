from odoo import _, api, fields, models


class StorageMapping(models.Model):
    _inherit = 'attachment.storage.mapping'

    bucket_id = fields.Many2one(
        'attachment.storage.bucket', string='Bucket Profile',
        ondelete='set null',
    )
    cleanup_state = fields.Selection([
        ('kept', 'Local Copy Kept'),
        ('quarantined', 'Quarantined'),
        ('cleaned', 'Local Copy Removed'),
    ], string='Cleanup State', default='kept', index=True)
    removed_at = fields.Datetime(
        string='Local Copy Removed At', readonly=True,
    )
    quarantined_at = fields.Datetime(string='Quarantined At', readonly=True)
    restored = fields.Boolean(string='Restored to Filestore', default=False)
    restored_at = fields.Datetime(string='Restored At', readonly=True)

    def action_restore_mapping(self):
        self.ensure_one()
        from ..services.restore_service import RestoreService
        RestoreService(self.env).restore_mapping(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Restore Complete'),
                'message': _('Attachment "%s" restored to the filestore.') % (
                    self.attachment_id.name
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def action_show_analytics(self):
        from ..services.analytics_service import AnalyticsService
        report = AnalyticsService(self.env).get_report()
        message = _(
            'Total %(total_d)s (%(total)s files) | Migrated %(migrated_d)s '
            '(%(pct)s%%) | Reclaimed %(reclaimed_d)s | Failed %(failed)s'
        ) % {
            'total_d': report['total_display'],
            'total': report['total_attachments'],
            'migrated_d': report['migrated_display'],
            'pct': report['migration_pct'],
            'reclaimed_d': report['reclaimed_display'],
            'failed': report['failed'],
        }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Storage Analytics'),
                'message': message,
                'type': 'info',
                'sticky': True,
            },
        }
