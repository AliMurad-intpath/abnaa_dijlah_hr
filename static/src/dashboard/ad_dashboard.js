/** @odoo-module **/
import { Component, onMounted, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const circle = (cx, cy, r) =>
    `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${r * 2} 0a${r} ${r} 0 1 0 ${-r * 2} 0`;
const AXES = "M3 3v18h18";
// Lucide-style line icons (ISC licence, see ICON_LICENSE.txt)
const ICONS = {
    kpi: [circle(12, 12, 10), circle(12, 12, 6), circle(12, 12, 2)],
    bar: [AXES, "M7 16h8", "M7 11h12", "M7 6h3"],
    column: [AXES, "M18 17V9", "M13 17V5", "M8 17v-3"],
    area: [AXES, "M7 16l4-5 3 3 5-6v8z"],
    pie: ["M21.21 15.89A10 10 0 1 1 8 2.83", "M22 12A10 10 0 0 0 12 2v10z"],
    doughnut: [circle(12, 12, 10), circle(12, 12, 4)],
    table: ["M3 5h18v14H3z", "M3 10h18", "M9 5v14"],
    sun: [circle(12, 12, 4), "M12 2v2", "M12 20v2", "m4.93 4.93 1.41 1.41", "m17.66 17.66 1.41 1.41", "M2 12h2", "M20 12h2", "m6.34 17.66-1.41 1.41", "m19.07 4.93-1.41 1.41"],
    moon: ["M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"],
    users: ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", circle(9, 7, 4), "M22 21v-2a4 4 0 0 0-3-3.87", "M16 3.13a4 4 0 0 1 0 7.75"],
    "user-plus": ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", circle(9, 7, 4), "M19 8v6", "M22 11h-6"],
    "check-user": ["M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2", circle(9, 7, 4), "m16 11 2 2 4-4"],
    calendar: ["M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", "M3 10h18", "M8 2v4", "M16 2v4"],
    clock: [circle(12, 12, 10), "M12 6v6l4 2"],
    wallet: ["M20 7H5a2 2 0 0 1 0-4h12v4", "M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1", "M16 14h2"],
    file: ["M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z", "M14 2v6h6", "M8 13h8", "M8 17h8"],
    alert: ["M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z", "M12 9v4", "M12 17h.01"],
    plus: ["M5 12h14", "M12 5v14"],
    refresh: ["M3 12a9 9 0 0 1 15-6.7L21 8", "M21 3v5h-5", "M21 12a9 9 0 0 1-15 6.7L3 16", "M3 21v-5h5"],
    comments: ["M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"],
    login: ["M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4", "M10 17l5-5-5-5", "M15 12H3"],
    logout: ["M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4", "M16 17l5-5-5-5", "M21 12H9"],
    swap: ["M17 3l4 4-4 4", "M3 7h18", "M7 21l-4-4 4-4", "M21 17H3"],
    gavel: ["m14 13-8.5 8.5a2.12 2.12 0 0 1-3-3L11 10", "m16 16 6-6", "m8 8 6-6", "m9 7 8 8", "m21 11-8-8"],
    check: ["M20 6 9 17l-5-5"],
    shield: ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"],
    pen: ["M12 20h9", "M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"],
    monitor: ["M2 4h20v12H2z", "M8 20h8", "M12 16v4"],
};
const PALETTE = ["#6366f1", "#0ea5e9", "#14b8a6", "#f97316", "#d946ef", "#8b5cf6", "#3b82f6", "#ef4444", "#64748b"];

export class AdDashboard extends Component {
    static template = "abnaa_dijlah_hr.AdDashboard";

    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        let dark = false;
        try {
            const saved = localStorage.getItem("ad_dashboard.theme");
            dark = saved ? saved === "dark" : !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
        } catch {}
        let auto = false;
        try { auto = localStorage.getItem("ad_dashboard.auto") === "1"; } catch {}
        this.state = proxy({ loading: true, error: false, errorMessage: "", data: null, dark, office: false, auto, edit: false });
        this.timer = null;
        onMounted(async () => {
            await this.load();
            this.schedule();
        });
        onWillUnmount(() => this.stopTimer());
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call("ad.dashboard", "get_data", [], { edit: this.state.edit });
        } catch (e) {
            console.error("[abnaa_dijlah_hr] dashboard failed to load", e);
            this.state.error = true;
            this.state.errorMessage = (e && (e.data && e.data.message || e.message)) || String(e);
        } finally {
            this.state.loading = false;
        }
    }

    // ---- presentation helpers ----
    icon(name) { return ICONS[name] || ICONS.kpi; }
    get greetIcon() { const h = new Date().getHours(); return h >= 18 || h < 5 ? "moon" : "sun"; }
    get greeting() {
        const h = new Date().getHours();
        return (h >= 5 && h < 12 ? "صباح الخير" : h >= 12 && h < 18 ? "مساء الخير" : "مساء الخير") + "، " + this.state.data.user_name;
    }
    get dateLabel() {
        try { return new Date().toLocaleDateString("ar", { weekday: "long", year: "numeric", month: "long", day: "numeric" }); }
        catch { return this.state.data.today; }
    }
    get trendMax() { return Math.max(1, ...this.state.data.trend.map((t) => t.count)); }
    get siteMax() { return Math.max(1, ...this.state.data.sites.map((s) => s.count)); }
    colHeight(c) { return Math.round((c / this.trendMax) * 100); }
    barWidth(c) { return Math.round((c / this.siteMax) * 100); }
    get createGroups() {
        const c = this.state.data.create;
        return [
            { title: "الموارد البشرية", items: c.filter((x) => x.group === "hr") },
            { title: "استمارات AD", items: c.filter((x) => x.group === "forms") },
        ].filter((g) => g.items.length);
    }
    /** Doughnut slices: forms created in the last 6 months, by type. */
    get doughnut() {
        const rows = this.state.data.tiles.filter((t) => t.created_6m > 0);
        const total = rows.reduce((a, t) => a + t.created_6m, 0);
        let offset = 0;
        const slices = rows.map((t, i) => {
            const pct = (t.created_6m / total) * 100;
            const s = { title: t.title, count: t.created_6m, color: PALETTE[i % PALETTE.length],
                        dash: `${pct} ${100 - pct}`, offset: -offset, model: t.model, tile: t };
            offset += pct;
            return s;
        });
        return { total, slices };
    }
    stamp(s) { return (s || "").slice(0, 10); }

    // ---- auto refresh (every 5 minutes) ----
    stopTimer() {
        if (this.timer) { clearInterval(this.timer); this.timer = null; }
    }
    schedule() {
        this.stopTimer();
        if (this.state.auto) {
            this.timer = setInterval(() => { if (!document.hidden) { this.load().catch(() => {}); } }, 5 * 60 * 1000);
        }
    }
    setAuto(on) {
        this.state.auto = !!on;
        try { localStorage.setItem("ad_dashboard.auto", on ? "1" : "0"); } catch {}
        this.schedule();
    }

    // ---- actions ----
    toggleTheme() {
        this.state.dark = !this.state.dark;
        try { localStorage.setItem("ad_dashboard.theme", this.state.dark ? "dark" : "light"); } catch {}
    }
    toggleEdit() {
        this.state.edit = !this.state.edit;
        return this.load();
    }
    editAccess(ev, key) {
        ev.stopPropagation();
        const id = this.state.data.ids[key];
        if (!id) { return; }
        this.action.doAction({
            type: "ir.actions.act_window", name: "صلاحيات العنصر", res_model: "ad.dashboard.block",
            res_id: id, views: [[false, "form"]], target: "new",
        }, { onClose: () => this.load() });
    }
    toggleOffice() { this.state.office = !this.state.office; }
    reload() { return this.load(); }
    openList(model, domain, name) {
        this.action.doAction({
            type: "ir.actions.act_window", name: name || "", res_model: model,
            views: [[false, "list"], [false, "form"]], domain: domain || [],
        });
    }
    openTile(tile) { this.openList(tile.model, tile.open ? [["state", "not in", tile.closed]] : [], tile.title); }
    openAll(tile) { this.openList(tile.model, [], tile.title); }
    openKpi(k) { if (k.model) { this.openList(k.model, k.domain, k.label); } }
    openAlert(a) { this.openList(a.model, a.domain, a.text); }
    openRecord(r) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: r.model, res_id: r.id,
                               views: [[false, "form"]], target: "current" });
    }
    openSite(site) { this.openList("hr.employee", [["ad_work_site_id", "=", site.id]], site.name); }
    createNew(item) {
        this.action.doAction({
            type: "ir.actions.act_window", name: item.label, res_model: item.model,
            views: [[item.view_id || false, "form"]], target: item.target || "current",
            context: { form_view_initial_mode: "edit" },
        }, { onClose: () => this.load() });
    }
}

registry.category("actions").add("ad_hr_dashboard", AdDashboard);
console.info("[abnaa_dijlah_hr] dashboard action registered");
