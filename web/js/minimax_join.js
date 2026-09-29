/**
 * MiniMax H3 Director Join Segments — drag-and-drop segment picker.
 *
 * Selects a historical segment-export run from the server, lets the user tick /
 * drag / reorder files, and mirrors the ordered selection into the node's
 * `files` text widget (the backend joins exactly that list). No Director
 * execution is involved.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { t } from "./minimax_i18n.js";

const JOIN_CLASS = "MiniMaxH3DirectorJoinSegments";
const WIDGET_NAME = "join_file_picker";
const ROW_HEIGHT = 22;

function escapeHtml(text) {
    return String(text ?? "").replace(/[&<>"']/g, (ch) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));
}

function basename(path) {
    return String(path || "").split(/[\\/]/).pop() || path;
}

function filesWidget(node) {
    return node?.widgets?.find((w) => w?.name === "files");
}

function setOrderedFromText(node, ui) {
    const raw = filesWidget(node)?.value ?? "";
    const seen = new Set();
    ui.ordered = [];
    for (const line of String(raw).split(/\r?\n/)) {
        const path = line.trim().replace(/^["']|["']$/g, "");
        if (!path || seen.has(path)) continue;
        seen.add(path);
        ui.ordered.push({ path, name: basename(path), include: true });
    }
    ui.selected = ui.ordered.length ? 0 : -1;
}

function syncToText(node, ui) {
    const text = ui.ordered.filter((item) => item.include).map((item) => item.path).join("\n");
    const widget = filesWidget(node);
    if (widget && widget.value !== text) {
        widget.value = text;
    }
    app.graph?.setDirtyCanvas?.(true, true);
}

function renderList(node, ui) {
    const list = ui.listEl;
    list.innerHTML = "";
    if (!ui.ordered.length) {
        const empty = document.createElement("div");
        empty.style.cssText = "padding:6px;color:#777";
        empty.textContent = t("joinNode.empty");
        list.appendChild(empty);
        return;
    }
    ui.ordered.forEach((item, index) => {
        const row = document.createElement("div");
        row.draggable = true;
        row.dataset.index = String(index);
        row.style.cssText = [
            "display:flex", "align-items:center", "gap:6px", "padding:1px 4px",
            `height:${ROW_HEIGHT}px`, "border-radius:3px", "cursor:grab",
            index === ui.selected ? "background:#22333f" : "",
        ].join(";");
        row.innerHTML = `
            <span style="opacity:.55;flex-shrink:0">☰</span>
            <input type="checkbox" ${item.include ? "checked" : ""} style="flex-shrink:0">
            <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                  title="${escapeHtml(item.path)}">${escapeHtml(item.name)}</span>`;
        const cb = row.querySelector("input");
        cb.onchange = () => {
            item.include = !!cb.checked;
            syncToText(node, ui);
        };
        row.onclick = (event) => {
            if (event.target === cb) return;
            ui.selected = index;
            renderList(node, ui);
        };
        row.ondragstart = (event) => {
            ui.dragFrom = index;
            event.dataTransfer.effectAllowed = "move";
        };
        row.ondragover = (event) => {
            event.preventDefault();
            event.dataTransfer.dropEffect = "move";
            row.style.boxShadow = "inset 0 2px 0 #6ab0ff";
        };
        row.ondragleave = () => {
            row.style.boxShadow = "";
        };
        row.ondrop = (event) => {
            event.preventDefault();
            row.style.boxShadow = "";
            const from = ui.dragFrom;
            ui.dragFrom = null;
            if (from == null || from === index) return;
            const [moved] = ui.ordered.splice(from, 1);
            ui.ordered.splice(index, 0, moved);
            ui.selected = index;
            renderList(node, ui);
            syncToText(node, ui);
        };
        list.appendChild(row);
    });
}

function selectedIndex(ui) {
    return Number.isInteger(ui.selected) && ui.selected >= 0 && ui.selected < ui.ordered.length
        ? ui.selected
        : -1;
}

function moveSelected(node, ui, delta) {
    const index = selectedIndex(ui);
    if (index < 0) return;
    const target = Math.max(0, Math.min(ui.ordered.length - 1, index + delta));
    if (target === index) return;
    const [moved] = ui.ordered.splice(index, 1);
    ui.ordered.splice(target, 0, moved);
    ui.selected = target;
    renderList(node, ui);
    syncToText(node, ui);
}

async function fetchRuns() {
    const resp = await api.fetchApi("/minimax/director/list_segment_runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ limit: 60 }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data?.error) {
        throw new Error(data?.error || `HTTP ${resp.status}`);
    }
    return Array.isArray(data.runs) ? data.runs : [];
}

function setStatus(ui, text, kind = "") {
    if (!ui.statusEl) return;
    ui.statusEl.textContent = text || "";
    ui.statusEl.style.color = kind === "err" ? "#f88" : kind === "ok" ? "#4fff8f" : "#9ab";
}

async function refreshRuns(node, ui) {
    setStatus(ui, t("joinNode.loading"));
    try {
        ui.runs = await fetchRuns();
    } catch (err) {
        ui.runs = [];
        setStatus(ui, t("joinNode.failed", { err: err?.message || err }), "err");
        return;
    }
    const sel = ui.runSel;
    sel.innerHTML = "";
    if (!ui.runs.length) {
        setStatus(ui, t("joinNode.noRuns"), "err");
        return;
    }
    for (const run of ui.runs) {
        const opt = document.createElement("option");
        opt.value = run.dir;
        opt.textContent = `${run.name} (${run.count})`;
        sel.appendChild(opt);
    }
    setStatus(ui, t("joinNode.runsReady", { n: ui.runs.length }), "ok");
}

function loadRunIntoList(node, ui, dir) {
    const run = (ui.runs || []).find((r) => r.dir === dir);
    if (!run) return;
    ui.ordered = (run.files || []).map((path) => ({
        path,
        name: basename(path),
        include: true,
    }));
    ui.selected = ui.ordered.length ? 0 : -1;
    renderList(node, ui);
    syncToText(node, ui);
    setStatus(ui, t("joinNode.loaded", { n: ui.ordered.length }), "ok");
}

function widgetByName(node, name) {
    return node?.widgets?.find((w) => w?.name === name);
}

function widgetStr(node, name, fallback = "") {
    const v = widgetByName(node, name)?.value;
    if (v == null || v === "") return fallback;
    return String(v);
}

async function joinNow(node, ui, { selection = false } = {}) {
    const payload = {
        output_name: widgetStr(node, "output_name", "director_joined"),
        output_dir: widgetStr(node, "output_dir", ""),
    };
    if (selection) {
        const files = filesWidget(node)?.value ?? "";
        if (String(files).trim()) {
            payload.files = files;
        } else if (ui.runSel?.value) {
            payload.directory = ui.runSel.value;
        }
    }
    setStatus(ui, t("joinNode.joining"), "");
    if (ui.oneClickBtn) ui.oneClickBtn.disabled = true;
    if (ui.joinSelBtn) ui.joinSelBtn.disabled = true;
    try {
        const resp = await api.fetchApi("/minimax/director/join_segments", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok || data?.error) {
            throw new Error(data?.error || `HTTP ${resp.status}`);
        }
        ui.lastOutput = String(data.output || "");
        setStatus(ui, t("joinNode.done", { path: ui.lastOutput }), "ok");
    } catch (err) {
        setStatus(ui, t("joinNode.joinFailed", { err: err?.message || err }), "err");
    } finally {
        if (ui.oneClickBtn) ui.oneClickBtn.disabled = false;
        if (ui.joinSelBtn) ui.joinSelBtn.disabled = false;
    }
}

function buildJoinUI(node) {
    if (node._mmxJoinUI || typeof node.addDOMWidget !== "function") return;
    const root = document.createElement("div");
    root.style.cssText = "display:flex;flex-direction:column;gap:4px;padding:2px;font-size:11px;color:#9ab;";

    // ── One-click row ────────────────────────────────────────────────
    const primary = document.createElement("div");
    primary.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap";
    primary.innerHTML = `<b>${escapeHtml(t("joinNode.title"))}</b>`;
    const oneClickBtn = document.createElement("button");
    oneClickBtn.type = "button";
    oneClickBtn.className = "bd-btn bd-join-oneclick";
    oneClickBtn.textContent = t("joinNode.oneClick");
    oneClickBtn.style.cssText = "padding:4px 10px;font-weight:600";
    primary.appendChild(oneClickBtn);
    root.appendChild(primary);

    const statusEl = document.createElement("div");
    statusEl.style.cssText = "color:#9ab;min-height:14px;user-select:text;word-break:break-all";
    statusEl.textContent = t("joinNode.hint");
    root.appendChild(statusEl);

    // ── Advanced (collapsed by default) ──────────────────────────────
    const advanced = document.createElement("details");
    advanced.style.cssText = "border-top:1px solid #333;padding-top:4px";
    const summary = document.createElement("summary");
    summary.style.cssText = "cursor:pointer;color:#8fb;user-select:none";
    summary.textContent = t("joinNode.advanced");
    advanced.appendChild(summary);

    const head = document.createElement("div");
    head.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:4px";
    const runSel = document.createElement("select");
    runSel.className = "bd-select";
    runSel.style.cssText = "max-width:210px;flex:1";
    head.appendChild(runSel);

    const mkBtn = (key, cls, parent = head) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = `bd-btn ${cls}`;
        b.textContent = t(key);
        parent.appendChild(b);
        return b;
    };
    const loadBtn = mkBtn("joinNode.load", "bd-join-load");
    const refreshBtn = mkBtn("joinNode.refresh", "bd-join-refresh");
    const joinSelBtn = mkBtn("joinNode.joinSelected", "bd-join-selected");
    advanced.appendChild(head);

    const tools = document.createElement("div");
    tools.style.cssText = "display:flex;gap:4px;align-items:center;flex-wrap:wrap;margin-top:4px";
    advanced.appendChild(tools);
    const allBtn = mkBtn("joinNode.selectAll", "bd-join-all", tools);
    const noneBtn = mkBtn("joinNode.selectNone", "bd-join-none", tools);
    const upBtn = mkBtn("joinNode.up", "bd-join-up", tools);
    const downBtn = mkBtn("joinNode.down", "bd-join-down", tools);
    const removeBtn = mkBtn("joinNode.remove", "bd-join-remove", tools);
    const clearBtn = mkBtn("joinNode.clear", "bd-join-clear", tools);
    const textBtn = mkBtn("joinNode.fromText", "bd-join-from-text", tools);

    const listEl = document.createElement("div");
    listEl.style.cssText = [
        "min-height:90px", "max-height:220px", "overflow:auto", "margin-top:4px",
        "border:1px solid #333", "border-radius:4px", "background:#141414",
    ].join(";");
    advanced.appendChild(listEl);
    root.appendChild(advanced);

    const ui = {
        root, runSel, listEl, statusEl, advanced, oneClickBtn, joinSelBtn,
        ordered: [], selected: -1, dragFrom: null, runs: [], lastOutput: "",
    };
    ui.widget = node.addDOMWidget(WIDGET_NAME, "join_file_picker", root, {
        hideOnZoom: false,
        getMinHeight: () => 220,
    });
    if (ui.widget) {
        ui.widget.serialize = false;
        if (!ui.widget.options) ui.widget.options = {};
        ui.widget.options.serialize = false;
    }
    node._mmxJoinUI = ui;

    oneClickBtn.onclick = (event) => {
        event.preventDefault();
        void joinNow(node, ui, { selection: false });
    };
    joinSelBtn.onclick = (event) => {
        event.preventDefault();
        void joinNow(node, ui, { selection: true });
    };
    runSel.onchange = () => loadRunIntoList(node, ui, runSel.value);
    loadBtn.onclick = (event) => {
        event.preventDefault();
        loadRunIntoList(node, ui, runSel.value);
    };
    refreshBtn.onclick = (event) => {
        event.preventDefault();
        void refreshRuns(node, ui);
    };
    allBtn.onclick = (event) => {
        event.preventDefault();
        ui.ordered.forEach((item) => { item.include = true; });
        renderList(node, ui);
        syncToText(node, ui);
    };
    noneBtn.onclick = (event) => {
        event.preventDefault();
        ui.ordered.forEach((item) => { item.include = false; });
        renderList(node, ui);
        syncToText(node, ui);
    };
    upBtn.onclick = (event) => { event.preventDefault(); moveSelected(node, ui, -1); };
    downBtn.onclick = (event) => { event.preventDefault(); moveSelected(node, ui, 1); };
    removeBtn.onclick = (event) => {
        event.preventDefault();
        const index = selectedIndex(ui);
        if (index < 0) return;
        ui.ordered.splice(index, 1);
        ui.selected = Math.min(index, ui.ordered.length - 1);
        renderList(node, ui);
        syncToText(node, ui);
    };
    clearBtn.onclick = (event) => {
        event.preventDefault();
        ui.ordered = [];
        ui.selected = -1;
        renderList(node, ui);
        syncToText(node, ui);
    };
    textBtn.onclick = (event) => {
        event.preventDefault();
        setOrderedFromText(node, ui);
        renderList(node, ui);
        setStatus(ui, t("joinNode.loaded", { n: ui.ordered.length }), "ok");
    };

    setOrderedFromText(node, ui);
    renderList(node, ui);
    void refreshRuns(node, ui);
}

function scheduleJoinUI(node) {
    buildJoinUI(node);
    queueMicrotask(() => buildJoinUI(node));
    setTimeout(() => buildJoinUI(node), 0);
    setTimeout(() => {
        buildJoinUI(node);
        const ui = node._mmxJoinUI;
        if (ui) {
            setOrderedFromText(node, ui);
            renderList(node, ui);
            if (!(ui.runs || []).length) void refreshRuns(node, ui);
        }
    }, 200);
}

app.registerExtension({
    name: "ComfyUI.MiniMaxH3DirectorJoinSegments",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData?.name !== JOIN_CLASS) return;
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (...args) {
            const result = onNodeCreated?.apply(this, args);
            scheduleJoinUI(this);
            return result;
        };
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...args) {
            const result = onConfigure?.apply(this, args);
            scheduleJoinUI(this);
            return result;
        };
    },
});
