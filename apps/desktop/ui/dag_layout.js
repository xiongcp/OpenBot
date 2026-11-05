import { effectStage } from './projection.js';

export function computeHierarchicalDagLayout(events = [], { filterStage = 'all', zoom = 1.0, panX = 0, panY = 0 } = {}) {
  const clampedZoom = Math.min(2.0, Math.max(0.5, Number(zoom) || 1.0));
  const byId = new Map(events.map(e => [e.event_id, e]));
  const depthMemo = new Map();

  function getDepth(eventId, visiting = new Set()) {
    if (depthMemo.has(eventId)) return depthMemo.get(eventId);
    if (visiting.has(eventId)) return 0;
    visiting.add(eventId);
    const ev = byId.get(eventId);
    const parentId = ev?.parent_event_id;
    const d = parentId && byId.has(parentId) ? getDepth(parentId, visiting) + 1 : 0;
    depthMemo.set(eventId, d);
    return d;
  }

  const filtered = events.filter(e => filterStage === 'all' || effectStage(e) === filterStage);
  const laneCounts = new Map();
  const nodes = filtered.map((ev, index) => {
    const depth = getDepth(ev.event_id);
    const lane = laneCounts.get(depth) || 0;
    laneCounts.set(depth, lane + 1);
    const x = Math.round((40 + lane * 200 + panX) * clampedZoom);
    const y = Math.round((24 + depth * 96 + panY) * clampedZoom);
    return {
      event_id: ev.event_id,
      parent_event_id: ev.parent_event_id || null,
      kind: ev.kind,
      stage: effectStage(ev),
      depth,
      lane,
      x,
      y,
      ordinal: index + 1,
    };
  });
  const nodeMap = new Map(nodes.map(n => [n.event_id, n]));
  const edges = [];
  for (const n of nodes) {
    if (n.parent_event_id && nodeMap.has(n.parent_event_id)) {
      const p = nodeMap.get(n.parent_event_id);
      edges.push({ from: p.event_id, to: n.event_id, x1: p.x + 82, y1: p.y + 64, x2: n.x + 82, y2: n.y });
    }
  }
  return { zoom: clampedZoom, filterStage, nodes, edges };
}
