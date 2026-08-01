from datetime import timedelta

from odoo import _, fields

from odoo.addons.attachment_optimizer.services.utils import human_size

from .cleanup_service import CleanupService
from .pro_config import ProConfig
from .s3_bridge import ProS3Bridge


class CleanupReadinessService:
    """Evaluate whether verified local copies can be cleaned safely."""

    def __init__(self, env):
        self.env = env

    def check(self, live=False):
        env = self.env
        cfg = ProConfig(env)
        cleanup = CleanupService(env)
        checks = []

        def add(code, label, status, detail):
            checks.append({
                'code': code,
                'label': label,
                'status': status,
                'detail': detail,
            })

        buckets = env['attachment.storage.bucket'].search([
            ('active', '=', True),
        ])
        add(
            'buckets', _('Active bucket profiles'),
            'pass' if buckets else 'fail',
            _('%d active bucket profile(s)') % len(buckets),
        )
        default_bucket = buckets.filtered('is_default')[:1]
        add(
            'default_bucket', _('Default routing bucket'),
            'pass' if default_bucket else 'fail',
            default_bucket.name if default_bucket else _(
                'Choose one active bucket as the default.'
            ),
        )

        Mapping = env['attachment.storage.mapping']
        finalized = Mapping.search([('status', '=', 'finalized')])
        missing_checksum = finalized.filtered(lambda mp: not mp.checksum_sha256)
        integrity_status = 'pass'
        integrity_detail = _('%d finalized mapping(s) have SHA-256') % len(finalized)
        if not finalized:
            integrity_status = 'warn'
            integrity_detail = _('No finalized mappings are available yet.')
        elif missing_checksum:
            integrity_status = 'fail'
            integrity_detail = _(
                '%d finalized mapping(s) are missing SHA-256.'
            ) % len(missing_checksum)
        add('integrity', _('Verified mapping integrity'),
            integrity_status, integrity_detail)

        Operation = env['attachment.migration.operation']
        failed = Operation.search_count([('state', '=', 'failed')])
        stale_before = fields.Datetime.now() - timedelta(minutes=30)
        stuck = Operation.search_count([
            ('state', '=', 'uploading'),
            ('heartbeat_at', '!=', False),
            ('heartbeat_at', '<', stale_before),
        ])
        add(
            'queue', _('Queue health'),
            'pass' if not failed and not stuck else 'fail',
            _('%(failed)d failed, %(stuck)d stuck operation(s)') % {
                'failed': failed, 'stuck': stuck,
            },
        )

        eligible = cleanup.eligible_mappings(
            retention_days=cfg.retention_days(),
        )
        eligible_bytes = cleanup.estimate_reclaimed(eligible)
        add(
            'eligible', _('Retention-eligible local copies'),
            'pass' if eligible else 'warn',
            _('%(count)d attachment(s), %(size)s reclaimable') % {
                'count': len(eligible), 'size': human_size(eligible_bytes),
            },
        )
        add(
            'cleanup_switch', _('Automatic cleanup switch'),
            'pass' if cfg.cleanup_enabled() else 'warn',
            _('Enabled') if cfg.cleanup_enabled() else _(
                'Disabled; manual cleanup remains available.'
            ),
        )

        if live and buckets:
            bridge = ProS3Bridge(env)
            failures = []
            for bucket in buckets:
                result = bridge.test_connection(
                    config=bucket._s3_config(), bucket=bucket.name,
                )
                if result.get('status') != 'ok':
                    failures.append(bucket.name)
            add(
                'live_connections', _('Live bucket connections'),
                'pass' if not failures else 'fail',
                _('All active buckets are reachable.') if not failures else _(
                    'Connection failed: %s'
                ) % ', '.join(failures),
            )

            samples = eligible[:3]
            missing_objects = samples.filtered(
                lambda mp: not bridge.head(mp.s3_bucket, mp.s3_key)
            )
            if not samples:
                sample_status = 'warn'
                sample_detail = _('No eligible object is available to sample.')
            elif missing_objects:
                sample_status = 'fail'
                sample_detail = _('%d sampled object(s) are missing.') % len(
                    missing_objects
                )
            else:
                sample_status = 'pass'
                sample_detail = _('%d sampled object(s) are reachable.') % len(
                    samples
                )
            add('sample_objects', _('Live object sample'),
                sample_status, sample_detail)

        blocking = [check for check in checks if check['status'] == 'fail']
        return {
            'ready': not blocking and bool(eligible),
            'live': live,
            'checked_at': fields.Datetime.now().isoformat(),
            'eligible_count': len(eligible),
            'eligible_bytes': eligible_bytes,
            'eligible_display': human_size(eligible_bytes),
            'checks': checks,
        }
