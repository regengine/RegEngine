/**
 * Resolution Recipes — maps rule failures + evidence → actionable fix options.
 *
 * Each recipe is a pure function: (error, rowIndex) → ResolutionOption[].
 * The frontend uses these to render interactive buttons in the FixItTooltip.
 */

import type { CellError, ResolutionOption } from './types';

// ---------------------------------------------------------------------------
// Stage → date field mapping (for temporal order recipes)
// ---------------------------------------------------------------------------

const STAGE_DATE_FIELD: Record<string, string> = {
  harvesting: 'harvest_date',
  cooling: 'cooling_date',
  initial_packing: 'packing_date',
  first_land_based_receiving: 'landing_date',
  transformation: 'transformation_date',
  shipping: 'ship_date',
  receiving: 'receive_date',
};

// ---------------------------------------------------------------------------
// Recipes by category
// ---------------------------------------------------------------------------

function getMassBalanceRecipes(error: CellError, rowIndex: number): ResolutionOption[] {
  const ev = error.evidence?.[0] as Record<string, unknown> | undefined;
  if (!ev) return [];

  const tlc = String(ev.tlc || '');
  const totalInput = Number(ev.total_input || 0);
  const totalOutput = Number(ev.total_output || 0);
  const units = (ev.units_seen as string[]) || [];
  const uom = units[0] || '';
  const deficit = Math.max(0, totalOutput - totalInput);

  const options: ResolutionOption[] = [];

  if (deficit > 0) {
    options.push({
      id: 'mb-add-receiving',
      label: 'Add a Receiving event',
      description: `Pre-fills ${deficit} ${uom} for TLC ${tlc}`,
      action: 'add_row',
      cteType: 'receiving',
      prefill: {
        cte_type: 'receiving',
        traceability_lot_code: tlc,
        quantity: String(deficit),
        unit_of_measure: uom,
      },
    });

    options.push({
      id: 'mb-add-transformation',
      label: 'Add a Transformation event',
      description: `If product was combined from another lot`,
      action: 'add_row',
      cteType: 'transformation',
      prefill: {
        cte_type: 'transformation',
        traceability_lot_code: tlc,
        quantity: String(deficit),
        unit_of_measure: uom,
      },
    });
  }

  options.push({
    id: 'mb-edit-quantity',
    label: 'Correct the shipping quantity',
    description: `Current output: ${totalOutput} ${uom}, max allowed: ${totalInput} ${uom}`,
    action: 'edit_cell',
    targetColumn: 'quantity',
    targetRow: rowIndex,
  });

  return options;
}

function getTemporalOrderRecipes(error: CellError, rowIndex: number): ResolutionOption[] {
  const ev = error.evidence?.[0] as Record<string, unknown> | undefined;
  if (!ev) return [];

  const laterStage = String(ev.later_stage || ev.earlier_stage || '');
  const earlierStage = String(ev.earlier_stage || ev.later_stage || '');

  const laterDateField = STAGE_DATE_FIELD[laterStage] || 'timestamp';
  const earlierDateField = STAGE_DATE_FIELD[earlierStage] || 'timestamp';

  return [
    {
      id: 'to-edit-later',
      label: `Correct the ${laterStage} date`,
      description: `This event's timestamp is earlier than expected`,
      action: 'edit_cell',
      targetColumn: laterDateField,
      targetRow: rowIndex,
    },
    {
      id: 'to-edit-earlier',
      label: `Correct the ${earlierStage} date`,
      description: `The ${earlierStage} event may have the wrong timestamp`,
      action: 'edit_cell',
      targetColumn: earlierDateField,
      targetRow: rowIndex,
    },
  ];
}

function getIdentityRecipes(error: CellError, rowIndex: number): ResolutionOption[] {
  const ev = error.evidence?.[0] as Record<string, unknown> | undefined;
  const otherProduct = ev ? String(ev.product || '') : '';
  const currentProduct = ev ? String(ev.current || '') : '';

  const options: ResolutionOption[] = [];

  if (otherProduct && currentProduct && otherProduct !== currentProduct) {
    options.push({
      id: 'id-standardize',
      label: `Standardize all to "${otherProduct}"`,
      description: `Apply the same product name across all events for this TLC`,
      action: 'mass_fill',
      fillColumn: 'product_description',
      fillValue: otherProduct,
    });
  }

  options.push({
    id: 'id-edit-product',
    label: "Edit this event's product",
    description: `Change the product description for this row`,
    action: 'edit_cell',
    targetColumn: 'product_description',
    targetRow: rowIndex,
  });

  return options;
}

function getKdePresenceRecipes(error: CellError, rowIndex: number): ResolutionOption[] {
  // Extract the field name from the rule title "Missing KDE: field_name"
  const match = error.ruleTitle.match(/Missing KDE: (.+)/);
  const field = match ? match[1] : '';

  return [{
    id: `kde-fill-${field}`,
    label: `Fill ${field}`,
    description: 'Click to start editing this cell',
    action: 'edit_cell',
    targetColumn: field,
    targetRow: rowIndex,
  }];
}

// ---------------------------------------------------------------------------
// Master dispatcher
// ---------------------------------------------------------------------------

export function getResolutionOptions(error: CellError, rowIndex: number): ResolutionOption[] {
  switch (error.category) {
    case 'quantity_consistency':
      return getMassBalanceRecipes(error, rowIndex);
    case 'temporal_ordering':
      return getTemporalOrderRecipes(error, rowIndex);
    case 'lot_linkage':
      if (error.ruleTitle.includes('Identity')) {
        return getIdentityRecipes(error, rowIndex);
      }
      return [];
    case 'kde_presence':
      return getKdePresenceRecipes(error, rowIndex);
    default:
      return [];
  }
}
