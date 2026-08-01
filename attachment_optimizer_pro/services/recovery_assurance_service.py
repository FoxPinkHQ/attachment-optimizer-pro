from datetime import timedelta

from odoo import fields

from .pro_config import ProConfig


class RecoveryAssuranceService:
    """Evaluate current restore evidence without mutating storage state."""

    LABELS = {
        'disabled': 'SCHEDULE OFF',
        'failed': 'ATTENTION',
        'overdue': 'DUE',
        'healthy': 'HEALTHY',
    }

    def __init__(self, env):
        self.env = env

    def assess(self, companies=None):
        companies = companies or self.env.companies
        config = ProConfig(self.env)
        interval_days = config.restore_drill_interval_days()
        now = fields.Datetime.now()
        latest_drills = []
        overdue_companies = 0
        for company in companies:
            drill = self.env['attachment.restore.drill'].search([
                ('company_id', '=', company.id),
                ('state', 'in', ('passed', 'failed')),
            ], order='run_at DESC, id DESC', limit=1)
            if drill:
                latest_drills.append(drill)
                if not drill.run_at or (
                    drill.run_at + timedelta(days=interval_days) <= now
                ):
                    overdue_companies += 1
            else:
                overdue_companies += 1
        failed_drills = sum(
            1 for drill in latest_drills if drill.state == 'failed'
        )
        last_run = max(
            (drill.run_at for drill in latest_drills if drill.run_at),
            default=False,
        )
        if not config.restore_drill_enabled():
            status = 'disabled'
        elif failed_drills:
            status = 'failed'
        elif overdue_companies:
            status = 'overdue'
        else:
            status = 'healthy'
        return {
            'enabled': config.restore_drill_enabled(),
            'status': status,
            'status_label': self.LABELS[status],
            'company_count': len(companies),
            'covered_companies': len(latest_drills),
            'coverage_display': '%d / %d companies' % (
                len(latest_drills), len(companies),
            ),
            'overdue_companies': overdue_companies,
            'failed_drills': failed_drills,
            'tested': sum(drill.tested for drill in latest_drills),
            'passed': sum(drill.passed for drill in latest_drills),
            'failed': sum(drill.failed for drill in latest_drills),
            'last_run': fields.Datetime.to_string(last_run) if last_run else False,
            'interval_days': interval_days,
        }