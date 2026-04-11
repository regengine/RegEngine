'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  AlertTriangle, ArrowRight, CheckCircle2, FileWarning, Package,
  Search, Shield, ShieldAlert, Upload, XCircle,
} from 'lucide-react';

/* ------------------------------------------------------------------ */
/*  RAW DATA — the messy CSV that a real supplier might send           */
/* ------------------------------------------------------------------ */

const RAW_CSV_LINES = [
  { line: 'lot_code,product,qty,unit,location,date,supplier,cooling_date,reference_doc', isHeader: true },
  { line: 'R-2026-0312,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12,Valley Fresh Farms LLC,,INV-001', problems: ['Missing cooling_date'] },
  { line: 'R-2026-0312,Romaine Lettuce,2000,lbs,valley fresh farms,2026-03-12,Valley Fresh,,INV-001', problems: ['Duplicate lot code', 'Inconsistent supplier name', 'Inconsistent location casing'] },
  { line: 'R-2026-0313,Baby Spinach,500,lbs,GreenLeaf Co,2026-03-13,GreenLeaf Co.,2026-03-13,', problems: ['Missing reference_document'] },
  { line: 'R-2026-0314,Spring Mix,300,bushels,FreshCo DC,2026-03-14,FreshCo,2026-03-14,PO-992', problems: ['Invalid unit_of_measure'] },
  { line: 'R-2026-0315,Romaine Hearts,1200,cases,Valley Fresh,2026-03-15,Valley Fresh Farms,2026-03-15,INV-003' },
];

/* ------------------------------------------------------------------ */
/*  PIPELINE STEPS                                                     */
/* ------------------------------------------------------------------ */

interface PipelineStep {
  id: string;
  label: string;
  icon: typeof Upload;
  description: string;
}

const STEPS: PipelineStep[] = [
  { id: 'ingest', label: 'Ingest', icon: Upload, description: 'Raw CSV uploaded' },
  { id: 'normalize', label: 'Normalize', icon: Search, description: 'Fields mapped to FSMA schema' },
  { id: 'validate', label: 'Validate', icon: Shield, description: '25 rules checked per event' },
  { id: 'flag', label: 'Flag', icon: FileWarning, description: 'Violations & exceptions created' },
  { id: 'block', label: 'Block / Pass', icon: ShieldAlert, description: 'Blocking defects enforced' },
  { id: 'package', label: 'Package', icon: Package, description: 'SHA-256 hashed FDA export' },
];

/* ------------------------------------------------------------------ */
/*  VALIDATION RESULTS                                                 */
/* ------------------------------------------------------------------ */

interface ValidationResult {
  lot: string;
  product: string;
  status: 'pass' | 'fail' | 'warning';
  issues: string[];
}

const VALIDATION_RESULTS: ValidationResult[] = [
  { lot: 'R-2026-0312', product: 'Romaine Lettuce', status: 'fail', issues: ['Missing required KDE: cooling_date', 'Duplicate lot code — identity conflict'] },
  { lot: 'R-2026-0313', product: 'Baby Spinach', status: 'fail', issues: ['Missing required KDE: reference_document'] },
  { lot: 'R-2026-0314', product: 'Spring Mix', status: 'fail', issues: ['Invalid unit_of_measure: "bushels" not in FSMA standard units'] },
  { lot: 'R-2026-0315', product: 'Romaine Hearts', status: 'pass', issues: [] },
];

const BLOCKING_DEFECTS = [
  'Missing required KDE: cooling_date (R-2026-0312)',
  'Unresolved identity conflict: "Valley Fresh Farms LLC" vs "Valley Fresh" (R-2026-0312)',
  'Missing required KDE: reference_document (R-2026-0313)',
  'Invalid unit_of_measure: "bushels" (R-2026-0314)',
];

/* ------------------------------------------------------------------ */
/*  COMPONENT                                                          */
/* ------------------------------------------------------------------ */

export function DataTransformDemo() {
  const [activeStep, setActiveStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const advanceStep = useCallback(() => {
    setActiveStep((prev) => {
      if (prev >= STEPS.length - 1) {
        setIsPlaying(false);
        return prev;
      }
      return prev + 1;
    });
  }, []);

  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(advanceStep, 2000);
    return () => clearInterval(timer);
  }, [isPlaying, advanceStep]);

  function handlePlay() {
    setActiveStep(0);
    setIsPlaying(true);
  }

  const showRaw = activeStep <= 1;
  const showValidation = activeStep >= 2 && activeStep <= 4;
  const showPackage = activeStep >= 5;
  const isBlocked = activeStep === 4;

  return (
    <div className="w-full">
      {/* Step Indicator */}
      <div className="flex items-center justify-between mb-6 sm:mb-8 overflow-x-auto pb-2">
        {STEPS.map((step, i) => {
          const isActive = i === activeStep;
          const isDone = i < activeStep;
          const StepIcon = step.icon;
          return (
            <div key={step.id} className="flex items-center flex-shrink-0">
              <button
                onClick={() => { setActiveStep(i); setIsPlaying(false); }}
                className={`flex flex-col items-center gap-1.5 px-2 sm:px-3 py-2 rounded-lg transition-all duration-300 cursor-pointer ${
                  isActive ? 'bg-[var(--re-brand)]/10' : ''
                }`}
              >
                <div className={`w-8 h-8 sm:w-9 sm:h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
                  isDone ? 'bg-[var(--re-brand)] text-white' :
                  isActive ? 'bg-[var(--re-brand)] text-white ring-2 ring-[var(--re-brand)]/30 ring-offset-2 ring-offset-[var(--re-surface-base)]' :
                  'bg-[var(--re-surface-elevated)] text-[var(--re-text-disabled)] border border-[var(--re-surface-border)]'
                }`}>
                  {isDone ? <CheckCircle2 className="w-4 h-4" /> : <StepIcon className="w-4 h-4" />}
                </div>
                <span className={`text-[0.6rem] sm:text-[0.65rem] font-medium whitespace-nowrap transition-colors ${
                  isActive || isDone ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-disabled)]'
                }`}>
                  {step.label}
                </span>
              </button>
              {i < STEPS.length - 1 && (
                <div className={`w-4 sm:w-8 h-px transition-colors duration-300 ${
                  isDone ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-border)]'
                }`} />
              )}
            </div>
          );
        })}
      </div>

      {/* Two-Panel View */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5">

        {/* Left Panel — Raw Input */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden">
          <div className="px-4 py-2.5 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-red-400" />
              <span className="font-mono text-[0.65rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                INCOMING: supplier_upload.csv
              </span>
            </div>
            <span className="text-[0.6rem] text-[var(--re-text-disabled)]">6 rows, 4 problems</span>
          </div>
          <div className="p-3 sm:p-4 overflow-x-auto">
            <div className="font-mono text-[0.65rem] sm:text-[0.7rem] leading-relaxed space-y-1 min-w-[500px]">
              {RAW_CSV_LINES.map((row, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="text-[var(--re-text-disabled)] w-4 text-right flex-shrink-0 select-none">{i + 1}</span>
                  <span className={`flex-1 ${
                    row.isHeader ? 'text-[var(--re-text-muted)]' :
                    row.problems ? 'text-[var(--re-text-primary)]' :
                    'text-[var(--re-text-primary)]'
                  }`}>
                    {row.line}
                  </span>
                  {row.problems && activeStep >= 1 && (
                    <span className="flex items-center gap-1 flex-shrink-0">
                      {row.problems.map((p, j) => (
                        <span key={j} className="text-[0.55rem] bg-re-danger-muted0/10 text-re-danger border border-re-danger/20 px-1.5 py-0.5 rounded whitespace-nowrap">
                          {p}
                        </span>
                      ))}
                    </span>
                  )}
                  {!row.problems && !row.isHeader && activeStep >= 1 && (
                    <span className="text-[0.55rem] bg-re-brand-muted text-re-brand border border-re-brand/20 px-1.5 py-0.5 rounded flex-shrink-0">
                      Clean
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Panel — Output */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden">
          <div className="px-4 py-2.5 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                showPackage ? 'bg-amber-400' : showValidation ? 'bg-amber-400' : 'bg-blue-400'
              }`} />
              <span className="font-mono text-[0.65rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                {showPackage ? 'FDA RESPONSE PACKAGE' : showValidation ? 'VALIDATION RESULTS' : 'REGENGINE OUTPUT'}
              </span>
            </div>
          </div>
          <div className="p-3 sm:p-4">

            {/* Pre-validation: Normalized fields */}
            {showRaw && (
              <div className="space-y-3">
                <p className="text-[0.8rem] text-[var(--re-text-muted)] mb-3">
                  {activeStep === 0
                    ? 'Waiting for data... Click "Run Pipeline" or step through manually.'
                    : 'Fields mapped to FSMA 204 CTE/KDE schema. Problems highlighted.'}
                </p>
                {activeStep >= 1 && (
                  <div className="space-y-2">
                    {[
                      { field: 'lot_code → traceability_lot_code', status: 'mapped' },
                      { field: 'supplier → source_facility_reference', status: 'mapped' },
                      { field: 'cooling_date → kdes.cooling_date', status: 'missing in 1 row' },
                      { field: 'reference_doc → kdes.reference_document', status: 'missing in 1 row' },
                    ].map((m) => (
                      <div key={m.field} className="flex items-center justify-between text-[0.7rem]">
                        <span className="font-mono text-[var(--re-text-secondary)]">{m.field}</span>
                        <span className={`text-[0.6rem] px-1.5 py-0.5 rounded ${
                          m.status === 'mapped'
                            ? 'bg-re-brand-muted text-re-brand border border-re-brand/20'
                            : 'bg-re-warning-muted0/10 text-re-warning border border-re-warning/20'
                        }`}>{m.status}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Validation results */}
            {showValidation && (
              <div className="space-y-3">
                {VALIDATION_RESULTS.map((r) => (
                  <div key={r.lot} className={`rounded-lg border p-3 ${
                    r.status === 'pass'
                      ? 'border-re-brand/20 bg-re-brand/5'
                      : 'border-re-danger/20 bg-re-danger-muted0/5'
                  }`}>
                    <div className="flex items-center gap-2 mb-1">
                      {r.status === 'pass'
                        ? <CheckCircle2 className="w-3.5 h-3.5 text-re-brand" />
                        : <XCircle className="w-3.5 h-3.5 text-re-danger" />}
                      <span className="font-mono text-[0.7rem] font-medium text-[var(--re-text-primary)]">{r.lot}</span>
                      <span className="text-[0.65rem] text-[var(--re-text-muted)]">{r.product}</span>
                    </div>
                    {r.issues.length > 0 && (
                      <ul className="ml-6 space-y-0.5">
                        {r.issues.map((issue, j) => (
                          <li key={j} className="text-[0.65rem] text-re-danger">{issue}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}

                {/* Blocking banner at step 4 */}
                {isBlocked && (
                  <div className="rounded-lg border-2 border-re-danger/30 bg-re-danger-muted0/10 p-4 mt-3">
                    <div className="flex items-center gap-2 mb-2">
                      <ShieldAlert className="w-5 h-5 text-re-danger" />
                      <span className="text-[0.8rem] font-semibold text-re-danger">
                        SUBMISSION BLOCKED — {BLOCKING_DEFECTS.length} blocking defects
                      </span>
                    </div>
                    <p className="text-[0.7rem] text-[var(--re-text-muted)] mb-2">
                      You cannot submit this package to the FDA until all blocking defects are resolved or waived.
                    </p>
                    <ul className="space-y-1">
                      {BLOCKING_DEFECTS.map((d, i) => (
                        <li key={i} className="text-[0.65rem] text-re-danger flex items-start gap-1.5">
                          <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                          {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Package output */}
            {showPackage && (
              <div className="space-y-3">
                <div className="rounded-lg border border-re-warning/20 bg-re-warning-muted0/5 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-5 h-5 text-re-warning" />
                    <span className="text-[0.8rem] font-semibold text-re-warning">
                      PACKAGE ASSEMBLED — 3 of 4 records blocked
                    </span>
                  </div>
                  <p className="text-[0.7rem] text-[var(--re-text-muted)] mb-3">
                    Only 1 of 4 records passed validation. Resolve blocking defects to include remaining records.
                  </p>
                  <div className="space-y-2 text-[0.7rem]">
                    {[
                      { label: 'Records included', value: '1 of 4', color: 'amber' },
                      { label: 'Blocking defects', value: '4 unresolved', color: 'red' },
                      { label: 'Package hash', value: 'sha256:a7c3e9...f2d1b8', color: 'brand' },
                      { label: 'Format', value: 'FDA 21 CFR 1.1455', color: 'brand' },
                    ].map((row) => (
                      <div key={row.label} className="flex items-center justify-between">
                        <span className="text-[var(--re-text-secondary)]">{row.label}</span>
                        <span className={`font-mono font-medium ${
                          row.color === 'red' ? 'text-re-danger' :
                          row.color === 'amber' ? 'text-re-warning' :
                          'text-[var(--re-brand)]'
                        }`}>{row.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <p className="text-[0.7rem] text-[var(--re-text-disabled)] italic">
                  This is what happens when supplier data is messy. RegEngine doesn&apos;t hide the problems — it makes them visible and blocks bad submissions.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-3 mt-6">
        <button
          onClick={handlePlay}
          className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-5 py-2.5 rounded-lg text-[0.85rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)] hover:-translate-y-0.5 hover:shadow-[0_4px_16px_rgba(16,185,129,0.3)]"
        >
          {isPlaying ? 'Restart Pipeline' : 'Run Pipeline'}
          <ArrowRight className="w-4 h-4" />
        </button>
        <span className="text-[0.7rem] text-[var(--re-text-disabled)]">
          or click any step above
        </span>
      </div>
    </div>
  );
}
