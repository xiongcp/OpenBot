export const emptyTrace = () => ({ runId: null, events: [], lastSeq: 0, missingParents: [] });
export function mergeTrace(previous, batch) {
  if (previous.runId && batch.run_id !== previous.runId) throw Error('RESET_REQUIRED');
  const entries = new Map(previous.events.map(e => [e.event_id, e]));
  for (const e of batch.events) {
    if (e.run_id !== batch.run_id || !Number.isSafeInteger(e.global_seq)) throw Error('INVALID_TRACE');
    entries.set(e.event_id, e);
  }
  const events = [...entries.values()].sort((a, b) => a.global_seq - b.global_seq);
  return { runId: batch.run_id, events, lastSeq: Math.max(previous.lastSeq, batch.last_seq),
    missingParents: [...new Set(events.filter(e => e.parent_event_id && !entries.has(e.parent_event_id)).map(e => e.parent_event_id))] };
}
export function effectStage(e) {
  if (['TOOL_PROPOSED', 'WAITING_APPROVAL'].includes(e.kind)) return 'proposed';
  if (e.kind === 'TOOL_DISPATCHED') return 'dispatched';
  if (e.kind === 'TOOL_RETURNED') return 'returned';
  if (e.kind === 'RUN_INTERRUPTED') return 'interrupted';
  return 'recorded';
}
export function totals(events) {
  return events.reduce((n, e) => ({
    input: n.input + (e.kind === 'MODEL_RETURNED' ? e.data.input_tokens || 0 : 0),
    output: n.output + (e.kind === 'MODEL_RETURNED' ? e.data.output_tokens || 0 : 0),
    estimated: n.estimated || e.data.usage_estimated === true,
    calls: n.calls + (e.kind === 'TOOL_DISPATCHED' ? 1 : 0),
  }), { input: 0, output: 0, calls: 0, estimated: false });
}
