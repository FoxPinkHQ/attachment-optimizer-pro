from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pro_routing_enabled = fields.Boolean(
        string='Enable Automatic Storage Routing',
        config_parameter='attachment_storage_pro.routing_enabled',
        default=False,
    )
    pro_cleanup_enabled = fields.Boolean(
        string='Enable Safe Local Cleanup',
        config_parameter='attachment_storage_pro.cleanup.enabled',
        default=False,
    )
    pro_cleanup_retention_days = fields.Integer(
        string='Cleanup Retention (days)',
        config_parameter='attachment_storage_pro.cleanup.retention_days',
        default=30,
    )
    pro_cleanup_quarantine_days = fields.Integer(
        string='Cleanup Quarantine (days)',
        config_parameter='attachment_storage_pro.cleanup.quarantine_days',
        default=7,
    )
    pro_concurrency = fields.Integer(
        string='Processing Concurrency',
        config_parameter='attachment_storage_pro.concurrency',
        default=10,
    )
    pro_alert_enabled = fields.Boolean(
        string='Enable Operational Alerts',
        config_parameter='attachment_storage_pro.alert.enabled',
        default=False,
    )
    pro_alert_email = fields.Char(
        string='Alert Recipient Email',
        config_parameter='attachment_storage_pro.alert.email',
    )
    pro_restore_drill_enabled = fields.Boolean(
        string='Enable Scheduled Restore Drills',
        config_parameter='attachment_storage_pro.restore_drill.enabled',
        default=False,
    )
    pro_restore_drill_sample_size = fields.Integer(
        string='Restore Drill Sample Size',
        config_parameter='attachment_storage_pro.restore_drill.sample_size',
        default=10,
    )
    pro_restore_drill_interval_days = fields.Integer(
        string='Restore Drill Interval (days)',
        config_parameter='attachment_storage_pro.restore_drill.interval_days',
        default=7,
    )

    pro_local_storage_cost_per_gib = fields.Float(
        string='Local Storage Cost (USD/GiB/month)',
        config_parameter='attachment_storage_pro.cost.local_usd_per_gib_month',
        default=0.20,
        digits=(16, 4),
    )

    @api.constrains('pro_local_storage_cost_per_gib')
    def _check_local_storage_cost(self):
        for record in self:
            if record.pro_local_storage_cost_per_gib < 0:
                raise ValidationError(_(
                    'Local storage cost cannot be negative.'
                ))

    @api.constrains(
        'pro_restore_drill_sample_size', 'pro_restore_drill_interval_days',
    )
    def _check_restore_drill_schedule(self):
        for record in self:
            if not 1 <= record.pro_restore_drill_sample_size <= 100:
                raise ValidationError(_(
                    'Restore drill sample size must be between 1 and 100.'
                ))
            if not 1 <= record.pro_restore_drill_interval_days <= 365:
                raise ValidationError(_(
                    'Restore drill interval must be between 1 and 365 days.'
                ))