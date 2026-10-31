import { getErrorStatus } from '@/lib/api-error';

export const BETA_UNAVAILABLE_COPY = 'not yet available in RegEngine Beta';

export function isBetaUnavailableStatus(status: unknown): boolean {
    return status === 404 || status === 403;
}

export function isBetaUnavailableError(error: unknown): boolean {
    return isBetaUnavailableStatus(getErrorStatus(error));
}
