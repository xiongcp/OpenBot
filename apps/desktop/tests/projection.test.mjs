import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeTrace, emptyTrace, effectStage, totals } from '../ui/projection.js';
import { messages, translate } from '../ui/i18n.js';

const event = (id, seq, kind, parent = null, data = {}) => ({ event_id: id, global_seq: seq, kind, parent_event_id: parent, data, run_id: 'run_1', task_id: 'tsk_1' });
const batch = events => ({ run_id: 'run_1', task_id: 'tsk_1', events, last_seq: events.at(-1)?.global_seq || 0 });

test('replay merges duplicate delivery without inventing steps or effects', () => {
  const a = event('a', 3, 'TOOL_PROPOSED');
  const b = event('b', 5, 'TOOL_DISPATCHED', 'a');
  let state = mergeTrace(emptyTrace(), batch([a, b]));
  state = mergeTrace(state, batch([b]));
  assert.equal(state.events.length, 2);
  assert.equal(effectStage(a), 'proposed');
  assert.equal(effectStage(b), 'dispatched');
  assert.equal(totals(state.events).calls, 1);
});

test('gaps and changed run identity stay explicit', () => {
  const state = mergeTrace(emptyTrace(), batch([event('b', 9, 'TOOL_RETURNED', 'missing')]));
  assert.deepEqual(state.missingParents, ['missing']);
  assert.throws(() => mergeTrace(state, { ...batch([]), run_id: 'run_2' }), /RESET_REQUIRED/);
});

test('untrusted text remains unchanged data and UNKNOWN is never success', () => {
  const text = '<img src=x onerror="globalThis.pwned=true">';
  const state = mergeTrace(emptyTrace(), batch([event('x', 1, 'RUN_INTERRUPTED', null, { text })]));
  assert.equal(state.events[0].data.text, text);
  assert.equal(effectStage(state.events[0]), 'interrupted');
  assert.equal(effectStage(event('a', 2, 'WAITING_APPROVAL')), 'proposed');
});

test('both languages cover identical labels and all event kinds', () => {
  assert.deepEqual(Object.keys(messages['zh-CN']).sort(), Object.keys(messages.en).sort());
  for (const kind of ['RUN_STARTED','SKILL_LOADED','MODEL_REQUESTED','MODEL_RETURNED','TOOL_PROPOSED','WAITING_APPROVAL','TOOL_DISPATCHED','TOOL_RETURNED','OUTCOME_VERIFIED','RUN_FINISHED','RUN_INTERRUPTED']) {
    assert.notEqual(translate('en', kind), kind);
    assert.notEqual(translate('zh-CN', kind), kind);
  }
});
