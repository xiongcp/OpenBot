export const ONBOARDING_STEPS = [
  'STEP_1_DAEMON_CHECK',
  'STEP_2_WORKSPACE_BIND',
  'STEP_3_KEYCHAIN_SECRET',
  'STEP_4_DOCTOR_SELF_CHECK',
  'READY',
];

export function evaluateOnboardingState({ daemonAlive, workspaceBound, credentialsConfigured, doctorPassed }) {
  if (!daemonAlive) return { currentStep: 'STEP_1_DAEMON_CHECK', stepIndex: 0, ready: false };
  if (!workspaceBound) return { currentStep: 'STEP_2_WORKSPACE_BIND', stepIndex: 1, ready: false };
  if (!credentialsConfigured) return { currentStep: 'STEP_3_KEYCHAIN_SECRET', stepIndex: 2, ready: false };
  if (!doctorPassed) return { currentStep: 'STEP_4_DOCTOR_SELF_CHECK', stepIndex: 3, ready: false };
  return { currentStep: 'READY', stepIndex: 4, ready: true };
}

export function validateKeychainSecretInput({ provider, secretRef, secretValue }) {
  if (!['openai', 'anthropic', 'gemini', 'ollama'].includes(provider)) {
    throw Error('UNSUPPORTED_PROVIDER');
  }
  const expectedPrefix = `keychain:provider:${provider}:`;
  if (typeof secretRef !== 'string' || !secretRef.startsWith(expectedPrefix)) {
    throw Error('INVALID_KEYCHAIN_COMPARTMENT_REF');
  }
  if (typeof secretValue !== 'string' || secretValue.trim().length < 6) {
    throw Error('EMPTY_OR_SHORT_SECRET');
  }
  return {
    provider,
    secretRef,
    persistInWebViewDomOrLocalStorage: false,
    redactedPreview: `${secretRef} (••••${secretValue.slice(-4)})`,
  };
}
