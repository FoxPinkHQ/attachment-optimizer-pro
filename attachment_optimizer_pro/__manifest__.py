{
    "name": "Attachment Optimizer Pro",
    "version": "19.0.1.0.0",
    "category": "Storage",
    "summary": "Automation, cleanup, routing and lifecycle for S3-compatible attachment storage.",
    "description": """
        Extends Attachment Optimizer (free edition) with safe local cleanup,
        automatic storage routing, one-click restore, scheduled lifecycle
        policies, multi-bucket routing, background processing, storage cost
        analytics, and operational alerts for larger Odoo environments.
    """,
    "author": "FoxPink",
    "support": "aduy000@gmail.com",
    "website": "https://github.com/FoxPinkHQ/attachment-optimizer-pro",
    "license": "LGPL-3",
    "depends": [
        "attachment_optimizer",
        "web",
    ],
    "external_dependencies": {
        "python": ["boto3"],
    },
    "data": [],
    "assets": {},
    "installable": True,
    "application": False,
    "auto_install": False,
}
