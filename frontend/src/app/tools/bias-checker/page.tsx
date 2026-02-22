"use client";

import { useState, useCallback } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Shield,
  BarChart3,
  Scale,
  ArrowRight,
  Plus,
  Trash2,
  RotateCcw,
  Download,
  Info,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────
   TYPES
   ───────────────────────────────────────────────────────────── */

interface DemographicGroup {
  id: string;
  name: string;
  approved: number;
  denied: number;
}

interface BiasResult {
  groupName: string;
  approvalRate: number;
  dir: number;
  passes80: boolean;
  severity: 'pass' | 'warning' | 'fail';
}

interface AnalysisResult {
  referenceGroup: string;
  referenceRate: number;
  results: BiasResult[];
  overallPass: boolean;
  applicableRegs: RegCitation[];
  totalApplicants: number;
  timestamp: string;
}

interface RegCitation {
  id: string;
  regulation: string;
  citation: string;
  requirement: string;
  relevance: string;
}

/* ─────────────────────────────────────────────────────────────
   CONSTANTS
   ───────────────────────────────────────────────────────────── */

const APPLICABLE_REGULATIONS: RegCitation[] = [
  {
    id: 'ecoa-prohibited',
    regulation: 'ECOA — Prohibited Basis Discrimination',
    citation: '12 CFR 1002.4(a)',
    requirement: 'Creditor shall not discriminate against any applicant on a prohibited basis (race, color, religion, national origin, sex, marital status, age).',
    relevance: 'Disparate Impact Ratio below 0.80 may indicate discriminatory outcomes requiring investigation.',
  },
  {
    id: 'ecoa-adverse',
    regulation: 'ECOA — Adverse Action Notice',
    citation: '12 CFR 1002.9(a)(1)',
    requirement: 'Must provide adverse action notice within 30 days with specific reasons for denial.',
    relevance: 'High denial rates in specific groups must be accompanied by individualized reason codes.',
  },
  {
    id: 'occ-bias',
    regulation: 'OCC AI/ML Bias Testing',
    citation: 'OCC Bulletin 2023-XX §3',
    requirement: 'Banks must test AI/ML models for bias and discriminatory outcomes, particularly for consumer-facing applications.',
    relevance: 'DIR analysis is a standard method for satisfying this requirement.',
  },
  {
    id: 'sr-11-7',
    regulation: 'SR 11-7 — Ongoing Monitoring',
    citation: 'SR 11-7 Section III.C',
    requirement: 'Models should be subject to ongoing monitoring to determine whether they are performing as intended.',
    relevance: 'Bias monitoring is a component of model risk management under SR 11-7.',
  },
  {
    id: 'fcra-accuracy',
    regulation: 'FCRA — Accuracy Requirement',
    citation: '15 U.S.C. § 1681e(b)',
    requirement: 'Reasonable procedures to assure maximum possible accuracy of consumer report information.',
    relevance: 'Inaccurate data can introduce bias — accuracy is a prerequisite for fair lending.',
  },
];

const DEMO_GROUPS: DemographicGroup[] = [
  { id: '1', name: 'White', approved: 7200, denied: 2800 },
  { id: '2', name: 'Black', approved: 5800, denied: 4200 },
  { id: '3', name: 'Hispanic', approved: 6100, denied: 3900 },
  { id: '4', name: 'Asian', approved: 7400, denied: 2600 },
  { id: '5', name: 'Native American', approved: 5500, denied: 4500 },
];

const PRESET_SCENARIOS = [
  {
    name: 'Credit Card Approvals',
    description: 'Consumer credit card application outcomes by race/ethnicity',
    groups: DEMO_GROUPS,
  },
  {
    name: 'Auto Loan Pricing',
    description: 'Auto loan approval rates showing potential markup disparities',
    groups: [
      { id: '1', name: 'White', approved: 8100, denied: 1900 },
      { id: '2', name: 'Black', approved: 6300, denied: 3700 },
      { id: '3', name: 'Hispanic', approved: 6800, denied: 3200 },
      { id: '4', name: 'Asian', approved: 8300, denied: 1700 },
    ],
  },
  {
    name: 'Mortgage Lending',
    description: 'Home mortgage approval decisions across demographic groups',
    groups: [
      { id: '1', name: 'White', approved: 6800, denied: 3200 },
      { id: '2', name: 'Black', approved: 4900, denied: 5100 },
      { id: '3', name: 'Hispanic', approved: 5300, denied: 4700 },
      { id: '4', name: 'Asian', approved: 7100, denied: 2900 },
      { id: '5', name: 'Native Hawaiian/Pacific Islander', approved: 5100, denied: 4900 },
    ],
  },
];

let nextId = 10;

/* ─────────────────────────────────────────────────────────────
   COMPONENT
   ───────────────────────────────────────────────────────────── */

export default function BiasCheckerPage() {
  const freshGroups = () => DEMO_GROUPS.map(g => ({ ...g }));
  const [groups, setGroups] = useState<DemographicGroup[]>(freshGroups);
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [activePreset, setActivePreset] = useState<number>(0);
  const [inputKey, setInputKey] = useState(0); // Forces React to remount inputs on reset

  /* ── Handlers ── */

  const addGroup = useCallback(() => {
    setGroups(prev => [...prev, {
      id: String(nextId++),
      name: '',
      approved: 0,
      denied: 0,
    }]);
  }, []);

  const removeGroup = useCallback((id: string) => {
    setGroups(prev => prev.filter(g => g.id !== id));
  }, []);

  const updateGroup = useCallback((id: string, field: keyof DemographicGroup, value: string | number) => {
    setGroups(prev => prev.map(g =>
      g.id === id ? { ...g, [field]: field === 'name' ? value : Math.max(0, Number(value)) } : g
    ));
  }, []);

  const loadPreset = useCallback((index: number) => {
    setActivePreset(index);
    setGroups(PRESET_SCENARIOS[index].groups.map(g => ({ ...g })));
    setAnalysis(null);
    setInputKey(k => k + 1);
  }, []);

  const reset = useCallback(() => {
    setGroups(freshGroups());
    setAnalysis(null);
    setActivePreset(0);
    setInputKey(k => k + 1);
  }, []);

  /* ── Analysis Engine ── */

  const runAnalysis = useCallback(() => {
    const validGroups = groups.filter(g => g.name && (g.approved + g.denied) > 0);
    if (validGroups.length < 2) return;

    // Calculate approval rates
    const rates = validGroups.map(g => ({
      ...g,
      total: g.approved + g.denied,
      rate: g.approved / (g.approved + g.denied),
    }));

    // Reference group = highest approval rate (most favored)
    const reference = rates.reduce((best, g) => g.rate > best.rate ? g : best, rates[0]);

    const results: BiasResult[] = rates.map(g => {
      const dir = reference.rate > 0 ? g.rate / reference.rate : 0;
      const passes80 = dir >= 0.80;
      let severity: 'pass' | 'warning' | 'fail' = 'pass';
      if (dir < 0.80) severity = 'fail';
      else if (dir < 0.90) severity = 'warning';

      return {
        groupName: g.name,
        approvalRate: Math.round(g.rate * 10000) / 100,
        dir: Math.round(dir * 1000) / 1000,
        passes80,
        severity,
      };
    });

    const overallPass = results.every(r => r.passes80);

    setAnalysis({
      referenceGroup: reference.name,
      referenceRate: Math.round(reference.rate * 10000) / 100,
      results,
      overallPass,
      applicableRegs: APPLICABLE_REGULATIONS,
      totalApplicants: rates.reduce((sum, g) => sum + g.total, 0),
      timestamp: new Date().toISOString(),
    });
  }, [groups]);

  /* ── Render ── */

  return (
    <>
      <style jsx global>{`
        :root {
          --bc-bg: #09090b;
          --bc-surface: #0f0f13;
          --bc-elevated: #16161d;
          --bc-border: rgba(255,255,255,0.08);
          --bc-border-strong: rgba(255,255,255,0.15);
          --bc-text: #e4e4e7;
          --bc-text-muted: #71717a;
          --bc-text-dim: #52525b;
          --bc-accent: #10b981;
          --bc-accent-hover: #34d399;
          --bc-fail: #ef4444;
          --bc-fail-bg: rgba(239,68,68,0.1);
          --bc-warn: #f59e0b;
          --bc-warn-bg: rgba(245,158,11,0.1);
          --bc-pass: #10b981;
          --bc-pass-bg: rgba(16,185,129,0.1);
          --bc-blue: #3b82f6;
          --bc-blue-bg: rgba(59,130,246,0.1);
        }

        .bc-page {
          min-height: 100vh;
          background: var(--bc-bg);
          color: var(--bc-text);
          font-family: 'Instrument Sans', 'Inter', system-ui, sans-serif;
        }

        .bc-container {
          max-width: 1100px;
          margin: 0 auto;
          padding: 0 1.5rem;
        }

        /* Header */
        .bc-header {
          padding: 2rem 0;
          border-bottom: 1px solid var(--bc-border);
        }
        .bc-breadcrumb {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8rem;
          color: var(--bc-text-muted);
          margin-bottom: 1.5rem;
        }
        .bc-breadcrumb a {
          color: var(--bc-text-muted);
          text-decoration: none;
        }
        .bc-breadcrumb a:hover {
          color: var(--bc-accent);
        }
        .bc-title-row {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 2rem;
        }
        .bc-badge-free {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          background: var(--bc-pass-bg);
          color: var(--bc-pass);
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 0.25rem 0.6rem;
          border-radius: 4px;
          border: 1px solid rgba(16,185,129,0.2);
          margin-bottom: 0.75rem;
        }
        .bc-page h1 {
          font-size: 2rem;
          font-weight: 700;
          line-height: 1.15;
          margin: 0 0 0.75rem;
          letter-spacing: -0.025em;
        }
        .bc-subtitle {
          font-size: 1.05rem;
          color: var(--bc-text-muted);
          line-height: 1.6;
          max-width: 600px;
        }

        /* Presets */
        .bc-presets {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          margin: 1.5rem 0;
        }
        .bc-preset-btn {
          background: var(--bc-surface);
          border: 1px solid var(--bc-border);
          color: var(--bc-text-muted);
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.15s;
        }
        .bc-preset-btn:hover {
          border-color: var(--bc-border-strong);
          color: var(--bc-text);
        }
        .bc-preset-btn.active {
          border-color: var(--bc-accent);
          color: var(--bc-accent);
          background: rgba(16,185,129,0.05);
        }

        /* Input Table */
        .bc-input-section {
          margin: 2rem 0;
        }
        .bc-section-label {
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--bc-text-dim);
          margin-bottom: 1rem;
        }
        .bc-table {
          width: 100%;
          border-collapse: collapse;
        }
        .bc-table th {
          text-align: left;
          font-size: 0.75rem;
          font-weight: 500;
          color: var(--bc-text-muted);
          padding: 0.75rem 1rem;
          border-bottom: 1px solid var(--bc-border);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .bc-table td {
          padding: 0.5rem 1rem;
          border-bottom: 1px solid var(--bc-border);
          vertical-align: middle;
        }
        .bc-input {
          background: var(--bc-surface);
          border: 1px solid var(--bc-border);
          color: var(--bc-text);
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          font-size: 0.9rem;
          width: 100%;
          font-family: 'JetBrains Mono', monospace;
          transition: border-color 0.15s;
        }
        .bc-input:focus {
          outline: none;
          border-color: var(--bc-accent);
        }
        .bc-input-name {
          font-family: 'Instrument Sans', system-ui, sans-serif;
        }
        .bc-rate-preview {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          color: var(--bc-text-muted);
          min-width: 60px;
          text-align: right;
        }
        .bc-remove-btn {
          background: none;
          border: none;
          color: var(--bc-text-dim);
          cursor: pointer;
          padding: 0.35rem;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s;
        }
        .bc-remove-btn:hover {
          background: var(--bc-fail-bg);
          color: var(--bc-fail);
        }

        /* Action Buttons */
        .bc-actions {
          display: flex;
          gap: 0.75rem;
          margin: 1.5rem 0 2rem;
          flex-wrap: wrap;
        }
        .bc-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.6rem 1.2rem;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s;
          border: 1px solid transparent;
        }
        .bc-btn-primary {
          background: var(--bc-accent);
          color: #000;
          border-color: var(--bc-accent);
        }
        .bc-btn-primary:hover {
          background: var(--bc-accent-hover);
          border-color: var(--bc-accent-hover);
        }
        .bc-btn-primary:disabled {
          opacity: 0.4;
          cursor: not-allowed;
        }
        .bc-btn-secondary {
          background: var(--bc-surface);
          color: var(--bc-text-muted);
          border-color: var(--bc-border);
        }
        .bc-btn-secondary:hover {
          border-color: var(--bc-border-strong);
          color: var(--bc-text);
        }

        /* Results */
        .bc-results {
          margin: 2rem 0 3rem;
        }
        .bc-overall {
          padding: 1.5rem;
          border-radius: 10px;
          border: 1px solid var(--bc-border);
          margin-bottom: 1.5rem;
          display: flex;
          align-items: center;
          gap: 1.25rem;
        }
        .bc-overall-pass {
          background: var(--bc-pass-bg);
          border-color: rgba(16,185,129,0.25);
        }
        .bc-overall-fail {
          background: var(--bc-fail-bg);
          border-color: rgba(239,68,68,0.25);
        }
        .bc-overall-icon {
          font-size: 2rem;
          flex-shrink: 0;
        }
        .bc-overall h3 {
          font-size: 1.1rem;
          margin: 0 0 0.25rem;
          font-weight: 600;
        }
        .bc-overall p {
          font-size: 0.85rem;
          color: var(--bc-text-muted);
          margin: 0;
          line-height: 1.5;
        }

        /* Result Cards */
        .bc-result-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
          gap: 0.75rem;
          margin-bottom: 2rem;
        }
        .bc-result-card {
          background: var(--bc-surface);
          border: 1px solid var(--bc-border);
          border-radius: 8px;
          padding: 1.25rem;
          transition: border-color 0.15s;
        }
        .bc-result-card:hover {
          border-color: var(--bc-border-strong);
        }
        .bc-result-card.fail {
          border-left: 3px solid var(--bc-fail);
        }
        .bc-result-card.warning {
          border-left: 3px solid var(--bc-warn);
        }
        .bc-result-card.pass {
          border-left: 3px solid var(--bc-pass);
        }
        .bc-result-name {
          font-size: 0.85rem;
          font-weight: 600;
          margin-bottom: 0.75rem;
        }
        .bc-result-metric {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-bottom: 0.35rem;
        }
        .bc-result-label {
          font-size: 0.75rem;
          color: var(--bc-text-muted);
        }
        .bc-result-value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          font-weight: 600;
        }
        .bc-result-dir {
          font-size: 1.4rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
          margin: 0.5rem 0;
        }
        .bc-result-badge {
          display: inline-flex;
          align-items: center;
          gap: 0.3rem;
          font-size: 0.7rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
        }
        .bc-badge-pass {
          background: var(--bc-pass-bg);
          color: var(--bc-pass);
        }
        .bc-badge-warn {
          background: var(--bc-warn-bg);
          color: var(--bc-warn);
        }
        .bc-badge-fail {
          background: var(--bc-fail-bg);
          color: var(--bc-fail);
        }

        /* Regulation Cards */
        .bc-regs {
          margin: 2rem 0;
        }
        .bc-reg-card {
          background: var(--bc-surface);
          border: 1px solid var(--bc-border);
          border-radius: 8px;
          padding: 1.25rem;
          margin-bottom: 0.75rem;
          transition: border-color 0.15s;
        }
        .bc-reg-card:hover {
          border-color: var(--bc-border-strong);
        }
        .bc-reg-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 0.5rem;
        }
        .bc-reg-name {
          font-size: 0.9rem;
          font-weight: 600;
        }
        .bc-reg-cite {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          color: var(--bc-accent);
          background: rgba(16,185,129,0.08);
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .bc-reg-req {
          font-size: 0.8rem;
          color: var(--bc-text-muted);
          line-height: 1.5;
          margin-bottom: 0.5rem;
        }
        .bc-reg-relevance {
          font-size: 0.78rem;
          color: var(--bc-text-dim);
          line-height: 1.5;
          font-style: italic;
        }

        /* Methodology */
        .bc-method {
          background: var(--bc-surface);
          border: 1px solid var(--bc-border);
          border-radius: 10px;
          padding: 1.5rem;
          margin: 2rem 0;
        }
        .bc-method h3 {
          font-size: 0.95rem;
          font-weight: 600;
          margin: 0 0 0.75rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .bc-method p {
          font-size: 0.85rem;
          color: var(--bc-text-muted);
          line-height: 1.65;
          margin: 0 0 0.75rem;
        }
        .bc-formula {
          background: var(--bc-elevated);
          border: 1px solid var(--bc-border);
          border-radius: 6px;
          padding: 1rem 1.25rem;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.9rem;
          color: var(--bc-accent);
          text-align: center;
          margin: 1rem 0;
        }

        /* CTA */
        .bc-cta {
          background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.08));
          border: 1px solid rgba(16,185,129,0.2);
          border-radius: 10px;
          padding: 2rem;
          text-align: center;
          margin: 2.5rem 0;
        }
        .bc-cta h3 {
          font-size: 1.2rem;
          font-weight: 700;
          margin: 0 0 0.5rem;
        }
        .bc-cta p {
          font-size: 0.9rem;
          color: var(--bc-text-muted);
          margin: 0 0 1.25rem;
          line-height: 1.5;
        }
        .bc-cta-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          background: var(--bc-accent);
          color: #000;
          font-weight: 600;
          font-size: 0.9rem;
          padding: 0.75rem 1.5rem;
          border-radius: 8px;
          text-decoration: none;
          transition: background 0.15s;
        }
        .bc-cta-btn:hover {
          background: var(--bc-accent-hover);
        }

        /* Footer */
        .bc-footer {
          border-top: 1px solid var(--bc-border);
          padding: 2rem 0;
          margin-top: 3rem;
        }
        .bc-footer-text {
          font-size: 0.78rem;
          color: var(--bc-text-dim);
          line-height: 1.65;
          max-width: 700px;
        }

        @media (max-width: 768px) {
          .bc-page h1 { font-size: 1.5rem; }
          .bc-title-row { flex-direction: column; gap: 1rem; }
          .bc-result-grid { grid-template-columns: 1fr; }
          .bc-overall { flex-direction: column; text-align: center; }
          .bc-reg-header { flex-direction: column; }
        }
      `}</style>

      <div className="bc-page">
        {/* Header */}
        <header className="bc-header">
          <div className="bc-container">
            <div className="bc-breadcrumb">
              <Link href="/">RegEngine</Link>
              <span>/</span>
              <Link href="/verticals/finance">Finance</Link>
              <span>/</span>
              <span>Bias Checker</span>
            </div>

            <div className="bc-title-row">
              <div>
                <div className="bc-badge-free">
                  <Shield size={12} />
                  Free Tool
                </div>
                <h1>AI Model Bias Checker</h1>
                <p className="bc-subtitle">
                  Input your model&apos;s approval and denial counts by demographic group.
                  Get instant Disparate Impact Ratio analysis with regulatory citations.
                </p>
              </div>
              <div style={{ flexShrink: 0, paddingTop: '2rem' }}>
                <Scale size={48} strokeWidth={1} color="var(--bc-accent)" />
              </div>
            </div>
          </div>
        </header>

        <main className="bc-container">
          {/* Preset Scenarios */}
          <div className="bc-section-label" style={{ marginTop: '2rem' }}>PRESET SCENARIOS</div>
          <div className="bc-presets">
            {PRESET_SCENARIOS.map((preset, i) => (
              <button
                key={i}
                className={`bc-preset-btn ${activePreset === i ? 'active' : ''}`}
                onClick={() => loadPreset(i)}
              >
                {preset.name}
              </button>
            ))}
          </div>

          {/* Input Table */}
          <div className="bc-input-section">
            <div className="bc-section-label">DEMOGRAPHIC GROUPS</div>
            <table className="bc-table">
              <thead>
                <tr>
                  <th style={{ width: '30%' }}>Group Name</th>
                  <th style={{ width: '22%' }}>Approved</th>
                  <th style={{ width: '22%' }}>Denied</th>
                  <th style={{ width: '18%', textAlign: 'right' }}>Rate</th>
                  <th style={{ width: '8%' }}></th>
                </tr>
              </thead>
              <tbody key={inputKey}>
                {groups.map(g => {
                  const total = g.approved + g.denied;
                  const rate = total > 0 ? ((g.approved / total) * 100).toFixed(1) : '—';
                  return (
                    <tr key={g.id}>
                      <td>
                        <input
                          className="bc-input bc-input-name"
                          type="text"
                          placeholder="Group name"
                          value={g.name}
                          onChange={e => updateGroup(g.id, 'name', e.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="bc-input"
                          type="number"
                          min="0"
                          value={g.approved || ''}
                          onChange={e => updateGroup(g.id, 'approved', e.target.value)}
                        />
                      </td>
                      <td>
                        <input
                          className="bc-input"
                          type="number"
                          min="0"
                          value={g.denied || ''}
                          onChange={e => updateGroup(g.id, 'denied', e.target.value)}
                        />
                      </td>
                      <td className="bc-rate-preview">{rate}%</td>
                      <td>
                        {groups.length > 2 && (
                          <button className="bc-remove-btn" onClick={() => removeGroup(g.id)}>
                            <Trash2 size={14} />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Action Buttons */}
          <div className="bc-actions">
            <button
              className="bc-btn bc-btn-primary"
              onClick={runAnalysis}
              disabled={groups.filter(g => g.name && (g.approved + g.denied) > 0).length < 2}
            >
              <BarChart3 size={16} />
              Run Bias Analysis
            </button>
            <button className="bc-btn bc-btn-secondary" onClick={addGroup}>
              <Plus size={16} />
              Add Group
            </button>
            <button className="bc-btn bc-btn-secondary" onClick={reset}>
              <RotateCcw size={16} />
              Reset
            </button>
          </div>

          {/* Results */}
          {analysis && (
            <div className="bc-results">
              {/* Overall Result */}
              <div className="bc-section-label">ANALYSIS RESULTS</div>
              <div className={`bc-overall ${analysis.overallPass ? 'bc-overall-pass' : 'bc-overall-fail'}`}>
                <div className="bc-overall-icon">
                  {analysis.overallPass ? (
                    <CheckCircle2 size={36} color="var(--bc-pass)" />
                  ) : (
                    <XCircle size={36} color="var(--bc-fail)" />
                  )}
                </div>
                <div>
                  <h3>
                    {analysis.overallPass
                      ? '80% Rule — All Groups Pass'
                      : '80% Rule Violation Detected'
                    }
                  </h3>
                  <p>
                    Reference group: <strong>{analysis.referenceGroup}</strong> ({analysis.referenceRate}% approval rate).
                    {' '}{analysis.totalApplicants.toLocaleString()} total applicants analyzed.
                    {!analysis.overallPass && (
                      <> <strong>{analysis.results.filter(r => !r.passes80).length} group(s)</strong> fall below the 80% threshold.</>
                    )}
                  </p>
                </div>
              </div>

              {/* Per-Group Cards */}
              <div className="bc-result-grid">
                {analysis.results.map((r, i) => (
                  <div key={i} className={`bc-result-card ${r.severity}`}>
                    <div className="bc-result-name">{r.groupName}</div>
                    <div className="bc-result-metric">
                      <span className="bc-result-label">Approval Rate</span>
                      <span className="bc-result-value">{r.approvalRate}%</span>
                    </div>
                    <div className="bc-result-dir" style={{
                      color: r.severity === 'pass' ? 'var(--bc-pass)'
                        : r.severity === 'warning' ? 'var(--bc-warn)'
                          : 'var(--bc-fail)'
                    }}>
                      {r.dir.toFixed(3)}
                    </div>
                    <div className="bc-result-metric">
                      <span className="bc-result-label">Disparate Impact Ratio</span>
                    </div>
                    <div style={{ marginTop: '0.5rem' }}>
                      <span className={`bc-result-badge ${r.severity === 'pass' ? 'bc-badge-pass'
                        : r.severity === 'warning' ? 'bc-badge-warn'
                          : 'bc-badge-fail'
                        }`}>
                        {r.severity === 'pass' ? '✓ PASS' : r.severity === 'warning' ? '⚠ MARGINAL' : '✗ FAIL'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Applicable Regulations */}
              <div className="bc-regs">
                <div className="bc-section-label">APPLICABLE REGULATIONS</div>
                {analysis.applicableRegs.map((reg) => (
                  <div key={reg.id} className="bc-reg-card">
                    <div className="bc-reg-header">
                      <span className="bc-reg-name">{reg.regulation}</span>
                      <span className="bc-reg-cite">{reg.citation}</span>
                    </div>
                    <div className="bc-reg-req">{reg.requirement}</div>
                    <div className="bc-reg-relevance">{reg.relevance}</div>
                  </div>
                ))}
              </div>

              {/* CTA */}
              <div className="bc-cta">
                <h3>Want Continuous Bias Monitoring?</h3>
                <p>
                  RegEngine&apos;s Bias Engine runs DIR, 80% rule, and statistical significance analysis
                  automatically on every model version — integrated directly into your CI/CD pipeline.
                </p>
                <Link href="/verticals/finance" className="bc-cta-btn">
                  Explore Finance API <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          )}

          {/* Methodology */}
          <div className="bc-method">
            <h3><Info size={16} /> Methodology</h3>
            <p>
              The <strong>Disparate Impact Ratio (DIR)</strong> compares the approval rate of each
              demographic group against the most favored group (reference group). A ratio below
              0.80 indicates potential disparate impact under the EEOC/CFPB four-fifths rule.
            </p>
            <div className="bc-formula">
              DIR = (Approval Rate of Group) / (Approval Rate of Reference Group)
            </div>
            <p>
              The <strong>80% Rule</strong> (four-fifths rule) states that a selection rate for any
              group that is less than 80% (4/5) of the rate for the group with the highest rate
              constitutes evidence of adverse impact. This standard is referenced in EEOC Uniform
              Guidelines (29 CFR 1607.4D) and applied by CFPB in fair lending examinations.
            </p>
            <p style={{ marginBottom: 0 }}>
              <strong>Note:</strong> This tool provides a preliminary assessment only. A comprehensive
              fair lending analysis requires regression modeling, matched-pair testing, and legal review.
              Results should be validated with your compliance team.
            </p>
          </div>

          {/* Footer */}
          <footer className="bc-footer">
            <p className="bc-footer-text">
              This tool is provided free of charge for educational and preliminary assessment purposes.
              It does not constitute legal advice. Disparate impact analysis should be conducted in
              consultation with qualified fair lending counsel. RegEngine Inc. © {new Date().getFullYear()}.
              <br />
              <Link href="/verticals/finance" style={{ color: 'var(--bc-accent)' }}>
                ← Back to Finance Vertical
              </Link>
            </p>
          </footer>
        </main>
      </div>
    </>
  );
}
