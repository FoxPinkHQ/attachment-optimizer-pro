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

    @api.depends('restored_bytes')
    def _compute_restored_display(self):
        from odoo.addons.attachment_optimizer.services.utils import human_size
        for rec in self:
            rec.restored_display = human_size(rec.restored_bytes)

    def action_run(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('This restore batch has already been processed.'))
        from ..services.restore_service import RestoreService
        RestoreService(self.env).run_batch(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Restore Complete'),
                'message': _(
                    '%(restored)d restored, %(failed)d failed'
                ) % {
                    'restored': self.restored,
                    'failed': self.failed,
                },
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'
