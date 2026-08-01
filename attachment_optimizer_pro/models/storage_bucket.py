from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StorageBucket(models.Model):
    _name = 'attachment.storage.bucket'
    _description = 'Storage Bucket Profile'
    _order = 'sequence, name'

    name = fields.Char(string='Bucket Name', required=True)
    sequence = fields.Integer(string='Priority', default=10)
    provider = fields.Selection([
        ('aws', 'AWS S3'),
        ('minio', 'MinIO'),
        ('other', 'S3-compatible'),
    ], string='Provider', default='other', required=True)
    endpoint_url = fields.Char(
        string='Endpoint URL',
        help='Leave empty for Amazon S3. For MinIO or another compatible '
             'provider, enter its API endpoint.',
    )
    region = fields.Char(string='Region', default='us-east-1')
    access_key_id = fields.Char(string='Access Key')
    secret_access_key = fields.Char(string='Secret Key')
    sse = fields.Selection([
        ('none', 'None'),
        ('aes256', 'SSE-S3 (AES-256)'),
    ], string='Server-Side Encryption', default='none')
    is_default = fields.Boolean(
        string='Default Bucket',
        help='Fallback bucket used when no routing rule or policy matches. '
             'Only one default bucket is allowed.',
    )
    company_ids = fields.Many2many(
        'res.company', string='Companies',
        help='Companies this bucket serves. Leave empty to serve all companies.',
    )
    active = fields.Boolean(string='Active', default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A bucket profile with this name already exists.',
    )

    @api.constrains('is_default')
    def _check_single_default(self):
        for rec in self:
            if not rec.is_default:
                continue
            others = self.search([
                ('is_default', '=', True),
                ('id', '!=', rec.id),
            ])
            if others:
                raise ValidationError(_(
                    'Bucket "%s" is already the default bucket. Only one '
                    'default bucket is allowed.'
                ) % others[0].name)

    def _s3_config(self):
        self.ensure_one()
        return {
            'endpoint_url': self.endpoint_url or '',
            'region': self.region or 'us-east-1',
            'access_key_id': self.access_key_id or '',
            'secret_access_key': self.secret_access_key or '',
            'sse': self.sse or 'none',
        }

    @api.model
    def _resolve_default_bucket(self, company_id=False):
        domain = [('active', '=', True)]
        if company_id:
            domain.append([
                '|',
                ('company_ids', '=', False),
                ('company_ids', '=', company_id),
            ])
        else:
            domain.append(('company_ids', '=', False))
        bucket = self.search(domain + [('is_default', '=', True)], limit=1)
        if not bucket:
            bucket = self.search(domain, order='sequence, id', limit=1)
        return bucket

    def action_test_connection(self):
        self.ensure_one()
        from odoo.exceptions import UserError

        from ..services.s3_bridge import ProS3Bridge
        bridge = ProS3Bridge(self.env)
        result = bridge.test_connection(config=self._s3_config(), bucket=self.name)
        if result['status'] != 'ok':
            raise UserError(result.get('error') or _('Connection test failed.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Connection OK'),
                'message': _('Connected to bucket "%s".') % self.name,
                'type': 'success',
                'sticky': False,
            },
        }
