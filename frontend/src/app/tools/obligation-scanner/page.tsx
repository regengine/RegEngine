"use client";

import { useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import {
    Shield,
    FileCheck2,
    AlertTriangle,
    CheckCircle2,
    ChevronDown,
    ChevronRight,
    ArrowRight,
    Search,
    Filter,
    BookOpen,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────
   OBLIGATION DATA (from obligations.yaml)
   ───────────────────────────────────────────────────────────── */

interface Obligation {
    id: string;
    citation: string;
    regulator: string;
    domain: string;
    domainLabel: string;
    description: string;
    triggerConditions: string[];
    requiredEvidence: string[];
    riskLevel: 'HIGH' | 'MEDIUM' | 'LOW';
    productTypes: string[];
}

const OBLIGATIONS: Obligation[] = [
    // ECOA
    {
        id: 'ECOA_ADVERSE_ACTION_NOTICE', citation: '12 CFR 1002.9(a)(1)', regulator: 'CFPB', domain: 'ECOA', domainLabel: 'Equal Credit Opportunity Act',
        description: 'Creditor must provide adverse action notice within 30 days of taking adverse action on a credit application.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['adverse_action_notice', 'reason_codes', 'notice_delivery_timestamp'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'ECOA_REASON_DISCLOSURE', citation: '12 CFR 1002.9(b)(2)', regulator: 'CFPB', domain: 'ECOA', domainLabel: 'Equal Credit Opportunity Act',
        description: 'Adverse action notice must include specific reasons for the action or disclose the applicant\'s right to request reasons.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['reason_codes', 'reason_description', 'adverse_action_notice'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'ECOA_CREDIT_SCORING_DISCLOSURE', citation: '12 CFR 1002.9(b)(2)', regulator: 'CFPB', domain: 'ECOA', domainLabel: 'Equal Credit Opportunity Act',
        description: 'If credit scoring system is used, disclosure must indicate key factors that adversely affected the applicant\'s score.',
        triggerConditions: ['credit_denial', 'uses_credit_scoring'], requiredEvidence: ['credit_score', 'adverse_factors', 'scoring_model_name'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending'],
    },
    {
        id: 'ECOA_PROHIBITED_BASIS', citation: '12 CFR 1002.4(a)', regulator: 'CFPB', domain: 'ECOA', domainLabel: 'Equal Credit Opportunity Act',
        description: 'Creditor shall not discriminate against any applicant on the basis of race, color, religion, national origin, sex, marital status, or age.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['protected_class_analysis', 'bias_report', 'disparate_impact_ratio'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance', 'payments'],
    },
    // TILA
    {
        id: 'TILA_APR_DISCLOSURE', citation: '12 CFR 1026.18(d)', regulator: 'CFPB', domain: 'TILA', domainLabel: 'Truth in Lending Act',
        description: 'Creditor must disclose the annual percentage rate (APR) using that term.',
        triggerConditions: ['credit_approval'], requiredEvidence: ['apr_value', 'apr_disclosure_timestamp', 'disclosure_form'],
        riskLevel: 'HIGH', productTypes: ['lending'],
    },
    {
        id: 'TILA_FINANCE_CHARGE_DISCLOSURE', citation: '12 CFR 1026.18(d)', regulator: 'CFPB', domain: 'TILA', domainLabel: 'Truth in Lending Act',
        description: 'Creditor must disclose the finance charge using that term.',
        triggerConditions: ['credit_approval'], requiredEvidence: ['finance_charge_amount', 'finance_charge_disclosure', 'itemized_costs'],
        riskLevel: 'HIGH', productTypes: ['lending'],
    },
    {
        id: 'TILA_AMOUNT_FINANCED', citation: '12 CFR 1026.18(b)', regulator: 'CFPB', domain: 'TILA', domainLabel: 'Truth in Lending Act',
        description: 'Creditor must disclose the amount financed.',
        triggerConditions: ['credit_approval'], requiredEvidence: ['amount_financed', 'loan_amount', 'disclosure_form'],
        riskLevel: 'MEDIUM', productTypes: ['lending'],
    },
    // FCRA
    {
        id: 'FCRA_ADVERSE_ACTION_NOTICE', citation: '15 U.S.C. § 1681m(a)', regulator: 'CFPB', domain: 'FCRA', domainLabel: 'Fair Credit Reporting Act',
        description: 'Must provide adverse action notice if credit is denied based on information from a consumer report.',
        triggerConditions: ['credit_denial', 'used_credit_report'], requiredEvidence: ['adverse_action_notice', 'credit_report_source', 'consumer_reporting_agency_name', 'cra_contact_info'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'FCRA_RISK_BASED_PRICING', citation: '15 U.S.C. § 1681m(h)', regulator: 'CFPB', domain: 'FCRA', domainLabel: 'Fair Credit Reporting Act',
        description: 'Must provide risk-based pricing notice when credit terms offered are materially less favorable based on consumer report.',
        triggerConditions: ['credit_approval', 'risk_based_pricing'], requiredEvidence: ['risk_based_pricing_notice', 'credit_score', 'credit_report_source', 'material_terms_comparison'],
        riskLevel: 'MEDIUM', productTypes: ['lending'],
    },
    {
        id: 'FCRA_ACCURACY_REQUIREMENT', citation: '15 U.S.C. § 1681e(b)', regulator: 'CFPB', domain: 'FCRA', domainLabel: 'Fair Credit Reporting Act',
        description: 'Must follow reasonable procedures to assure maximum possible accuracy of consumer report information.',
        triggerConditions: ['credit_denial', 'used_credit_report'], requiredEvidence: ['credit_report_validation_timestamp', 'accuracy_verification_method', 'data_quality_checks'],
        riskLevel: 'MEDIUM', productTypes: ['credit', 'lending'],
    },
    // UDAAP
    {
        id: 'UDAAP_UNFAIR_PRACTICE', citation: '12 U.S.C. § 5531(c)(1)', regulator: 'CFPB', domain: 'UDAAP', domainLabel: 'Unfair, Deceptive, or Abusive Acts',
        description: 'Act or practice is unfair if it causes substantial injury to consumers which is not reasonably avoidable.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['consumer_injury_assessment', 'avoidability_analysis', 'benefit_cost_analysis'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'payments', 'insurance', 'collections'],
    },
    {
        id: 'UDAAP_DECEPTIVE_PRACTICE', citation: '12 U.S.C. § 5531(c)(2)', regulator: 'CFPB', domain: 'UDAAP', domainLabel: 'Unfair, Deceptive, or Abusive Acts',
        description: 'Act or practice is deceptive if it misleads or is likely to mislead the consumer acting reasonably.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['disclosure_accuracy_check', 'materiality_assessment', 'consumer_understanding_validation'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'payments', 'insurance', 'collections'],
    },
    {
        id: 'UDAAP_ABUSIVE_PRACTICE', citation: '12 U.S.C. § 5531(d)', regulator: 'CFPB', domain: 'UDAAP', domainLabel: 'Unfair, Deceptive, or Abusive Acts',
        description: 'Act or practice is abusive if it materially interferes with consumer\'s ability to understand a term or condition.',
        triggerConditions: ['credit_denial'], requiredEvidence: ['comprehensibility_assessment', 'reasonable_advantage_analysis', 'consumer_vulnerability_check'],
        riskLevel: 'MEDIUM', productTypes: ['credit', 'lending', 'payments', 'insurance', 'collections'],
    },
    // SR 11-7
    {
        id: 'SR_11_7_MODEL_VALIDATION', citation: 'SR 11-7 Section III.B', regulator: 'FRB', domain: 'SR_11_7', domainLabel: 'Model Risk Management',
        description: 'Model validation should include evaluation of conceptual soundness, ongoing monitoring, and outcomes analysis.',
        triggerConditions: ['model_usage'], requiredEvidence: ['validation_report_hash', 'validator_name', 'validation_date', 'conceptual_soundness_assessment'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'SR_11_7_MODEL_DOCUMENTATION', citation: 'SR 11-7 Section III.D', regulator: 'FRB', domain: 'SR_11_7', domainLabel: 'Model Risk Management',
        description: 'Model documentation should provide clear explanation of model design, theory, logic, intended use, and limitations.',
        triggerConditions: ['model_usage'], requiredEvidence: ['model_documentation_hash', 'model_design_description', 'intended_use_statement', 'limitations_disclosure'],
        riskLevel: 'MEDIUM', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'SR_11_7_ONGOING_MONITORING', citation: 'SR 11-7 Section III.C', regulator: 'FRB', domain: 'SR_11_7', domainLabel: 'Model Risk Management',
        description: 'Model should be subject to ongoing monitoring to determine whether it is performing as intended.',
        triggerConditions: ['model_usage'], requiredEvidence: ['monitoring_report_hash', 'performance_metrics', 'drift_detection_results', 'monitoring_frequency'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'SR_11_7_MODEL_INVENTORY', citation: 'SR 11-7 Section II', regulator: 'FRB', domain: 'SR_11_7', domainLabel: 'Model Risk Management',
        description: 'Must maintain inventory of models with information about model type, use, and risk rating.',
        triggerConditions: ['model_usage'], requiredEvidence: ['model_registry_entry', 'model_version_id', 'model_risk_rating', 'model_use_case'],
        riskLevel: 'MEDIUM', productTypes: ['credit', 'lending', 'insurance'],
    },
    // OCC AI
    {
        id: 'OCC_AI_GOVERNANCE', citation: 'OCC Bulletin 2023-XX', regulator: 'OCC', domain: 'OCC_AI', domainLabel: 'OCC AI/ML Guidance',
        description: 'Establish effective governance, risk management, and controls over AI/ML model development and deployment.',
        triggerConditions: ['model_usage', 'ai_ml_model'], requiredEvidence: ['ai_governance_framework', 'risk_assessment', 'control_documentation', 'board_oversight_evidence'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'payments', 'insurance'],
    },
    {
        id: 'OCC_AI_BIAS_TESTING', citation: 'OCC Bulletin 2023-XX §3', regulator: 'OCC', domain: 'OCC_AI', domainLabel: 'OCC AI/ML Guidance',
        description: 'Must test AI/ML models for bias and discriminatory outcomes, particularly for consumer-facing applications.',
        triggerConditions: ['model_usage', 'ai_ml_model', 'consumer_facing'], requiredEvidence: ['bias_testing_report', 'disparate_impact_analysis', 'protected_class_analysis', 'bias_mitigation_evidence'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'OCC_AI_EXPLAINABILITY', citation: 'OCC Bulletin 2023-XX §4', regulator: 'OCC', domain: 'OCC_AI', domainLabel: 'OCC AI/ML Guidance',
        description: 'AI/ML models must provide sufficient explainability, especially for adverse consumer outcomes.',
        triggerConditions: ['credit_denial', 'ai_ml_model'], requiredEvidence: ['model_explanation', 'feature_importance', 'reason_codes', 'consumer_explanation_provided'],
        riskLevel: 'HIGH', productTypes: ['credit', 'lending', 'insurance'],
    },
    {
        id: 'OCC_AI_DATA_QUALITY', citation: 'OCC Bulletin 2023-XX §2', regulator: 'OCC', domain: 'OCC_AI', domainLabel: 'OCC AI/ML Guidance',
        description: 'Data used for AI/ML training and inference must be accurate, complete, and representative.',
        triggerConditions: ['model_usage', 'ai_ml_model'], requiredEvidence: ['training_data_hash', 'data_quality_report', 'representativeness_assessment', 'data_source_documentation'],
        riskLevel: 'MEDIUM', productTypes: ['credit', 'lending', 'insurance'],
    },
];

const PRODUCT_TYPES = [
    { id: 'credit', label: 'Credit Decisioning', description: 'Credit card approvals, credit line increases' },
    { id: 'lending', label: 'Lending', description: 'Mortgages, auto loans, personal loans, BNPL' },
    { id: 'payments', label: 'Payment Processing', description: 'Payment gateways, money transfer, digital wallets' },
    { id: 'insurance', label: 'Insurance Underwriting', description: 'Policy pricing, claims, risk assessment' },
    { id: 'collections', label: 'Collections', description: 'Debt collection, recovery, settlement' },
];

const DOMAIN_COLORS: Record<string, string> = {
    ECOA: 'var(--os-warn, #f59e0b)',
    TILA: 'var(--os-blue, #3b82f6)',
    FCRA: '#8b5cf6',
    UDAAP: 'var(--os-fail, #ef4444)',
    SR_11_7: 'var(--os-accent, #10b981)',
    OCC_AI: '#06b6d4',
};

/* ─────────────────────────────────────────────────────────────
   COMPONENT
   ───────────────────────────────────────────────────────────── */

export default function ObligationScannerPage() {
    const [selectedProduct, setSelectedProduct] = useState<string>('credit');
    const [usesAiMl, setUsesAiMl] = useState(true);
    const [usesCreditReports, setUsesCreditReports] = useState(true);
    const [consumerFacing, setConsumerFacing] = useState(true);
    const [expandedId, setExpandedId] = useState<string | null>(null);

    const filteredObligations = useMemo(() => {
        return OBLIGATIONS.filter(ob => {
            // Must match product type
            if (!ob.productTypes.includes(selectedProduct)) return false;
            // Filter SR 11-7 and OCC obligations if not using AI/ML
            if (!usesAiMl && (ob.domain === 'SR_11_7' || ob.domain === 'OCC_AI')) return false;
            // Filter FCRA credit report requirements if not using credit reports
            if (!usesCreditReports && ob.triggerConditions.includes('used_credit_report')) return false;
            // Filter consumer-facing OCC if not consumer facing
            if (!consumerFacing && ob.triggerConditions.includes('consumer_facing')) return false;
            return true;
        });
    }, [selectedProduct, usesAiMl, usesCreditReports, consumerFacing]);

    const domainGroups = useMemo(() => {
        const groups: Record<string, Obligation[]> = {};
        filteredObligations.forEach(ob => {
            if (!groups[ob.domain]) groups[ob.domain] = [];
            groups[ob.domain].push(ob);
        });
        return groups;
    }, [filteredObligations]);

    const highCount = filteredObligations.filter(o => o.riskLevel === 'HIGH').length;
    const medCount = filteredObligations.filter(o => o.riskLevel === 'MEDIUM').length;

    return (
        <>
            <style jsx global>{`
        :root {
          --os-bg: var(--re-surface-base, #06090f);
          --os-surface: var(--re-surface-card, #0c1017);
          --os-elevated: var(--re-surface-elevated, #111827);
          --os-border: rgba(255,255,255,0.08);
          --os-border-strong: rgba(255,255,255,0.15);
          --os-text: var(--re-text-primary, #f8fafc);
          --os-text-muted: var(--re-text-muted, #64748b);
          --os-text-dim: var(--re-text-disabled, #475569);
          --os-accent: var(--re-brand, #10b981);
          --os-accent-hover: var(--re-brand-light, #34d399);
          --os-fail: #ef4444;
          --os-warn: #f59e0b;
          --os-blue: #3b82f6;
        }
        .os-page {
          min-height: 100vh;
          background: var(--os-bg);
          color: var(--os-text);
          font-family: 'Instrument Sans', 'Inter', system-ui, sans-serif;
        }
        .os-container {
          max-width: 1100px;
          margin: 0 auto;
          padding: 0 1.5rem;
        }
        .os-header {
          padding: 2rem 0;
          border-bottom: 1px solid var(--os-border);
        }
        .os-breadcrumb {
          display: flex; align-items: center; gap: 0.5rem;
          font-size: 0.8rem; color: var(--os-text-muted); margin-bottom: 1.5rem;
        }
        .os-breadcrumb a { color: var(--os-text-muted); text-decoration: none; }
        .os-breadcrumb a:hover { color: var(--os-accent); }
        .os-badge-free {
          display: inline-flex; align-items: center; gap: 0.35rem;
          background: rgba(16,185,129,0.1); color: var(--os-accent);
          font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
          padding: 0.25rem 0.6rem; border-radius: 4px; border: 1px solid rgba(16,185,129,0.2); margin-bottom: 0.75rem;
        }
        .os-page h1 { font-size: 2rem; font-weight: 700; margin: 0 0 0.75rem; letter-spacing: -0.025em; }
        .os-subtitle { font-size: 1.05rem; color: var(--os-text-muted); line-height: 1.6; max-width: 600px; }
        .os-section-label {
          font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em;
          color: var(--os-text-dim); margin-bottom: 1rem; margin-top: 2rem;
        }

        /* Product Selector */
        .os-products { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem; }
        .os-product-btn {
          background: var(--os-surface); border: 1px solid var(--os-border);
          color: var(--os-text-muted); padding: 1rem; border-radius: 8px;
          cursor: pointer; transition: all 0.15s; text-align: left;
        }
        .os-product-btn:hover { border-color: var(--os-border-strong); color: var(--os-text); }
        .os-product-btn.active { border-color: var(--os-accent); color: var(--os-accent); background: rgba(16,185,129,0.05); }
        .os-product-name { font-size: 0.9rem; font-weight: 600; margin-bottom: 0.25rem; }
        .os-product-desc { font-size: 0.75rem; opacity: 0.7; }

        /* Toggles */
        .os-toggles { display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.5rem 0; }
        .os-toggle {
          display: flex; align-items: center; gap: 0.5rem;
          background: var(--os-surface); border: 1px solid var(--os-border);
          padding: 0.6rem 1rem; border-radius: 6px; cursor: pointer;
          font-size: 0.85rem; color: var(--os-text-muted); transition: all 0.15s;
          user-select: none;
        }
        .os-toggle:hover { border-color: var(--os-border-strong); }
        .os-toggle.active { border-color: var(--os-accent); color: var(--os-accent); background: rgba(16,185,129,0.05); }
        .os-toggle-dot {
          width: 12px; height: 12px; border-radius: 50%;
          background: var(--os-border-strong); transition: background 0.15s;
        }
        .os-toggle.active .os-toggle-dot { background: var(--os-accent); }

        /* Summary Bar */
        .os-summary {
          display: flex; gap: 1.5rem; flex-wrap: wrap;
          padding: 1.25rem 1.5rem; background: var(--os-surface);
          border: 1px solid var(--os-border); border-radius: 10px; margin: 1.5rem 0;
        }
        .os-summary-item { text-align: center; }
        .os-summary-value {
          font-family: 'JetBrains Mono', monospace; font-size: 1.4rem; font-weight: 700;
        }
        .os-summary-label { font-size: 0.7rem; color: var(--os-text-muted); text-transform: uppercase; letter-spacing: 0.05em; }

        /* Obligation Cards */
        .os-domain-group { margin-bottom: 1.5rem; }
        .os-domain-header {
          display: flex; align-items: center; gap: 0.75rem;
          padding: 0.75rem 0; margin-bottom: 0.5rem;
          font-size: 0.9rem; font-weight: 600;
        }
        .os-domain-dot { width: 10px; height: 10px; border-radius: 50%; }
        .os-domain-count {
          font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;
          background: var(--os-surface); padding: 0.15rem 0.5rem; border-radius: 10px;
          color: var(--os-text-muted);
        }
        .os-ob-card {
          background: var(--os-surface); border: 1px solid var(--os-border);
          border-radius: 8px; margin-bottom: 0.5rem; overflow: hidden;
          transition: border-color 0.15s;
        }
        .os-ob-card:hover { border-color: var(--os-border-strong); }
        .os-ob-header {
          display: flex; align-items: center; justify-content: space-between; gap: 1rem;
          padding: 1rem 1.25rem; cursor: pointer;
        }
        .os-ob-left { display: flex; align-items: center; gap: 0.75rem; flex: 1; min-width: 0; }
        .os-ob-name { font-size: 0.85rem; font-weight: 500; }
        .os-ob-cite {
          font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
          color: var(--os-accent); background: rgba(16,185,129,0.08);
          padding: 0.2rem 0.5rem; border-radius: 4px; white-space: nowrap; flex-shrink: 0;
        }
        .os-risk-badge {
          font-size: 0.65rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
          padding: 0.2rem 0.5rem; border-radius: 4px; flex-shrink: 0;
        }
        .os-risk-high { background: rgba(239,68,68,0.15); color: var(--os-fail); }
        .os-risk-medium { background: rgba(245,158,11,0.15); color: var(--os-warn); }
        .os-risk-low { background: rgba(16,185,129,0.15); color: var(--os-accent); }
        .os-ob-detail {
          padding: 0 1.25rem 1.25rem;
          border-top: 1px solid var(--os-border);
        }
        .os-ob-desc {
          font-size: 0.85rem; color: var(--os-text-muted); line-height: 1.6; margin: 1rem 0;
        }
        .os-evidence-title {
          font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
          color: var(--os-text-dim); margin-bottom: 0.5rem;
        }
        .os-evidence-list {
          display: flex; flex-wrap: wrap; gap: 0.4rem;
        }
        .os-evidence-tag {
          font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
          background: var(--os-elevated); border: 1px solid var(--os-border);
          padding: 0.25rem 0.6rem; border-radius: 4px; color: var(--os-text-muted);
        }

        /* CTA */
        .os-cta {
          background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.08));
          border: 1px solid rgba(16,185,129,0.2); border-radius: 10px;
          padding: 2rem; text-align: center; margin: 2.5rem 0;
        }
        .os-cta h3 { font-size: 1.2rem; font-weight: 700; margin: 0 0 0.5rem; }
        .os-cta p { font-size: 0.9rem; color: var(--os-text-muted); margin: 0 0 1.25rem; line-height: 1.5; }
        .os-cta-btn {
          display: inline-flex; align-items: center; gap: 0.5rem;
          background: var(--os-accent); color: #000; font-weight: 600; font-size: 0.9rem;
          padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; transition: background 0.15s;
        }
        .os-cta-btn:hover { background: var(--os-accent-hover); }

        .os-footer {
          border-top: 1px solid var(--os-border); padding: 2rem 0; margin-top: 3rem;
        }
        .os-footer-text {
          font-size: 0.78rem; color: var(--os-text-dim); line-height: 1.65; max-width: 700px;
        }

        @media (max-width: 768px) {
          .os-page h1 { font-size: 1.5rem; }
          .os-products { grid-template-columns: 1fr 1fr; }
          .os-ob-header { flex-direction: column; align-items: flex-start; }
        }
      `}</style>

            <div className="os-page">
                <header className="os-header">
                    <div className="os-container">
                        <div className="os-breadcrumb">
                            <Link href="/">RegEngine</Link>
                            <span>/</span>
                            <Link href="/verticals/finance">Finance</Link>
                            <span>/</span>
                            <span>Obligation Scanner</span>
                        </div>
                        <div className="os-badge-free"><Shield size={12} /> Free Tool</div>
                        <h1>Regulatory Obligation Scanner</h1>
                        <p className="os-subtitle">
                            Select your fintech product type and features — see exactly which of the 21 regulatory
                            obligations apply to you, with full CFR citations and required evidence.
                        </p>
                    </div>
                </header>

                <main className="os-container">
                    {/* Product Type Selection */}
                    <div className="os-section-label">SELECT YOUR PRODUCT TYPE</div>
                    <div className="os-products">
                        {PRODUCT_TYPES.map(pt => (
                            <button
                                key={pt.id}
                                className={`os-product-btn ${selectedProduct === pt.id ? 'active' : ''}`}
                                onClick={() => setSelectedProduct(pt.id)}
                            >
                                <div className="os-product-name">{pt.label}</div>
                                <div className="os-product-desc">{pt.description}</div>
                            </button>
                        ))}
                    </div>

                    {/* Feature Toggles */}
                    <div className="os-section-label">YOUR FEATURES</div>
                    <div className="os-toggles">
                        <div className={`os-toggle ${usesAiMl ? 'active' : ''}`} onClick={() => setUsesAiMl(!usesAiMl)}>
                            <div className="os-toggle-dot" />
                            Uses AI/ML Models
                        </div>
                        <div className={`os-toggle ${usesCreditReports ? 'active' : ''}`} onClick={() => setUsesCreditReports(!usesCreditReports)}>
                            <div className="os-toggle-dot" />
                            Uses Credit Reports
                        </div>
                        <div className={`os-toggle ${consumerFacing ? 'active' : ''}`} onClick={() => setConsumerFacing(!consumerFacing)}>
                            <div className="os-toggle-dot" />
                            Consumer-Facing
                        </div>
                    </div>

                    {/* Summary */}
                    <div className="os-summary">
                        <div className="os-summary-item">
                            <div className="os-summary-value" style={{ color: 'var(--os-accent)' }}>{filteredObligations.length}</div>
                            <div className="os-summary-label">Obligations Apply</div>
                        </div>
                        <div className="os-summary-item">
                            <div className="os-summary-value" style={{ color: 'var(--os-fail)' }}>{highCount}</div>
                            <div className="os-summary-label">High Risk</div>
                        </div>
                        <div className="os-summary-item">
                            <div className="os-summary-value" style={{ color: 'var(--os-warn)' }}>{medCount}</div>
                            <div className="os-summary-label">Medium Risk</div>
                        </div>
                        <div className="os-summary-item">
                            <div className="os-summary-value">{Object.keys(domainGroups).length}</div>
                            <div className="os-summary-label">Reg Domains</div>
                        </div>
                        <div className="os-summary-item">
                            <div className="os-summary-value">{filteredObligations.reduce((sum, o) => sum + o.requiredEvidence.length, 0)}</div>
                            <div className="os-summary-label">Evidence Items</div>
                        </div>
                    </div>

                    {/* Obligation Cards by Domain */}
                    <div className="os-section-label">YOUR REGULATORY OBLIGATIONS</div>
                    {Object.entries(domainGroups).map(([domain, obs]) => (
                        <div key={domain} className="os-domain-group">
                            <div className="os-domain-header">
                                <div className="os-domain-dot" style={{ background: DOMAIN_COLORS[domain] || '#888' }} />
                                <span>{obs[0].domainLabel}</span>
                                <span className="os-domain-count">{obs.length}</span>
                            </div>
                            {obs.map(ob => (
                                <div key={ob.id} className="os-ob-card">
                                    <div className="os-ob-header" onClick={() => setExpandedId(expandedId === ob.id ? null : ob.id)}>
                                        <div className="os-ob-left">
                                            {expandedId === ob.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                                            <span className="os-ob-name">{ob.description.substring(0, 80)}{ob.description.length > 80 ? '...' : ''}</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                            <span className="os-ob-cite">{ob.citation}</span>
                                            <span className={`os-risk-badge os-risk-${ob.riskLevel.toLowerCase()}`}>{ob.riskLevel}</span>
                                        </div>
                                    </div>
                                    {expandedId === ob.id && (
                                        <div className="os-ob-detail">
                                            <div className="os-ob-desc">{ob.description}</div>
                                            <div className="os-evidence-title">Required Evidence ({ob.requiredEvidence.length} items)</div>
                                            <div className="os-evidence-list">
                                                {ob.requiredEvidence.map(ev => (
                                                    <span key={ev} className="os-evidence-tag">{ev}</span>
                                                ))}
                                            </div>
                                            <div style={{ marginTop: '0.75rem', fontSize: '0.78rem', color: 'var(--os-text-dim)' }}>
                                                Regulator: {ob.regulator} &nbsp;·&nbsp; ID: {ob.id}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    ))}

                    {filteredObligations.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '3rem 0', color: 'var(--os-text-muted)' }}>
                            <Filter size={32} strokeWidth={1} style={{ marginBottom: '1rem', opacity: 0.5 }} />
                            <p>No obligations match your current selection. Try adjusting your product type or feature toggles.</p>
                        </div>
                    )}

                    {/* CTA */}
                    <div className="os-cta">
                        <h3>Automate Obligation Evaluation</h3>
                        <p>
                            RegEngine&apos;s ROE (Regulatory Obligation Engine) evaluates every financial decision
                            against all {filteredObligations.length} applicable requirements automatically — zero manual mapping.
                        </p>
                        <Link href="/verticals/finance" className="os-cta-btn">
                            Explore Finance API <ArrowRight size={16} />
                        </Link>
                    </div>

                    {/* Footer */}
                    <footer className="os-footer">
                        <p className="os-footer-text">
                            Obligation mappings are based on published federal regulations and guidance documents.
                            This tool is for informational purposes only and does not constitute legal advice.
                            Consult qualified regulatory counsel for compliance determinations.
                            <br />
                            <Link href="/tools/bias-checker" style={{ color: 'var(--os-accent)', marginRight: '1rem' }}>
                                AI Model Bias Checker →
                            </Link>
                            <Link href="/verticals/finance" style={{ color: 'var(--os-accent)' }}>
                                ← Back to Finance Vertical
                            </Link>
                        </p>
                    </footer>
                </main>
            </div>
        </>
    );
}
