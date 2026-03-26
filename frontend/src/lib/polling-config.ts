/**
 * Centralized polling interval configuration.
 *
 * All polling intervals are overridable via NEXT_PUBLIC_POLL_*_MS env vars.
 * Default values are production-tuned: health checks at 30s, metrics at 15s,
 * data refresh at 30s. (L11 from API audit)
 */

/** Health check endpoints (admin, ingestion, compliance) */
export const POLL_HEALTH_MS =
    Number(process.env.NEXT_PUBLIC_POLL_HEALTH_MS) || 30_000;

/** System metrics and real-time dashboards */
export const POLL_METRICS_MS =
    Number(process.env.NEXT_PUBLIC_POLL_METRICS_MS) || 15_000;

/** Data list refresh (partners, contracts, tax, etc.) */
export const POLL_DATA_MS =
    Number(process.env.NEXT_PUBLIC_POLL_DATA_MS) || 30_000;

/** Control plane / compliance state */
export const POLL_CONTROL_PLANE_MS =
    Number(process.env.NEXT_PUBLIC_POLL_CONTROL_PLANE_MS) || 15_000;

/** Long-lived data that changes infrequently */
export const POLL_SLOW_MS =
    Number(process.env.NEXT_PUBLIC_POLL_SLOW_MS) || 60_000;
