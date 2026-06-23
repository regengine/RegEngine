export const STEP_UP_REQUIRED_EVENT = 'regengine:requires-step-up';

type StepUpDetail = {
  code?: string;
  message?: string;
  auth_method?: string | null;
};

function hasRequiresStepUpCode(value: unknown): boolean {
  return Boolean(
    value
    && typeof value === 'object'
    && !Array.isArray(value)
    && (value as StepUpDetail).code === 'requires_step_up',
  );
}

export function isRequiresStepUpPayload(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') {
    return false;
  }

  const record = payload as { detail?: unknown; error?: unknown; code?: unknown };
  return hasRequiresStepUpCode(record)
    || hasRequiresStepUpCode(record.detail)
    || hasRequiresStepUpCode(record.error);
}

export function emitStepUpRequired(payload: unknown): void {
  if (typeof window === 'undefined' || !isRequiresStepUpPayload(payload)) {
    return;
  }

  window.dispatchEvent(
    new CustomEvent(STEP_UP_REQUIRED_EVENT, {
      detail: payload,
    }),
  );
}
