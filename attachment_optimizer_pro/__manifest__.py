{
    "name": "Attachment Optimizer Pro",
    "version": "16.0.1.0.5",
    "category": "Storage",
    "summary": "Automation, cleanup, routing and lifecycle for S3-compatible attachment storage.",
    "description": """
        Extends Attachment Optimizer (free edition) with safe local cleanup,
        automatic storage routing, one-click restore, scheduled lifecycle
        policies, multi-bucket routing, background processing, storage volume
        analytics, and operational alerts for larger Odoo environments.
    """,
    "author": "FoxPink",
    "support": "aduy000@gmail.com",
    "website": "https://github.com/FoxPinkHQ/attachment-optimizer-pro",
    "license": "OPL-1",
    "price": 49.0,
    "currency": "USD",
    "images": [
        "static/description/preview.png",
    ],
    "depends": [
        "attachment_optimizer",
        "mail",
    ],
    "external_dependencies": {
        "python": ["boto3"],
    },
    "data": [
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "views/storage_bucket_views.xml",
        "views/storage_rule_views.xml",
        "views/storage_policy_views.xml",
        "views/cleanup_batch_views.xml",
        "views/restore_batch_views.xml",
        "views/storage_mapping_views.xml",
        "views/pro_menu.xml",
        "views/res_config_settings_views.xml",
        "wizard/views/cleanup_confirm_views.xml",
        "wizard/views/restore_confirm_views.xml",
        "data/pro_params.xml",
        "data/pro_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "attachment_optimizer_pro/static/src/components/pro_dashboard/pro_dashboard.js",
            "attachment_optimizer_pro/static/src/components/pro_dashboard/pro_dashboard.xml",
            "attachment_optimizer_pro/static/src/components/pro_dashboard/pro_dashboard.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
