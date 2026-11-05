export function buildDiffModel(diffLines = [], mode = 'split', { oldSha256 = null, newSha256 = null } = {}) {
  if (!['split', 'unified'].includes(mode)) throw Error('INVALID_DIFF_MODE');
  const rows = [];
  let oldLine = 1;
  let newLine = 1;
  for (const raw of diffLines) {
    const text = String(raw ?? '');
    if (text.startsWith('---') || text.startsWith('+++') || text.startsWith('@@')) {
      rows.push({ kind: 'meta', oldLine: null, newLine: null, leftText: text, rightText: text, text });
    } else if (text.startsWith('-')) {
      rows.push({ kind: 'remove', oldLine: oldLine++, newLine: null, leftText: text.slice(1), rightText: '', text });
    } else if (text.startsWith('+')) {
      rows.push({ kind: 'add', oldLine: null, newLine: newLine++, leftText: '', rightText: text.slice(1), text });
    } else {
      const clean = text.startsWith(' ') ? text.slice(1) : text;
      rows.push({ kind: 'context', oldLine: oldLine++, newLine: newLine++, leftText: clean, rightText: clean, text: clean });
    }
  }
  return {
    mode,
    oldBadge: oldSha256 ? String(oldSha256).slice(0, 8) : 'none',
    newBadge: newSha256 ? String(newSha256).slice(0, 8) : 'none',
    rows,
  };
}

export function computeApprovalCountdown(expiresAtMs, nowMs, { preconditionDrift = false } = {}) {
  const remainingMs = Math.max(0, Number(expiresAtMs) - Number(nowMs));
  const remainingSeconds = Math.ceil(remainingMs / 1000);
  const expired = remainingMs <= 0;
  const approveDisabled = expired || Boolean(preconditionDrift);
  return {
    remainingMs,
    remainingSeconds,
    expired,
    preconditionDrift: Boolean(preconditionDrift),
    approveDisabled,
    regenerateRequired: approveDisabled,
  };
}
