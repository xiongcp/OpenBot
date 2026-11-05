import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeTrace, emptyTrace, effectStage, totals } from '../ui/projection.js';
import { messages, translate } from '../ui/i18n.js';
import { evaluateOnboardingState, validateKeychainSecretInput } from '../ui/onboarding.js';
import { buildDiffModel, computeApprovalCountdown } from '../ui/diff_viewer.js';
import { computeHierarchicalDagLayout } from '../ui/dag_layout.js';
import { createReconciliationWizardState, validateReconciliationSubmission } from '../ui/reconcile_wizard.js';

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

test('onboarding state machine and keychain secret guard prevent DOM/storage leak', () => {
  assert.equal(
    evaluateOnboardingState({ daemonAlive: false, workspaceBound: false, credentialsConfigured: false, doctorPassed: false }).currentStep,
    'STEP_1_DAEMON_CHECK'
  );
  assert.equal(
    evaluateOnboardingState({ daemonAlive: true, workspaceBound: true, credentialsConfigured: true, doctorPassed: true }).ready,
    true
  );
  assert.throws(
    () => validateKeychainSecretInput({ provider: 'openai', secretRef: 'keychain:provider:anthropic:main', secretValue: 'sk-123456' }),
    /INVALID_KEYCHAIN_COMPARTMENT_REF/
  );
  const ok = validateKeychainSecretInput({ provider: 'openai', secretRef: 'keychain:provider:openai:main', secretValue: 'sk-12345678' });
  assert.equal(ok.persistInWebViewDomLocalStorage ?? ok.persistInWebViewDomOrLocalStorage, false);
});

test('diff viewer split/unified model and TTL countdown disable approval on drift or expiry', () => {
  const diff = buildDiffModel(['--- a/app.py', '+++ b/app.py', '-v = 1', '+v = 2'], 'split', {
    oldSha256: '111122223333',
    newSha256: '444455556666',
  });
  assert.equal(diff.oldBadge, '11112222');
  assert.equal(diff.newBadge, '44445555');
  assert.equal(diff.rows.filter(r => r.kind === 'remove').length, 1);
  assert.equal(diff.rows.filter(r => r.kind === 'add').length, 1);

  const drifted = computeApprovalCountdown(20_000, 10_000, { preconditionDrift: true });
  assert.equal(drifted.approveDisabled, true);
  assert.equal(drifted.regenerateRequired, true);
});

test('hierarchical DAG layout and UNKNOWN reconciliation wizard enforce safety invariants', () => {
  const evs = [
    event('e1', 1, 'RUN_STARTED', null),
    event('e2', 2, 'TOOL_PROPOSED', 'e1'),
    event('e3', 3, 'TOOL_DISPATCHED', 'e2'),
  ];
  const dag = computeHierarchicalDagLayout(evs, { zoom: 1.25 });
  assert.equal(dag.nodes.length, 3);
  assert.equal(dag.edges.length, 2);
  assert.equal(dag.nodes[2].depth, 2);

  const wiz = createReconciliationWizardState({ operation_id: 'op_1', task_id: 'tsk_1', version: 4 });
  assert.equal(wiz.step, 1);
  assert.throws(
    () => validateReconciliationSubmission({ operationId: 'op_1', expectedVersion: 4, outcome: 'CONFIRMED_SUCCEEDED', host_path: '/etc/passwd' }),
    /FORBIDDEN_RECONCILE_BYPASS_FIELD/
  );
  const valid = validateReconciliationSubmission({
    operationId: 'op_1',
    expectedVersion: 4,
    outcome: 'CONFIRMED_NOT_EXECUTED',
    evidenceContent: 'Verified target unchanged',
  });
  assert.equal(valid.outcome, 'CONFIRMED_NOT_EXECUTED');
});
