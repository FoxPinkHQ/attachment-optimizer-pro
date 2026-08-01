from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RestoreConfirm(models.TransientModel):
    _name = 'attachment.restore.confirm'
    _description = 'Confirm Restore from S3'

    count = fields.Integer(string='Mappings to Restore', readonly=True)
    mapping_ids = fields.Many2many(
        'attachment.storage.mapping', string='Mappings', readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        from ..services.restore_service import RestoreService
        active_ids = self.env.context.get('active_ids')
        mappings = self.env['attachment.storage.mapping'].browse(
            active_ids
        ) if active_ids else None
        candidates = RestoreService(self.env).find_restore_candidates()
        if mappings:
            candidates = candidates.filtered(
                lambda m: m.id in mappings.ids
            )
        res['count'] = len(candidates)
        res['mapping_ids'] = [(6, 0, candidates.ids)]
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.mapping_ids:
            raise UserError(_(
                'No attachments are ready to restore. Select finalized '
                'mappings whose local copies are quarantined or removed.'
            ))
        from ..services.restore_service import RestoreService
        batch = self.env['attachment.restore.batch'].create({
            'state': 'draft',
        })
        batch.write({'mapping_ids': [(6, 0, self.mapping_ids.ids)]})
        RestoreService(self.env).run_batch(batch)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Restore Complete'),
                'message': _(
                    '%(restored)d restored, %(failed)d failed'
                ) % {
                    'restored': batch.restored,
                    'failed': batch.failed,
                },
                'type': 'warning' if batch.failed else 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
