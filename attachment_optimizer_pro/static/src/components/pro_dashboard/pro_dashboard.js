/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ProSafetyDashboard extends Component {
static template = "attachment_optimizer_pro.SafetyDashboard";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            checking: false,
            analytics: {
                total_display: "0 B",
                migrated_display: "0 B",
                migrated: 0,
                reclaimable_display: "0 B",
                reclaimable: 0,
                reclaimed_display: "0 B",
                reclaimed: 0,
                failed: 0,
                buckets: [],
            },
            readiness: { ready: false, checks: [], checked_at: false },
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "attachment.storage.mapping",
                "action_get_pro_dashboard_data",
                []
            );
            this.state.analytics = data.analytics;
            this.state.readiness = data.readiness;
        } catch (error) {
            this.notification.add(error.message || "Unable to load Pro dashboard.", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    async onRunReadiness() {
        this.state.checking = true;
        try {
            this.state.readiness = await this.orm.call(
                "attachment.storage.mapping",
                "action_run_cleanup_readiness",
                []
            );
            this.notification.add(
                this.state.readiness.ready
                    ? "Live cleanup readiness check passed."
                    : "Readiness check found items that need attention.",
                { type: this.state.readiness.ready ? "success" : "warning" }
            );
        } catch (error) {
            this.notification.add(error.message || "Live readiness check failed.", {
                type: "danger",
            });
        } finally {
            this.state.checking = false;
        }
    }

    onViewReclaimable() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Reclaimable Attachments",
            res_model: "attachment.storage.mapping",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["status", "=", "finalized"],
                ["cleanup_state", "=", "kept"],
                ["removed_at", "=", false],
            ],
        });
    }

    onViewReclaimed() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Reclaimed Attachments",
            res_model: "attachment.storage.mapping",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["cleanup_state", "in", ["quarantined", "cleaned"]]],
        });
    }

    onViewFailed() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Failed Operations",
            res_model: "attachment.migration.operation",
            view_mode: "tree,form",
            views: [[false, "list"], [false, "form"]],
            domain: [["state", "=", "failed"]],
        });
    }
}

registry.category("actions").add(
    "attachment_optimizer_pro.safety_dashboard",
    ProSafetyDashboard
);
