import type { CteTypeSuggestion } from '@/types/api';

/**
 * The seven FDA-defined critical tracking events POST /api/v1/ingest/csv
 * accepts as `cte_type`, with display labels.
 */
export const CTE_LABELS: Readonly<Record<string, string>> = {
  harvesting: 'Harvesting',
  cooling: 'Cooling',
  initial_packing: 'Initial Packing',
  first_land_based_receiving: 'First Land-Based Receiving',
  shipping: 'Shipping',
  receiving: 'Receiving',
  transformation: 'Transformation',
};

export interface ActionableCteSuggestion {
  cteType: string;
  label: string;
  /** 0..1, or null when the server sent none. */
  confidence: number | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

/**
 * A `cte_type_suggestion` the uploader can act on, or null.
 *
 * Actionable means it names one of the seven CTEs, was not already applied
 * by the server, and is not in the reject band. Anything else (mixed or
 * unclear files, provider failures, unknown values) is not offered.
 */
export function actionableCteSuggestion(value: unknown): ActionableCteSuggestion | null {
  const suggestion = asRecord(value) as Partial<CteTypeSuggestion>;
  const cteType = suggestion.cte_type;
  if (typeof cteType !== 'string' || !Object.hasOwn(CTE_LABELS, cteType)) return null;
  if (suggestion.applied === true || suggestion.band === 'reject') return null;
  const confidence = typeof suggestion.confidence === 'number'
    && Number.isFinite(suggestion.confidence)
    && suggestion.confidence >= 0
    && suggestion.confidence <= 1
    ? suggestion.confidence
    : null;
  return { cteType, label: CTE_LABELS[cteType], confidence };
}

/**
 * Jev's suggested CTE carried by a CSV upload the server rejected.
 *
 * The route answers a file whose rows have no CTE with a 400 ("No valid rows
 * found") whose detail may include `cte_type_suggestion` (see
 * CteTypeSuggestionResult in services/ingestion/app/webhook_models.py).
 * `apiClient.ingestFile` keeps the original response on the error it throws.
 */
export function cteSuggestionFromUploadError(error: unknown): ActionableCteSuggestion | null {
  const detail = asRecord(asRecord(asRecord(error).response).data).detail;
  return actionableCteSuggestion(asRecord(detail).cte_type_suggestion);
}
