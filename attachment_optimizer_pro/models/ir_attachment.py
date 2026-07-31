import logging

from odoo import models

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def create(self, vals_list):
        recs = super().create(vals_list)
        ctx = self.env.context
        if ctx.get('attachment_storage_pro.disable_routing'):
            return recs
        ICP = self.env['ir.config_parameter'].sudo()
        if ICP.get_param('attachment_storage_pro.routing_enabled', 'False') \
                not in ('True', 'true', '1'):
            return recs
        binary = recs.filtered(lambda a: a.type == 'binary')
        if not binary:
            return recs
        try:
            self.env['attachment.storage.rule']._route_attachments(binary)
        except Exception:
            _logger.exception(
                'Routing rule evaluation failed for %d new attachment(s)',
                len(binary),
            )
        return recs
