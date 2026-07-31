# Attachment Optimizer Pro

> **Automate, route, and reclaim S3-compatible attachment storage at scale.**
>
> Extends the free [Attachment Optimizer](https://github.com/FoxPinkHQ/attachment-optimizer) module with automation, lifecycle policies, safe local cleanup, and multi-bucket routing.

**Version:** 19.0.1.0.0 -- **License:** LGPL-3 -- **Publisher:** FoxPink -- Maintained for **Odoo 19.0** (one validated build per series)

---

## Why use Attachment Optimizer Pro?

Attachment Optimizer Pro builds on the verified replication and SHA-256 guarantees of the free edition and adds the automation and storage-reclamation tools needed by larger Odoo environments. Every Pro capability preserves the same safety-first core: nothing is deleted before checksum verification, every action is audited, and rollback is always possible.

| Problem | Solution |
|--------|----------|
| Filestore growing without bound | Safe local cleanup with retention and quarantine |
| New attachments still stored locally | Automatic storage routing by model, MIME, size, company, and rules |
| Need to roll back or uninstall | One-click restore from S3 to the Odoo filestore |
| Manual migration everywhere | Scheduled lifecycle policies for migrate, archive, retain, restore, clean |
| One bucket fits nobody | Multi-bucket and multi-company routing |
| Uploads tie up the UI | Background processing with configurable concurrency and throttling |

- **Reclaim filestore space safely** — cleanup only after successful checksum verification
- **Route new attachments automatically** — configurable, model-aware rules
- **Operate unattended** — scheduled batches, policies, alerts, and reports

---

## Features

### Safe Local Cleanup
- **Verified deletion** — filestore space is reclaimed only after the S3 object checksum matches
- **Configurable retention** — keep local copies for N days before cleanup
- **Quarantine period** — deleted files stay recoverable for a grace window

### Automatic Storage Routing
- **Rule-based routing** — route new attachments to S3 by model, MIME type, file size, company, and custom rules
- **Transparent reads** — finalized attachments served from S3 with filestore fallback (inherited from free edition)

### Restore
- **One-click restore** — restore selected files or complete batches from S3 to the Odoo filestore
- **Rollback ready** — restore before rollback or uninstall, no data loss

### Lifecycle Policies
- **Scheduled policies** — migrate, archive, retain, restore, and clean up attachments on a schedule
- **Policy engine** — evaluate attachments against company, model, age, and size rules

### Storage Topology
- **Multi-bucket routing** — isolate storage by company, environment, workload, or data policy
- **Multi-company isolation** — record rules keep company data separate

### Background Processing
- **Scheduled batches** — migration and maintenance jobs run via cron
- **Configurable concurrency and throttling** — control load on S3 and Odoo
- **Resumable workers** — interrupted work continues where it stopped

### Analytics and Operations
- **Storage cost analytics** — compare local and object-storage volume, forecast growth, report reclaimed space
- **Operational alerts** — notify administrators about failed queues, storage health, policy violations, and recovery actions

### Advanced Security
- **IAM role support** — replace static keys where supported
- **Server-side encryption** — SSE options on upload
- **Key rotation guidance and policy validation**

---

## Safety First

```
✓ Nothing deleted before checksum verification
✓ Original filestore preserved until cleanup is explicitly scheduled
✓ Quarantine window keeps deleted files recoverable
✓ Immutable audit trail — every action logged with user, timestamp, result
✓ Retry and recovery are idempotent — no duplicates, no data loss
```

---

## Installation

**Prerequisites:** the free [Attachment Optimizer](https://github.com/FoxPinkHQ/attachment-optimizer) module must be installed first. Attachment Optimizer Pro is an extension of it.

**Option 1 — ZIP:** Download the ZIP for your Odoo version from the [Releases](https://github.com/FoxPinkHQ/attachment-optimizer-pro/releases) page, unzip into your addons directory, restart Odoo, and install via Apps.

**Option 2 — Git:**

```bash
git clone -b 19.0 https://github.com/FoxPinkHQ/attachment-optimizer-pro addons/attachment_optimizer_pro
```

Before installing the module, install the required Python dependency in the same environment that runs Odoo:

```bash
pip3 install boto3
```

> **Deployment note:** This module requires Python code and the external `boto3` package. It is intended for Odoo.sh and on-premise/Docker deployments where server dependencies can be installed; it is not compatible with Odoo Online.

---

## Getting Started

1. **Install the free edition** — configure S3 and run a verified migration (see [Attachment Optimizer](https://github.com/FoxPinkHQ/attachment-optimizer))
2. **Install Attachment Optimizer Pro** — the Pro menu appears under **Storage Optimization**
3. **Configure routing rules** — Settings → Attachment Optimizer Pro
4. **Schedule lifecycle policies** — create a policy and let cron process it
5. **Enable safe cleanup** — set retention and quarantine, then run a cleanup batch
6. **Monitor analytics and alerts** — review reclaimed space, volume trends, and notifications

---

## Security

- **Role-based access** — Storage Optimization Manager group controls Pro features
- **Multi-company isolation** — record rules enforce data isolation
- **Immutable audit log** — every action logged with user, timestamp, result
- **No credential is stored in audit logs**

---

## Compatibility

| Odoo Version | Status |
|---|---|
| 19.0 | ✅ This branch |

Additional Odoo series (14.0-18.0) will receive validated branches and releases as they ship.

---

## Dependencies

- `attachment_optimizer` (free edition)
- `web`
- **Python:** `boto3`

---

## Support

- **Issues:** [GitHub Issues](https://github.com/FoxPinkHQ/attachment-optimizer-pro/issues)

---

## License

**LGPL-3** — see [LICENSE](LICENSE).
