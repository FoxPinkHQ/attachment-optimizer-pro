from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RestoreDrill(models.Model):
    _name = 'attachment.restore.drill'
    _description = 'Attachment Restore Drill'
    _order = 'create_date DESC, id DESC'

    name = fields.Char(
        required=True,
        default=lambda self: _('Restore Drill %s') %
        fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    source = fields.Selection([
        ('manual', 'Manual'), ('scheduled', 'Scheduled'),
    ], default='manual', required=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('running', 'Running'),
        ('passed', 'Passed'), ('failed', 'Failed'),
    ], default='draft', required=True, readonly=True)
    sample_size = fields.Integer(default=10, required=True)
    tested = fields.Integer(readonly=True)
    passed = fields.Integer(readonly=True)
    failed = fields.Integer(readonly=True)
    verified_bytes = fields.Integer(readonly=True)
    verified_display = fields.Char(
        compute='_compute_verified_display', string='Verified Data',
    )
    run_at = fields.Datetime(readonly=True)
    line_ids = fields.One2many(
        'attachment.restore.drill.line', 'drill_id', readonly=True,
    )

    def write(self, vals):
        protected = {
            'state', 'tested', 'passed', 'failed', 'verified_bytes',
            'run_at', 'line_ids',
        }
        if protected.intersection(vals) and not self.env.su:
            raise UserError(_('Restore drill evidence is read-only.'))
        return super().write(vals)

    @api.constrains('sample_size')
    def _check_sample_size(self):
        for record in self:
            if record.sample_size < 1 or record.sample_size > 100:
                raise UserError(_('Sample size must be between 1 and 100.'))

    @api.depends('verified_bytes')
    def _compute_verified_display(self):
        from odoo.addons.attachment_optimizer.services.utils import human_size
        for record in self:
            record.verified_display = human_size(record.verified_bytes)

    def action_run(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft restore drills can run.'))
        from ..services.restore_drill_service import RestoreDrillService
        passed = RestoreDrillService(self.env).run(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Restore Drill Passed' if passed else
                           'Restore Drill Needs Attention'),
                'message': _(
                    '%(tested)d tested, %(passed)d passed, %(failed)d failed.'
                ) % {
                    'tested': self.tested,
                    'passed': self.passed,
                    'failed': self.failed,
                },
                'type': 'success' if passed else 'warning',
                'sticky': bool(self.failed),
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    @api.model
    def action_run_scheduled(self):
        from ..services.pro_config import ProConfig
        from ..services.restore_drill_service import RestoreDrillService

        config = ProConfig(self.env)
        if not config.restore_drill_enabled():
            return 0
        now = fields.Datetime.now()
        last_run_value = config.restore_drill_last_run()
        if last_run_value:
            last_run = fields.Datetime.to_datetime(last_run_value)
            due_at = last_run + timedelta(
                days=config.restore_drill_interval_days(),
            )
            if now < due_at:
                return 0

        service = RestoreDrillService(self.env)
        sample_size = config.restore_drill_sample_size()
        created = 0
        for company in self.env['res.company'].search([]):
            if not service.candidates(company.id, 1):
                continue
            drill = self.sudo().create({
                'company_id': company.id,
                'sample_size': sample_size,
                'source': 'scheduled',
            })
            service.run(drill)
            created += 1
        self.env['ir.config_parameter'].sudo().set_param(
            config.RESTORE_DRILL_LAST_RUN,
            fields.Datetime.to_string(now),
        )
        return created


class RestoreDrillLine(models.Model):
    _name = 'attachment.restore.drill.line'
    _description = 'Attachment Restore Drill Result'
    _order = 'id'

    drill_id = fields.Many2one(
        'attachment.restore.drill', required=True, ondelete='cascade',
    )
    company_id = fields.Many2one(related='drill_id.company_id', store=True)
    mapping_id = fields.Many2one(
        'attachment.storage.mapping', required=True, ondelete='restrict',
    )
    attachment_id = fields.Many2one(
        related='mapping_id.attachment_id', string='Attachment', store=True,
    )
    result = fields.Selection(
        [('pass', 'Pass'), ('fail', 'Fail')], required=True,
    )
    expected_checksum = fields.Char(readonly=True)
    actual_checksum = fields.Char(readonly=True)
    verified_bytes = fields.Integer(readonly=True)
    error_message = fields.Text(readonly=True)