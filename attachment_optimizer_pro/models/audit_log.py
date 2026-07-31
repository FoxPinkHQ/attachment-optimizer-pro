from odoo import fields, models


class AuditLog(models.Model):
    _inherit = 'attachment.audit.log'

    action = fields.Selection(
        selection_add=[
            ('route', 'Routing'),
            ('cleanup', 'Cleanup'),
            ('quarantine', 'Quarantine'),
            ('restore', 'Restore'),
            ('policy', 'Policy'),
            ('alert', 'Alert'),
        ],
        ondelete={
            'route': 'cascade',
            'cleanup': 'cascade',
            'quarantine': 'cascade',
            'restore': 'cascade',
            'policy': 'cascade',
            'alert': 'cascade',
        },
    )

    def action_send_alert(self):
        from ..services.alert_service import AlertService
        return AlertService(self.env).send_alert()
