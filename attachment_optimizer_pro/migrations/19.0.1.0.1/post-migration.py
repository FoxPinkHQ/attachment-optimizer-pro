from odoo import SUPERUSER_ID, api


CRON_UPDATES = {
    'attachment_optimizer_pro.ir_cron_pro_routing': {
        'name': 'Attachment Optimizer Pro - Routing Engine',
    },
    'attachment_optimizer_pro.ir_cron_pro_cleanup': {
        'name': 'Attachment Optimizer Pro - Safe Cleanup',
    },
    'attachment_optimizer_pro.ir_cron_pro_policies': {
        'name': 'Attachment Optimizer Pro - Lifecycle Policies',
        'interval_number': 5,
        'interval_type': 'minutes',
    },
    'attachment_optimizer_pro.ir_cron_pro_alerts': {
        'name': 'Attachment Optimizer Pro - Operational Alerts',
    },
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, values in CRON_UPDATES.items():
        env.ref(xmlid).write(values)