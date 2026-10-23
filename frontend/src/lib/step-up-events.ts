export const STEP_UP_REQUIRED_EVENT = 'regengine:requires-step-up';

/** Fallback for a blocked action whose caller did not name it. */
export const DEFAULT_STEP_UP_REASON = "Confirm it's you to complete this action.";

type StepUpDetail = {
  code?: string;
  message?: string;
  auth_method?: string | null;
};

export type StepUpRequest = {
  /** Sentence shown in the dialog naming the action being protected. */
  reason: string;
  /** Where Cancel sends the user. Omit to stay on the current page. */
  returnTo?: string;
  /** Runs after passkey verification instead of reloading the page. */
  onSuccess?: () => void;
};

export type StepUpEventDetail = StepUpRequest & {
  payload?: unknown;
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

/** Opens the step-up dialog for an action the user just tried. */
export function requestStepUp(request: StepUpRequest, payload?: unknown): void {
  if (typeof window === 'undefined') {
    return;
  }

  const detail: StepUpEventDetail = { ...request, payload };
  window.dispatchEvent(new CustomEvent(STEP_UP_REQUIRED_EVENT, { detail }));
}

export function emitStepUpRequired(payload: unknown, request: StepUpRequest): void {
  if (!isRequiresStepUpPayload(payload)) {
    return;
  }

  requestStepUp(request, payload);
}
