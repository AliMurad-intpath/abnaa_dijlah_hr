/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useSetupAction } from "@web/search/action_hook";

const MIN_SIZE = 6;
const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const FIELD_PROPS = ["page", "x", "y", "width", "height", "font_size", "min_font_size", "text_align", "bold", "multiline", "sample_value", "font_family", "date_format"];
const FONT_STACKS = {
    naskh: '"AdDocNaskh", Arial, Helvetica, sans-serif',
    dejavu: '"AdDocDejaVu", sans-serif',
};
const RULE_PROPS = ["signature_page", "signature_x", "signature_y", "signature_width", "signature_height", "print_signature"];

function round(value) {
    return Math.round(value * 2) / 2;
}

export class AdPdfDesigner extends Component {
    static template = "abnaa_dijlah_hr.AdPdfDesigner";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.history = [];
        this.nextLocalId = -1;
        const action = this.props.action || {};
        this.typeId = (action.params && action.params.type_id) || (action.context && action.context.active_id);
        this.handles = HANDLES;
        this.state = proxy({
            loaded: false, name: "", locked: false, structureLocked: false, pages: [[595, 842]], fields: [], rules: [],
            issues: [], frames: [], page: 1, zoom: 1.25, selected: null, exact: false, stamp: Date.now(),
            dirty: {}, saving: false, selection: [], undoCount: 0, drawMode: null, drawing: null, creator: null,
            sources: [], fieldTypes: [], systemSources: [], approvers: [], groups: [],
        });
        useSetupAction({
            beforeLeave: () => this.confirmLeave(),
            beforeUnload: (ev) => {
                if (this.hasUnsaved) { ev.preventDefault(); ev.returnValue = ""; }
            },
        });
        this.drag = null;
        this.onMove = (ev) => this.dragMove(ev);
        this.onUp = () => this.dragEnd();
        this.onKey = (ev) => this.keyNudge(ev);
        window.addEventListener("keydown", this.onKey);
        onWillUnmount(() => {
            window.removeEventListener("keydown", this.onKey);
            this.stopListening();
        });
        onWillStart(async () => {
            if (!this.typeId) {
                return;
            }
            this.applyData(await this.orm.call("ad.form.template", "designer_load", [[this.typeId]]));
            const initial = this.items.find(i => i.kind === action.params?.selected_kind && i.id === action.params?.selected_id);
            if (initial) this.select(initial);
        });
    }
    applyData(data) {
        Object.assign(this.state, {
            loaded: true, name: data.name, locked: data.locked, structureLocked: Boolean(data.structure_locked), pages: data.pages.length ? data.pages : [[595, 842]],
            frames: data.frames || [],
            fields: data.fields, rules: data.rules, issues: data.issues,
            dirty: {}, stamp: Date.now(), creator: null, drawing: null, drawMode: null,
            sources: data.sources || [], fieldTypes: data.field_types || [], groups: data.groups || [],
            systemSources: data.system_sources || [], approvers: data.approvers || [],
        });
        this.history = []; this.state.undoCount = 0;
        this.state.page = Math.min(this.state.page, this.state.pages.length);
        if (this.state.selected && !this.selectedItem) {
            this.state.selected = null;
        }
    }

    get items() {
        const fields = this.state.fields.map((f) => ({
            kind: "field", id: f.id, ref: f, label: f.name, page: f.page, x: f.x, y: f.y, width: f.width, height: f.height,
        }));
        const rules = this.state.rules.map((r) => ({
            kind: "rule", id: r.id, ref: r, label: r.name, page: r.signature_page, x: r.signature_x,
            y: r.signature_y, width: r.signature_width, height: r.signature_height,
        }));
        return [...fields, ...rules];
    }

    get pageItems() {
        return this.items
            .filter((item) => item.page === this.state.page)
            .sort((a, b) => b.width * b.height - a.width * a.height);
    }

    get selectedItem() {
        const sel = this.state.selected;
        return sel && this.items.find((item) => item.kind === sel.kind && item.id === sel.id);
    }

    get pageSize() {
        const [width, height] = this.state.pages[this.state.page - 1] || [595, 842];
        return { width, height };
    }

    get dirtyCount() {
        return Object.keys(this.state.dirty).length;
    }

    get imageUrl() {
        const base = `/abnaa_dijlah_hr/preview/${this.typeId}/${this.state.page}`;
        return this.state.exact ? `${base}?overlay=1&ts=${this.state.stamp}` : `${base}?ts=${this.state.stamp}`;
    }

    issueFor(item) {
        const key = item.kind === "field" ? `field-${item.id}` : `signature-${item.id}`;
        return this.state.issues.find((issue) => issue.key === key);
    }

    isSelected(item) {
        return this.state.selection.some(sel => sel.kind === item.kind && sel.id === item.id);
    }

    setGeometry(item, geometry) {
        if (this.state.locked || this.state.saving) return;
        const ref = item.ref;
        if (item.kind === "field") {
            Object.assign(ref, { page: geometry.page ?? ref.page, x: geometry.x, y: geometry.y, width: geometry.width, height: geometry.height });
        } else {
            Object.assign(ref, {
                signature_page: geometry.page ?? ref.signature_page, signature_x: geometry.x, signature_y: geometry.y,
                signature_width: geometry.width, signature_height: geometry.height,
            });
        }
        this.markDirty(item);
    }

    markDirty(item) {
        this.state.dirty[`${item.kind}-${item.id}`] = true;
        this.state.exact = false;
    }
    boxStyle(item) {
        const z = this.state.zoom;
        return `left:${item.x * z}px;top:${item.y * z}px;width:${item.width * z}px;height:${item.height * z}px;`;
    }

    textStyle(item) {
        const f = item.ref;
        const z = this.state.zoom;
        return [
            `font-family:${FONT_STACKS[f.font_family] || FONT_STACKS.dejavu}`,
            `font-synthesis:none`,
            `font-size:${(f.font_size || 11) * z}px`,
            `text-align:${f.text_align || "right"}`,
            `font-weight:${f.bold ? "bold" : "normal"}`,
            `white-space:${f.multiline ? "pre-wrap" : "nowrap"}`,
            `line-height:1.15`,
        ].join(";");
    }

    sampleText(item) {
        return item.ref.sample_value || item.label;
    }

    get canvasStyle() {
        const { width, height } = this.pageSize;
        return `width:${width * this.state.zoom}px;height:${height * this.state.zoom}px;`;
    }
    select(item, ev) {
        const ref = {kind: item.kind, id: item.id};
        if (ev && (ev.ctrlKey || ev.metaKey || ev.shiftKey)) {
            const exists = this.state.selection.some(s => s.kind === item.kind && s.id === item.id);
            this.state.selection = exists ? this.state.selection.filter(s => s.kind !== item.kind || s.id !== item.id) : [...this.state.selection, ref];
        } else {
            this.state.selection = [ref];
        }
        this.state.selected = ref;
        if (item.page !== this.state.page && item.page <= this.state.pages.length) {
            this.state.page = item.page;
        }
    }

    selectIssue(issue) {
        const [kind, id] = issue.key.split("-");
        const item = this.items.find((i) => i.id === Number(id) && (kind === "field" ? i.kind === "field" : i.kind === "rule"));
        if (item) {
            this.select(item);
        }
    }

    setPage(delta) {
        this.state.page = Math.max(1, Math.min(this.state.pages.length, this.state.page + delta));
    }

    setZoom(delta) {
        this.state.zoom = Math.max(0.5, Math.min(3, Math.round((this.state.zoom + delta) * 100) / 100));
    }

    bringHere(item) {
        const { width, height } = this.pageSize;
        this.pushHistory();
        this.setGeometry(item, {
            page: this.state.page, x: 20, y: 20,
            width: Math.min(item.width, width - 40), height: Math.min(item.height, height - 40),
        });
        this.select(item);
    }

    get canSnap() {
        return Boolean((this.state.frames[this.state.page - 1] || []).length);
    }

    snapToFrame(item) {
        const frames = this.state.frames[item.page - 1] || [];
        const overlap = ([x, y, w, h]) =>
            Math.max(0, Math.min(x + w, item.x + item.width) - Math.max(x, item.x)) *
            Math.max(0, Math.min(y + h, item.y + item.height) - Math.max(y, item.y));
        const distance = ([x, y, w, h]) =>
            Math.hypot(x + w / 2 - (item.x + item.width / 2), y + h / 2 - (item.y + item.height / 2));
        const ranked = [...frames].sort((a, b) => overlap(b) - overlap(a) || distance(a) - distance(b));
        const frame = ranked[0];
        if (!frame || (!overlap(frame) && distance(frame) > 60)) {
            this.notification.add("لا يوجد مربع مرسوم قرب هذا الحقل. اسحبه فوق مربع من الاستمارة اولا.", { type: "warning" });
            return;
        }
        this.pushHistory();
        const inset = Math.min(2, frame[2] / 10, frame[3] / 6);
        this.setGeometry(item, {
            x: round(frame[0] + inset), y: round(frame[1] + inset),
            width: round(frame[2] - 2 * inset), height: round(frame[3] - 2 * inset),
        });
    }
    dragStart(ev, item, handle) {
        if (this.state.locked || this.state.saving || this.state.creator || this.state.drawMode || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey) { this.select(item, ev); return; }
        if (!this.isSelected(item)) this.select(item);
        else this.state.selected = {kind: item.kind, id: item.id};
        this.pushHistory();
        this.drag = { item, group: this.selectedItems.map(i => ({item:i,x:i.x,y:i.y,width:i.width,height:i.height})), handle, startX: ev.clientX, startY: ev.clientY, origin: { x: item.x, y: item.y, width: item.width, height: item.height } };
        window.addEventListener("pointermove", this.onMove);
        window.addEventListener("pointerup", this.onUp);
    }

    dragMove(ev) {
        const drag = this.drag;
        if (!drag) {
            return;
        }
        if (drag.create) {
            const box = drag.canvas.getBoundingClientRect();
            const x = Math.max(0, Math.min(this.pageSize.width, (ev.clientX - box.left) / this.state.zoom));
            const y = Math.max(0, Math.min(this.pageSize.height, (ev.clientY - box.top) / this.state.zoom));
            this.state.drawing = {x:Math.min(x,drag.startX), y:Math.min(y,drag.startY), width:Math.abs(x-drag.startX), height:Math.abs(y-drag.startY)};
            return;
        }
        const z = this.state.zoom;
        const dx = (ev.clientX - drag.startX) / z;
        const dy = (ev.clientY - drag.startY) / z;
        const o = drag.origin;
        const { width: pw, height: ph } = this.pageSize;
        let { x, y, width, height } = o;
        if (drag.handle === "move" && drag.group.length > 1) {
            const group = drag.group;
            const offsetX = Math.max(-Math.min(...group.map(g=>g.x)), Math.min(pw - Math.max(...group.map(g=>g.x+g.width)), dx));
            const offsetY = Math.max(-Math.min(...group.map(g=>g.y)), Math.min(ph - Math.max(...group.map(g=>g.y+g.height)), dy));
            for (const g of group) this.setGeometry(g.item,{x:round(g.x+offsetX),y:round(g.y+offsetY),width:g.width,height:g.height});
            return;
        }
        if (drag.handle === "move") {
            x = Math.max(0, Math.min(pw - width, o.x + dx));
            y = Math.max(0, Math.min(ph - height, o.y + dy));
        } else {
            const h = drag.handle;
            if (h.includes("e")) {
                width = Math.max(MIN_SIZE, Math.min(pw - o.x, o.width + dx));
            }
            if (h.includes("s")) {
                height = Math.max(MIN_SIZE, Math.min(ph - o.y, o.height + dy));
            }
            if (h.includes("w")) {
                x = Math.max(0, Math.min(o.x + o.width - MIN_SIZE, o.x + dx));
                width = o.x + o.width - x;
            }
            if (h.includes("n")) {
                y = Math.max(0, Math.min(o.y + o.height - MIN_SIZE, o.y + dy));
                height = o.y + o.height - y;
            }
        }
        this.setGeometry(drag.item, { x: round(x), y: round(y), width: round(width), height: round(height) });
    }

    dragEnd() {
        if (this.drag?.create) {
            const rect = this.state.drawing;
            const kind = this.state.drawMode;
            this.state.drawing = null; this.state.drawMode = null;
            if (rect && rect.width >= MIN_SIZE && rect.height >= MIN_SIZE) {
                this.state.creator = {kind, page:this.state.page, name:"", field_type:"text", source:"", approver_id:0, group_id:0, ...Object.fromEntries(Object.entries(rect).map(([k,v])=>[k,round(v)]))};
            } else this.notification.add("ارسم مستطيلا اكبر.",{type:"warning"});
        }
        this.drag = null;
        this.stopListening();
    }

    stopListening() {
        window.removeEventListener("pointermove", this.onMove);
        window.removeEventListener("pointerup", this.onUp);
    }

    keyNudge(ev) {
        const item = this.selectedItem;
        const tag = ev.target && ev.target.tagName;
        if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z" && !["INPUT","SELECT","TEXTAREA"].includes(tag)) { ev.preventDefault(); this.undo(); return; }
        if (!item || this.state.locked || this.state.saving || this.state.creator || ["INPUT", "SELECT", "TEXTAREA"].includes(tag)) {
            return;
        }
        const step = ev.shiftKey ? 10 : 1;
        const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
        const move = moves[ev.key];
        if (!move) {
            return;
        }
        ev.preventDefault();
        const { width: pw, height: ph } = this.pageSize;
        this.pushHistory();
        this.setGeometry(item, {
            x: Math.max(0, Math.min(pw - item.width, item.x + move[0])),
            y: Math.max(0, Math.min(ph - item.height, item.y + move[1])),
            width: item.width, height: item.height,
        });
    }
    geometryInput(name, ev) {
        const item = this.selectedItem;
        const value = parseFloat(ev.target.value);
        if (!item || this.state.locked || this.state.saving || !Number.isFinite(value)) {
            return;
        }
        this.pushHistory();
        const geometry = { x: item.x, y: item.y, width: item.width, height: item.height, page: item.page };
        geometry[name] = name === "page" ? Math.max(1, Math.min(this.state.pages.length, Math.round(value))) : Math.max(0, value);
        this.setGeometry(item, geometry);
        if (name === "page") {
            this.state.page = geometry.page;
        }
    }

    fieldInput(name, ev) {
        const item = this.selectedItem;
        if (!item || this.state.locked || this.state.saving || item.kind !== "field") {
            return;
        }
        let value;
        if (ev.target.type === "checkbox") {
            value = ev.target.checked;
        } else if (["font_size", "min_font_size"].includes(name)) {
            value = parseInt(ev.target.value, 10);
            if (!Number.isFinite(value)) {
                return;
            }
        } else {
            value = ev.target.value;
        }
        this.pushHistory();
        item.ref[name] = value;
        this.markDirty(item);
    }

    signatureInput(ev) {
        const item=this.selectedItem;
        if (!item || item.kind!=="rule" || this.state.locked || this.state.saving) return;
        this.pushHistory(); item.ref.print_signature=ev.target.checked; this.markDirty(item);
    }
    get hasUnsaved() { return Boolean(this.dirtyCount || this.state.creator || this.state.drawing); }
    get selectedItems() { return this.items.filter(i => this.isSelected(i) && i.page === this.state.page); }
    get drawingStyle() {
        const r=this.state.drawing;
        return r ? `left:${r.x*this.state.zoom}px;top:${r.y*this.state.zoom}px;width:${r.width*this.state.zoom}px;height:${r.height*this.state.zoom}px;` : "";
    }
    pushHistory() {
        this.history.push(JSON.stringify({fields:this.state.fields,rules:this.state.rules,dirty:this.state.dirty,selection:this.state.selection,selected:this.state.selected}));
        if (this.history.length > 50) this.history.shift();
        this.state.undoCount = this.history.length;
    }
    undo() {
        if (this.state.creator || this.state.drawing || this.state.drawMode) { this.cancelCreator(); this.drag=null; this.stopListening(); return; }
        if (!this.history.length || this.state.saving || this.state.locked || this.drag) return;
        Object.assign(this.state,JSON.parse(this.history.pop()));
        this.state.undoCount=this.history.length; this.state.exact=false; this.state.creator=null; this.state.drawing=null; this.state.drawMode=null;
    }
    nextKey(seed="field") {
        const base=seed.replace(/[^a-z0-9_]/g,"_").replace(/^[^a-z]+/,"") || "field";
        let n=1; while (this.state.fields.some(f=>f.key===`${base}_${n}`)) n++;
        return `${base}_${n}`;
    }
    startAdd(kind) {
        if (this.state.locked || this.state.saving || this.state.creator || (kind === "field" && this.state.structureLocked)) return;
        this.state.exact=false; this.state.drawMode=this.state.drawMode===kind ? null : kind;
    }
    drawStart(ev) {
        if (!this.state.drawMode || this.state.locked || this.state.saving || ev.button!==0) return;
        ev.preventDefault(); ev.stopPropagation();
        const box=ev.currentTarget.getBoundingClientRect();
        const x=Math.max(0,Math.min(this.pageSize.width,(ev.clientX-box.left)/this.state.zoom));
        const y=Math.max(0,Math.min(this.pageSize.height,(ev.clientY-box.top)/this.state.zoom));
        this.drag={create:true,canvas:ev.currentTarget,startX:x,startY:y};
        this.state.drawing={x,y,width:0,height:0};
        window.addEventListener("pointermove",this.onMove); window.addEventListener("pointerup",this.onUp);
    }
    creatorInput(name,ev) {
        if (!this.state.creator) return;
        this.state.creator[name]=ev.target.type==="checkbox" ? ev.target.checked : ev.target.value;
        if (name==="source") { const hit=this.state.sources.find(s=>"path:"+s[0]===this.state.creator.source); if (hit) { this.state.creator.field_type=hit[2]; if (!this.state.creator.name) this.state.creator.name=hit[1]; } }
    }
    cancelCreator() { this.state.creator=null; this.state.drawMode=null; this.state.drawing=null; }
    addCreator() {
        const c=this.state.creator;
        if (!c || !c.name.trim()) {this.notification.add("ادخل اسم الحقل او المرحلة.",{type:"warning"});return;}
        if (c.kind==="rule" && !Number(c.approver_id) && !Number(c.group_id)) {this.notification.add("اختر معتمدا او مجموعة.",{type:"warning"});return;}
        if (c.kind==="field" && !c.source) {this.notification.add("اختر مصدر القيمة.",{type:"warning"});return;}
        this.pushHistory();
        const id=this.nextLocalId--;
        if (c.kind==="field") {
            const system=c.source.startsWith("system:");
            this.state.fields.push({id,name:c.name.trim(),key:this.nextKey(c.key || "field"),
                field_type:system ? "system" : c.field_type,source_path:system ? false : c.source.slice(5),match_value:"",
                system_source:system ? c.source.slice(7) : false,
                sequence:Math.max(0,...this.state.fields.map(f=>f.sequence||0))+10,
                page:c.page || this.state.page,x:c.x,y:c.y,width:c.width,height:c.height,
                font_size:c.font_size || 11,min_font_size:c.min_font_size || 6,text_align:c.text_align || "right",font_family:c.font_family || "dejavu",
                bold:Boolean(c.bold),multiline:Boolean(c.multiline),sample_value:c.sample_value || "",date_format:c.date_format || "%d / %m / %Y"});
        } else {
            this.state.rules.push({id,name:c.name.trim(),approver_id:Number(c.approver_id) ? [Number(c.approver_id),""] : false,
                group_id:Number(c.group_id) ? [Number(c.group_id),""] : false,print_signature:true,
                sequence:Math.max(0,...this.state.rules.map(r=>r.sequence||0))+10,
                signature_page:c.page || this.state.page,signature_x:c.x,signature_y:c.y,signature_width:c.width,signature_height:c.height});
        }
        this.state.creator=null;
        const item=this.items.find(i=>i.id===id && i.kind===c.kind); this.markDirty(item); this.select(item);
    }
    duplicateSelected() {
        const item=this.selectedItem;
        if (!item || item.kind!=="field" || this.state.structureLocked || this.state.locked || this.state.saving || this.state.creator) return;
        const f=item.ref;
        if (["approver_name","approval_date"].includes(f.system_source)) {this.notification.add("حقول المعتمد/تاريخ الموافقة تنسخ من تبويب الحقول المطبوعة.",{type:"info"});return;}
        this.state.creator={...JSON.parse(JSON.stringify(f)),kind:"field",name:f.name+" 2",
            source:f.field_type==="system" ? "system:"+f.system_source : "path:"+f.source_path,
            x:Math.max(0,Math.min(this.pageSize.width-item.width,item.x+8)),
            y:Math.max(0,Math.min(this.pageSize.height-item.height,item.y+8)),field_type:f.field_type==="system"?"text":f.field_type};
    }
    alignSelected(edge) {
        const items=this.selectedItems;
        if (items.length<2 || this.state.locked || this.state.saving || this.state.creator) return;
        this.pushHistory();
        const left=Math.min(...items.map(i=>i.x)),top=Math.min(...items.map(i=>i.y));
        const right=Math.max(...items.map(i=>i.x+i.width)),bottom=Math.max(...items.map(i=>i.y+i.height));
        for (const i of items) this.setGeometry(i,{x:edge==="left"?left:edge==="right"?right-i.width:i.x,
            y:edge==="top"?top:edge==="bottom"?bottom-i.height:i.y,width:i.width,height:i.height});
    }
    fillLongSamples() {
        if (this.state.locked || this.state.saving || this.state.creator) return;
        this.pushHistory();
        for (const f of this.state.fields) {
            f.sample_value=f.field_type==="date" || (f.system_source || "").includes("date") ? "18/11/2026" :
                ["money"].includes(f.field_type) ? "1,250,000" : ["mark","mark_in"].includes(f.field_type) ? "✔" :
                f.multiline ? "ملاحظات تجريبية طويلة لاختبار مساحة الحقل\nSecond test line 2026" : "عبد الرحمن محمد علي حسن أحمد نظير عيسى";
            this.markDirty({kind:"field",id:f.id});
        }
        this.notification.add("تم ملء قيم طويلة للتجربة. احفظ ثم فعّل المعاينة الدقيقة للطباعة. بيانات الاستمارات لا تتغير.",{type:"info"});
    }
    collectChanges() {
        const changes={fields:{},rules:{},new_fields:[],new_rules:[]};
        const fieldKeys=[...FIELD_PROPS,"name","key","field_type","source_path","match_value","system_source","sequence","date_format"];
        for (const f of this.state.fields) {
            if (f.id<0) changes.new_fields.push({local_id:String(f.id),values:Object.fromEntries(fieldKeys.filter(k=>f[k]!==undefined).map(k=>[k,f[k]]))});
            else if (this.state.dirty[`field-${f.id}`]) changes.fields[f.id]=Object.fromEntries(FIELD_PROPS.map(k=>[k,f[k]===undefined?false:f[k]]));
        }
        for (const r of this.state.rules) {
            if (r.id<0) changes.new_rules.push({local_id:String(r.id),values:{...Object.fromEntries(RULE_PROPS.map(k=>[k,r[k]])),name:r.name,sequence:r.sequence,approver_id:r.approver_id ? r.approver_id[0] : false,group_id:r.group_id ? r.group_id[0] : false,print_signature:r.print_signature}});
            else if (this.state.dirty[`rule-${r.id}`]) changes.rules[r.id]=Object.fromEntries(RULE_PROPS.map(k=>[k,r[k]]));
        }
        return changes;
    }
    confirmDialog(body,confirmLabel="متابعة") {
        return new Promise(resolve=>this.dialog.add(ConfirmationDialog,{body,confirmLabel,confirm:()=>resolve(true),cancel:()=>resolve(false)}, {onClose:()=>resolve(false)}));
    }
    async confirmLeave() {
        if (!this.hasUnsaved && !this.state.saving) return true;
        if (this.state.saving) return false;
        if (this.state.creator || this.state.drawing) {this.notification.add("انه الحقل الجديد او الغه قبل المغادرة.",{type:"warning"});return false;}
        if (!await this.confirmDialog("حفظ التعديلات قبل المغادرة؟ الالغاء يبقيك في المصمم.","حفظ ومغادرة")) return false;
        return await this.save();
    }

    async save() {
        if (this.state.creator || this.state.drawing) {this.notification.add("انه الحقل الجديد او الغه اولا.",{type:"warning"});return false;}
        if (this.state.locked || this.state.saving) return false;
        if (!this.dirtyCount) return true;
        this.state.saving = true;
        try {
            const data = await this.orm.call("ad.form.template", "designer_save", [[this.typeId], this.collectChanges()]);
            const remap=sel=>sel ? {kind:sel.kind,id:data.created_ids?.[sel.kind]?.[String(sel.id)] || sel.id} : null;
            const selected=remap(this.state.selected), selection=this.state.selection.map(remap);
            this.applyData(data);this.state.selected=selected;this.state.selection=selection;
            this.notification.add(this.state.issues.length ? "تم الحفظ — راجع تحذيرات التخطيط" : "تم حفظ التخطيط",
                { type: this.state.issues.length ? "warning" : "success" });
            return true;
        } finally {
            this.state.saving = false;
        }
    }

    async reload() {
        if (this.state.saving) return;
        if (this.hasUnsaved && !await this.confirmDialog("تجاهل كل التعديلات غير المحفوظة؟","تجاهل التعديلات")) return;
        this.applyData(await this.orm.call("ad.form.template", "designer_load", [[this.typeId]]));
    }

    toggleExact() {
        if (this.dirtyCount) {
            this.notification.add("احفظ التخطيط اولا لترى المعاينة الدقيقة.", { type: "warning" });
            return;
        }
        this.state.exact = !this.state.exact;
        this.state.stamp = Date.now();
    }

    async back() {
        if (!await this.confirmLeave()) return;
        this.action.doAction({ type: "ir.actions.act_window", res_model: "ad.form.template", res_id: this.typeId, views: [[false, "form"]] });
    }
}

registry.category("actions").add("ad_pdf_designer", AdPdfDesigner);
