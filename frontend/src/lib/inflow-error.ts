export function inflowErrorMessage(status: number, payload: Record<string, unknown>): string {
    if (typeof payload.error === 'string' && payload.error) return payload.error;
    if (typeof payload.detail === 'string' && payload.detail) return payload.detail;
    if (status === 404) return 'Inflow Lab is unavailable on this deployment. Core backend health does not include the simulator.';
    return `Inflow Lab request failed: ${status}`;
}
