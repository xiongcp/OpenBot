export function createReconciliationWizardState(operation) {
  if (!operation || !operation.operation_id) throw Error('OPERATION_REQUIRED');
  return {
    step: 1,
    operationId: operation.operation_id,
    taskId: operation.task_id,
    toolName: operation.tool_name || operation.tool_id || 'unknown',
    expectedVersion: Number(operation.version || 1),
    evidenceText: '',
    outcome: null,
  };
}

export function validateReconciliationSubmission(payload) {
  if (!payload || typeof payload !== 'object') throw Error('RECONCILE_PAYLOAD_REQUIRED');
  if ('host_path' in payload || 'revive_consumed_grant' in payload) {
    throw Error('FORBIDDEN_RECONCILE_BYPASS_FIELD');
  }
  if (!['CONFIRMED_SUCCEEDED', 'CONFIRMED_NOT_EXECUTED', 'KEEP_UNKNOWN'].includes(payload.outcome)) {
    throw Error('INVALID_RECONCILE_OUTCOME');
  }
  if (payload.outcome !== 'KEEP_UNKNOWN') {
    const text = String(payload.evidenceContent || '').trim();
    if (!text || text.length > 16384) throw Error('EVIDENCE_CONTENT_REQUIRED');
  }
  return {
    operationId: payload.operationId,
    expectedVersion: Number(payload.expectedVersion),
    outcome: payload.outcome,
    evidenceContent: String(payload.evidenceContent || '').trim(),
  };
}
