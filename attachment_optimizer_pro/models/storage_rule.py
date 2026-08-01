from odoo import api, fields, models


class StorageRule(models.Model):
    _name = 'attachment.storage.rule'
    _description = 'Storage Routing Rule'
    _order = 'sequence, id'

    name = fields.Char(string='Rule Name', required=True)
    sequence = fields.Integer(string='Priority', default=10)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    res_model_id = fields.Many2one(
        'ir.model', string='Model',
        ondelete='set null',
        help='Restrict routing to attachments linked to this model.',
    )
    mime_type = fields.Char(
        string='MIME Type',
        help='Exact MIME type to match, e.g. application/pdf. '
             'Leave empty to match any.',
    )
    min_size_kb = fields.Integer(string='Min Size (KB)', default=0)
    max_size_kb = fields.Integer(
        string='Max Size (KB)', default=0,
        help='0 = unlimited.',
    )
    bucket_id = fields.Many2one(
        'attachment.storage.bucket', string='Target Bucket',
        required=True, ondelete='restrict',
    )
    notes = fields.Text(string='Notes')

    def _matches(self, attachment):
        self.ensure_one()
        if self.res_model_id and attachment.res_model != self.res_model_id.model:
            return False
        if self.mime_type and (
            (attachment.mimetype or '').lower()
            != self.mime_type.strip().lower()
        ):
            return False
        size_kb = (attachment.file_size or 0) / 1024.0
        if self.min_size_kb and size_kb < self.min_size_kb:
            return False
        if self.max_size_kb and size_kb > self.max_size_kb:
            return False
        return True

    @api.model
    def _resolve_rule(self, attachment):
        company = attachment.company_id or self.env.company
        rules = self.search([
            ('active', '=', True),
            ('company_id', '=', company.id),
        ], order='sequence, id')
        for rule in rules:
            if rule._matches(attachment):
                return rule
        return False

    @api.model
    def _route_attachments(self, attachments):
        from ..services.routing_service import RoutingService
        return RoutingService(self.env).route_attachments(attachments)

    @api.model
    def action_process_routed(self):
        from ..services.routing_service import RoutingService
        return RoutingService(self.env).process_routed_batch()
