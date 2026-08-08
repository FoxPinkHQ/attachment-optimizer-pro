from odoo.tests import TransactionCase


class TestProBranding(TransactionCase):

    def test_root_menu_uses_pro_icon(self):
        menu = self.env.ref(
            'attachment_optimizer.storage_optimization_menu'
        )
        self.assertEqual(
            menu.web_icon,
            'attachment_optimizer_pro,static/description/icon.png',
        )

    def test_settings_app_uses_pro_identity(self):
        view = self.env.ref(
            'attachment_optimizer_pro.'
            'attachment_optimizer_pro_res_config_settings'
        )
        arch = str(view.arch_db)
        self.assertIn('Attachment Optimizer Pro', arch)
        self.assertIn('<attribute name="data-key">attachment_optimizer_pro</attribute>', arch)
        action = self.env.ref(
            'attachment_optimizer.attachment_optimizer_settings_action'
        )
        self.assertIn('attachment_optimizer_pro', action.context)