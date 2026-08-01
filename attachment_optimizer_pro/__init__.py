from odoo import SUPERUSER_ID, api

from . import models
from . import services
from . import wizard


def _hook_env(env_or_cr, registry=None):
    if registry is None:
        return env_or_cr
    return api.Environment(env_or_cr, SUPERUSER_ID, {})


def _uninstall_hook(env_or_cr, registry=None):
    """Restore Free edition branding after Pro is removed."""
    env = _hook_env(env_or_cr, registry)
    menu = env.ref(
        'attachment_optimizer.storage_optimization_menu',
        raise_if_not_found=False,
    )
    if menu:
        menu.write({
            'web_icon': 'attachment_optimizer,static/description/icon.png',
        })
    action = env.ref(
        'attachment_optimizer.attachment_optimizer_settings_action',
        raise_if_not_found=False,
    )
    if action and 'attachment_optimizer_pro' in (action.context or ''):
        action.write({'context': "{'module': 'attachment_optimizer'}"})