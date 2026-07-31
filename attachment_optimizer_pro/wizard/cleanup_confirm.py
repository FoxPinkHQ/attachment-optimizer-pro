from odoo import _, api, fields, models


class CleanupConfirm(models.TransientModel):
    _name = 'attachment.cleanup.confirm'
    _description = 'Confirm Safe Local Copy Cleanup'

    count = fields.Integer(string='Eligible Mappings', readonly=True)
    estimated_bytes = fields.Integer(string='Estimated Reclaim', readonly=True)
    estimated_display = fields.Char(
        string='Estimated Reclaimed Space', readonly=True,
    )
    retention_days = fields.Integer(string='Retention (days)', default=30)
    quarantine_days = fields.Integer(string='Quarantine (days)', default=7)
    mapping_ids = fields.Many2many(
        'attachment.storage.mapping', string='Eligible Mappings',
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        from odoo.addons.attachment_optimizer.services.utils import human_size

        from ..services.cleanup_service import CleanupService
        from ..services.pro_config import ProConfig
        cfg = ProConfig(self.env)
        retention = cfg.retention_days()
        res['retention_days'] = retention
        res['quarantine_days'] = cfg.quarantine_days()

        active_ids = self.env.context.get('active_ids')
        mappings = self.env['attachment.storage.mapping'].browse(
            active_ids
        ) if active_ids else None
        service = CleanupService(self.env)
        eligible = service.eligible_mappings(
            mappings=mappings, retention_days=retention,
        )
        estimated = service.estimate_reclaimed(eligible)
        res['count'] = len(eligible)
        res['estimated_bytes'] = estimated
        res['estimated_display'] = human_size(estimated)
        res['mapping_ids'] = [(6, 0, eligible.ids)]
        return res

    def action_confirm(self):
        self.ensure_one()
        from ..services.cleanup_service import CleanupService
        batch = self.env['attachment.cleanup.batch'].create({
            'retention_days': self.retention_days,
            'quarantine_days': self.quarantine_days,
            'state': 'draft',
        })
        CleanupService(self.env).run_mappings(batch, self.mapping_ids)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Cleanup Complete'),
                'message': _(
                    '%(cleaned)d cleaned, %(skipped)d skipped, %(failed)d failed'
                ) % {
                    'cleaned': batch.cleaned,
                    'skipped': batch.skipped,
                    'failed': batch.failed,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
