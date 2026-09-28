/**
 * MiniMax H3 Director Motion Fix — graph-wired pack witness.
 *
 * The first-pass cache panel runs on the backend, where the Director's
 * `motion_fix` link is invisible. This module packs the connected Motion Fix
 * node's widgets so `first_pass_cache_status` can rebuild the same
 * `motion_*` fingerprint keys the run writes.
 */

import { app } from "../../scripts/app.js";

function widgetByName(node, name) {
    return (node?.widgets || []).find((w) => w?.name === name);
}

function widgetValue(w) {
    return w?.value;
}

function widgetStr(node, name, fallback) {
    const v = widgetValue(widgetByName(node, name));
    if (v == null || v === "") return fallback;
    return String(v);
}

function widgetNum(node, name, fallback) {
    const n = Number(widgetValue(widgetByName(node, name)));
    return Number.isFinite(n) ? n : fallback;
}

function widgetBool(node, name, fallback) {
    const v = widgetValue(widgetByName(node, name));
    if (v === true || v === false) return v;
    if (v == null || v === "") return fallback;
    if (v === 1 || v === "1" || v === "true") return true;
    if (v === 0 || v === "0" || v === "false") return false;
    return Boolean(v);
}

function nodeMuted(node) {
    const mode = Number(node?.mode ?? 0);
    return mode === 2 || mode === 4; // NEVER / BYPASS
}

function inputSourceNode(node, inputName) {
    const graph = node?.graph ?? app.graph ?? app.canvas?.graph;
    const input = (node?.inputs || []).find((i) => i?.name === inputName);
    if (!input || input.link == null) return null;
    const link = graph?.links?.[input.link] ?? graph?._links?.[input.link];
    const id = link?.origin_id;
    if (id == null) return null;
    if (typeof graph?.getNodeById === "function") {
        return graph.getNodeById(id) || null;
    }
    return (graph?._nodes || []).find((n) => String(n?.id) === String(id)) || null;
}

/**
 * Pack the graph-wired Motion Fix node for the cache panel. Unconnected /
 * bypassed → null (the backend then treats the plan as motion-off).
 */
export function collectMotionFixWitness(director) {
    const src = inputSourceNode(director, "motion_fix");
    if (!src || nodeMuted(src)) return null;
    // Guard against a wrong node type plugged into the socket.
    if (widgetByName(src, "mode") === undefined && widgetByName(src, "dilate") === undefined) {
        return null;
    }
    return {
        enabled: true,
        mode: widgetStr(src, "mode", "uniform"),
        dilate: widgetNum(src, "dilate", 2),
        source_init_denoise: widgetNum(src, "source_init_denoise", 0.6),
        audio_recover: widgetStr(src, "audio_recover", "splice"),
        gate_abs: widgetNum(src, "gate_abs", 2.0),
        gate_rel: widgetNum(src, "gate_rel", 0.35),
        bridge: widgetNum(src, "bridge", 2),
        ramp: widgetNum(src, "ramp", 1),
        min_frames: widgetNum(src, "min_frames", 36),
        max_slowed_frames: widgetNum(src, "max_slowed_frames", 512),
        fail_fallback: widgetBool(src, "fail_fallback", true),
    };
}
