class ProConfig:
    """Reads Attachment Optimizer Pro configuration parameters."""

    ROUTING_ENABLED = 'attachment_storage_pro.routing_enabled'
    CLEANUP_ENABLED = 'attachment_storage_pro.cleanup.enabled'
    CLEANUP_RETENTION = 'attachment_storage_pro.cleanup.retention_days'
    CLEANUP_QUARANTINE = 'attachment_storage_pro.cleanup.quarantine_days'
    CONCURRENCY = 'attachment_storage_pro.concurrency'
    ALERT_ENABLED = 'attachment_storage_pro.alert.enabled'
    ALERT_EMAIL = 'attachment_storage_pro.alert.email'
    LOCAL_STORAGE_COST = (
        'attachment_storage_pro.cost.local_usd_per_gib_month'
    )

    def __init__(self, env):
        self.env = env

    def _get(self, key, default=''):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    def _bool(self, key, default=False):
        return self._get(key, 'True' if default else 'False') in (
            'True', 'true', '1',
        )

    def _int(self, key, default=0):
        try:
            return int(self._get(key, str(default)) or 0)
        except (TypeError, ValueError):
            return default

    def _float(self, key, default=0.0):
        try:
            return float(self._get(key, str(default)) or 0)
        except (TypeError, ValueError):
            return default
    def routing_enabled(self):
        return self._bool(self.ROUTING_ENABLED)

    def cleanup_enabled(self):
        return self._bool(self.CLEANUP_ENABLED)

    def retention_days(self):
        return self._int(self.CLEANUP_RETENTION, 30)

    def quarantine_days(self):
        return self._int(self.CLEANUP_QUARANTINE, 7)

    def concurrency(self):
        return max(1, self._int(self.CONCURRENCY, 10))

    def alert_enabled(self):
        return self._bool(self.ALERT_ENABLED)

    def alert_email(self):
        return self._get(self.ALERT_EMAIL, '').strip()

    def local_storage_cost_per_gib(self):
        return max(0.0, self._float(self.LOCAL_STORAGE_COST, 0.20))