export function inflowErrorMessage(status: number, payload: Record<string, unknown>): string {
    let message: string;
    if (typeof payload.error === 'string' && payload.error) {
        message = payload.error;
    } else if (typeof payload.detail === 'string' && payload.detail) {
        message = payload.detail;
    } else if (status === 404) {
        message =
            'Inflow Lab is unavailable on this deployment. Core backend health does not include the simulator.';
    } else {
        message = `Inflow Lab request failed: ${status}`;
    }
    // Proxy session failures include a recovery hint; surface it so the user
    // knows to refresh and sign in again before live actions work.
    if (typeof payload.hint === 'string' && payload.hint.trim()) {
        return `${message} ${payload.hint.trim()}`;
    }
    return message;
}
