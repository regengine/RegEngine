'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Plus, ShieldCheck } from 'lucide-react';

// ---------------------------------------------------------------------------
// Required KDEs by CTE type — mirrors webhook_models.py REQUIRED_KDES_BY_CTE
// Source of truth: services/ingestion/app/webhook_models.py lines 64-104
// ---------------------------------------------------------------------------

const REQUIRED_KDES: Record<string, string[]> = {
  harvesting: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'harvest_date', 'location_name', 'reference_document',
  ],
  cooling: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'cooling_date', 'location_name', 'reference_document',
  ],
  initial_packing: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'packing_date', 'location_name', 'reference_document',
    'harvester_business_name',
  ],
  first_land_based_receiving: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'landing_date', 'receiving_location', 'reference_document',
  ],
  shipping: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'ship_date', 'ship_from_location', 'ship_to_location',
    'reference_document', 'tlc_source_reference',
  ],
  receiving: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'receive_date', 'receiving_location',
    'immediate_previous_source', 'reference_document', 'tlc_source_reference',
  ],
  transformation: [
    'traceability_lot_code', 'product_description', 'quantity',
    'unit_of_measure', 'transformation_date', 'location_name', 'reference_document',
  ],
};

// Friendly labels for field names
const FIELD_LABELS: Record<string, string> = {
  cte_type: 'CTE Type',
  traceability_lot_code: 'Traceability Lot Code',
  product_description: 'Product Description',
  quantity: 'Quantity',
  unit_of_measure: 'Unit of Measure',
  harvest_date: 'Harvest Date',
  cooling_date: 'Cooling Date',
  packing_date: 'Packing Date',
  landing_date: 'Landing Date',
  ship_date: 'Ship Date',
  receive_date: 'Receive Date',
  transformation_date: 'Transformation Date',
  location_name: 'Location Name',
  receiving_location: 'Receiving Location',
  ship_from_location: 'Ship From Location',
  ship_to_location: 'Ship To Location',
  reference_document: 'Reference Document (BOL/Invoice)',
  tlc_source_reference: 'TLC Source Reference',
  immediate_previous_source: 'Immediate Previous Source',
  harvester_business_name: 'Harvester Business Name',
  timestamp: 'Event Timestamp',
};

interface AddEventModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (values: Record<string, string>) => void;
  cteType: string;
  prefill: Record<string, string>;
}

export function AddEventModal({ open, onClose, onConfirm, cteType, prefill }: AddEventModalProps) {
  // Build field list: cte_type (locked) + required KDEs for this CTE type
  const requiredFields = REQUIRED_KDES[cteType] || ['traceability_lot_code', 'product_description', 'quantity', 'unit_of_measure'];
  const allFields = ['cte_type', ...requiredFields.filter((f) => f !== 'cte_type'), 'timestamp'];

  // Initialize form values from prefill
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = { cte_type: cteType };
    for (const field of allFields) {
      initial[field] = prefill[field] || '';
    }
    initial.cte_type = cteType; // Always locked
    return initial;
  });

  const [confirmed, setConfirmed] = useState(false);

  function handleChange(field: string, value: string) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  function handleSubmit() {
    if (!confirmed) return;
    onConfirm(values);
    onClose();
    // Reset for next open
    setConfirmed(false);
  }

  const isPrefilled = (field: string) => !!prefill[field];
  const fieldLabel = (field: string) => FIELD_LABELS[field] || field.replace(/_/g, ' ');

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="bg-[#1a1a2e] border-[var(--re-surface-border)] text-[var(--re-text-primary)] sm:max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[var(--re-text-primary)]">
            <Plus className="w-4 h-4 text-[var(--re-brand)]" />
            Add {cteType.replace(/_/g, ' ')} event
          </DialogTitle>
          <DialogDescription className="text-[var(--re-text-muted)]">
            Review and complete the pre-filled values. All fields marked with * are required by FSMA 204.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {allFields.map((field) => {
            const isLocked = field === 'cte_type';
            const isRequired = requiredFields.includes(field);
            const hasPrefill = isPrefilled(field);

            return (
              <div key={field} className="space-y-1">
                <label className="text-[0.65rem] font-medium text-[var(--re-text-secondary)] flex items-center gap-1">
                  {fieldLabel(field)}
                  {isRequired && <span className="text-re-danger">*</span>}
                  {hasPrefill && (
                    <span className="text-[0.55rem] text-re-brand font-normal ml-1">
                      (suggested)
                    </span>
                  )}
                </label>
                {isLocked ? (
                  <div className="px-3 py-2 bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] rounded-lg text-[0.75rem] text-[var(--re-text-muted)] font-mono">
                    {values[field]}
                  </div>
                ) : (
                  <input
                    type="text"
                    value={values[field] || ''}
                    onChange={(e) => handleChange(field, e.target.value)}
                    placeholder={`Enter ${fieldLabel(field).toLowerCase()}`}
                    className={`w-full bg-[var(--re-surface-base)] border rounded-lg px-3 py-2 text-[0.75rem] font-mono text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30 ${
                      hasPrefill
                        ? 'border-re-brand/30'
                        : 'border-[var(--re-surface-border)]'
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Compliance Guardrail */}
        <div className="border-t border-[var(--re-surface-border)] pt-3 mt-2">
          <label className="flex items-start gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              className="mt-0.5 rounded border-[var(--re-surface-border)] bg-[var(--re-surface-base)]"
            />
            <div className="space-y-0.5">
              <div className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-re-brand" />
                <span className="text-[0.7rem] font-semibold text-[var(--re-text-primary)]">
                  Physical Supply Chain Confirmation
                </span>
              </div>
              <span className="text-[0.6rem] text-[var(--re-text-muted)] leading-relaxed block">
                I confirm this event occurred in the physical supply chain. Pre-filled values are
                suggestions based on the traceability gap detected — I have verified them against
                actual records.
              </span>
            </div>
          </label>
        </div>

        <DialogFooter>
          <button
            onClick={onClose}
            className="px-4 py-2 text-[0.75rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!confirmed}
            className="px-4 py-2 bg-[var(--re-brand)] text-white rounded-lg text-[0.75rem] font-semibold hover:bg-[var(--re-brand-dark)] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            Add Event to Grid
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
