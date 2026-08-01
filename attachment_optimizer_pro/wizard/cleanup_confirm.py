from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CleanupConfirm(models.TransientModel):
    _name = 'attachment.cleanup.confirm'
    _description = 'Confirm Safe Local Copy Cleanup'

    selected_count = fields.Integer(string='Selected', readonly=True)
    count = fields.Integer(string='Safe to Clean', readonly=True)
    blocked_count = fields.Integer(string='Blocked', readonly=True)
    remote_verified_count = fields.Integer(
        string='Live S3 Verified', readonly=True,
    )
    estimated_bytes = fields.Integer(string='Estimated Reclaim', readonly=True)
    estimated_display = fields.Char(
        string='Estimated Reclaimed Space', readonly=True,
    )
    blocked_summary = fields.Text(string='Blocked Reasons', readonly=True)
    safety_previewed = fields.Boolean(string='Safety Preview Complete')
    previewed_at = fields.Datetime(string='Previewed At', readonly=True)
    retention_days = fields.Integer(string='Retention (days)', default=30)
    quarantine_days = fields.Integer(string='Quarantine (days)', default=7)
    candidate_ids = fields.Many2many(
        'attachment.storage.mapping',
        'attachment_cleanup_confirm_candidate_rel',
        string='Selected Mappings', readonly=True,
    )
    mapping_ids = fields.Many2many(
        'attachment.storage.mapping',
        'attachment_cleanup_confirm_eligible_rel',
        string='Safety-Verified Mappings', readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        from ..services.pro_config import ProConfig
        cfg = ProConfig(self.env)
        res['retention_days'] = cfg.retention_days()
        res['quarantine_days'] = cfg.quarantine_days()
        active_ids = self.env.context.get('active_ids') or []
        candidates = self.env['attachment.storage.mapping'].browse(active_ids)
        res['selected_count'] = len(candidates)
        res['candidate_ids'] = [(6, 0, candidates.ids)]
        return res

    @api.onchange('retention_days', 'quarantine_days')
    def _onchange_safety_inputs(self):
        self.safety_previewed = False
        self.previewed_at = False
        self.mapping_ids = [(5, 0, 0)]
        self.count = 0
        self.blocked_count = 0
        self.remote_verified_count = 0
        self.estimated_bytes = 0
        self.estimated_display = False
        self.blocked_summary = False

    def action_preview(self):
        self.ensure_one()
        from odoo.addons.attachment_optimizer.services.utils import human_size
        from ..services.cleanup_service import CleanupService
        report = CleanupService(self.env).preview_mappings(
            self.candidate_ids,
            retention_days=self.retention_days,
            live=True,
        )
        summary = '\n'.join(
            '%s: %d' % (reason, count)
            for reason, count in sorted(report['blocked'].items())
        ) or _('No blocked mappings.')
        self.write({
            'selected_count': report['selected'],
            'count': report['eligible_count'],
            'blocked_count': report['blocked_count'],
            'remote_verified_count': report['remote_verified'],
            'estimated_bytes': report['eligible_bytes'],
            'estimated_display': human_size(report['eligible_bytes']),
            'blocked_summary': summary,
            'mapping_ids': [(6, 0, report['eligible'].ids)],
            'safety_previewed': True,
            'previewed_at': fields.Datetime.now(),
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm(self):
        self.ensure_one()
        if not self.safety_previewed:
            raise UserError(_('Run Safety Preview before cleanup.'))
        if not self.mapping_ids:
            raise UserError(_(
                'No local copies passed the safety preview. Review the '
                'blocked reasons and resolve them before cleanup.'
            ))
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
                'type': 'warning' if batch.failed else 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }