"use client";

import { useState, useEffect } from 'react';
import Head from 'next/head';
import Link from 'next/link';

import { useToast } from "@/components/ui/use-toast";

export default function FinancePage() {
  const [stats, setStats] = useState<any>(null);
  const [snapshot, setSnapshot] = useState<any>(null);
  const [statsError, setStatsError] = useState<string | null>(null);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const { toast } = useToast();

  useEffect(() => {
    setLoading(true);

    // Fetch live Finance API stats
    fetch('/api/finance/stats')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then(data => {
        setStats(data);
        setStatsError(null);
      })
      .catch(err => {
        console.error('Stats fetch failed:', err);
        setStatsError('Unable to load statistics. The Finance API may be offline.');
        toast({
          title: "Connection Error",
          description: "Could not connect to Finance API stats service.",
          variant: "destructive",
        });
      });

    // Fetch compliance snapshot
    fetch('/api/finance/snapshot')
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        return res.json();
      })
      .then(data => {
        setSnapshot(data);
        setSnapshotError(null);
      })
      .catch(err => {
        console.error('Snapshot fetch failed:', err);
        setSnapshotError('Unable to load compliance snapshot. The Finance API may be offline.');
        toast({
          title: "Snapshot Failed",
          description: "Could not retrieve compliance snapshot.",
          variant: "destructive",
        });
      })
      .finally(() => {
        setLoading(false);
      });
  }, [toast]);

  return (
    <>
      <Head>
        <title>RegEngine Finance — The API for Financial Compliance</title>
        <meta name="description" content="Immutable evidence chains for SOC 2, PCI DSS, and multi-jurisdiction licensing" />
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Instrument+Sans:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </Head>

      <style jsx global>{`
        :root {
          --bg-primary: #09090b;
          --bg-secondary: #0f0f13;
          --bg-card: #16161d;
          --bg-card-hover: #1c1c26;
          --accent-emerald: #34d399;
          --accent-violet: #8b5cf6;
          --accent-blue: #3b82f6;
          --accent-amber: #fbbf24;
          --accent-red: #f87171;
          --accent-sky: #38bdf8;
          --text-primary: #f4f4f5;
          --text-secondary: #a1a1aa;
          --text-muted: #71717a;
          --border: #27272a;
          --border-accent: #2e2e3a;
          --glow-emerald: rgba(52, 211, 153, 0.12);
          --glow-violet: rgba(139, 92, 246, 0.1);
        }

        body {
          font-family: 'Instrument Sans', sans-serif;
          background: var(--bg-primary);
          color: var(--text-primary);
          line-height: 1.7;
          overflow-x: hidden;
        }

        code, .mono { font-family: 'JetBrains Mono', monospace; }

        .container { max-width: 1140px; margin: 0 auto; padding: 0 2rem; }
        .section { padding: 5rem 0; }
        .section-label {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.75rem;
          letter-spacing: 0.15em;
          text-transform: uppercase;
          color: var(--accent-emerald);
          margin-bottom: 1rem;
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .section-label::before {
          content: '';
          width: 24px;
          height: 1px;
          background: var(--accent-emerald);
        }
        .section-title {
          font-size: 2.25rem;
          font-weight: 700;
          line-height: 1.2;
          margin-bottom: 1rem;
        }
        .section-subtitle {
          font-size: 1.1rem;
          color: var(--text-secondary);
          max-width: 640px;
          margin-bottom: 3rem;
        }
        .badge {
          display: inline-block;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.7rem;
          padding: 0.2rem 0.6rem;
          border-radius: 4px;
          font-weight: 500;
          letter-spacing: 0.05em;
        }
        .badge-high { background: rgba(248,113,113,0.15); color: var(--accent-red); }
        .badge-medium { background: rgba(251,191,36,0.15); color: var(--accent-amber); }
        .badge-low { background: rgba(52,211,153,0.15); color: var(--accent-emerald); }
        .badge-new { background: rgba(52,211,153,0.15); color: var(--accent-emerald); }
        .badge-hot { background: rgba(139,92,246,0.15); color: var(--accent-violet); }

        .hero {
          padding: 10rem 0 6rem;
          position: relative;
          overflow: hidden;
        }
        .hero::before {
          content: '';
          position: absolute;
          top: -200px;
          right: -150px;
          width: 600px;
          height: 600px;
          background: radial-gradient(circle, var(--glow-emerald), transparent 70%);
          pointer-events: none;
        }
        .hero::after {
          content: '';
          position: absolute;
          bottom: -100px;
          left: -100px;
          width: 400px;
          height: 400px;
          background: radial-gradient(circle, var(--glow-violet), transparent 70%);
          pointer-events: none;
        }
        .hero-eyebrow {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
          color: var(--accent-emerald);
          letter-spacing: 0.1em;
          margin-bottom: 1.5rem;
        }
        .hero h1 {
          font-size: 3.75rem;
          font-weight: 700;
          line-height: 1.1;
          letter-spacing: -0.03em;
          max-width: 740px;
          margin-bottom: 1.5rem;
        }
        .hero h1 .highlight {
          background: linear-gradient(135deg, var(--accent-emerald), var(--accent-sky));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .hero-sub {
          font-size: 1.2rem;
          color: var(--text-secondary);
          max-width: 580px;
          margin-bottom: 2.5rem;
          line-height: 1.8;
        }
        .hero-actions { display: flex; gap: 1rem; margin-bottom: 3rem; }
        .btn {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.6rem 1.25rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 600;
          text-decoration: none;
          transition: all 0.2s;
          cursor: pointer;
          border: none;
        }
        .btn-primary {
          background: var(--accent-emerald);
          color: #09090b;
          box-shadow: 0 0 20px rgba(52,211,153,0.25);
        }
        .btn-primary:hover { background: #2dd4a0; box-shadow: 0 0 30px rgba(52,211,153,0.35); }
        .btn-secondary {
          background: transparent;
          color: var(--text-secondary);
          border: 1px solid var(--border);
        }
        .btn-secondary:hover { border-color: var(--text-muted); color: var(--text-primary); }

        .hero-stats {
          display: flex;
          gap: 3rem;
          padding-top: 2.5rem;
          border-top: 1px solid var(--border);
        }
        .hero-stat .mono {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-primary);
          display: block;
        }
        .hero-stat span:last-child {
          font-size: 0.8rem;
          color: var(--text-muted);
        }

        .hero-rotate {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.85rem;
          color: var(--accent-emerald);
          background: rgba(52,211,153,0.06);
          border: 1px solid rgba(52,211,153,0.15);
          border-radius: 6px;
          padding: 0.75rem 1rem;
          margin-bottom: 2rem;
          max-width: 620px;
          position: relative;
          overflow: hidden;
          height: 2.75rem;
        }
        .hero-rotate .rotate-item {
          position: absolute;
          left: 1rem;
          opacity: 0;
          animation: rotateText 16s infinite;
        }
        .hero-rotate .rotate-item:nth-child(1) { animation-delay: 0s; }
        .hero-rotate .rotate-item:nth-child(2) { animation-delay: 4s; }
        .hero-rotate .rotate-item:nth-child(3) { animation-delay: 8s; }
        .hero-rotate .rotate-item:nth-child(4) { animation-delay: 12s; }
        @keyframes rotateText {
          0%, 2% { opacity: 0; transform: translateY(8px); }
          4%, 22% { opacity: 1; transform: translateY(0); }
          24%, 100% { opacity: 0; transform: translateY(-8px); }
        }

        .challenge-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
          gap: 1.5rem;
        }
        .challenge-card {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 1.75rem;
          transition: all 0.3s;
          position: relative;
        }
        .challenge-card:hover {
          border-color: var(--border-accent);
          background: var(--bg-card-hover);
          transform: translateY(-2px);
        }
        .challenge-card h3 {
          font-size: 1.05rem;
          font-weight: 600;
          margin-bottom: 0.5rem;
        }
        .challenge-card p {
          font-size: 0.9rem;
          color: var(--text-secondary);
          line-height: 1.7;
        }
        .challenge-card .severity {
          position: absolute;
          top: 1.75rem;
          right: 1.75rem;
        }

        .code-block {
          background: #0d1117;
          border: 1px solid var(--border);
          border-radius: 10px;
          overflow: hidden;
          margin-top: 2rem;
        }
        .code-header {
          background: var(--bg-secondary);
          padding: 0.75rem 1.25rem;
          border-bottom: 1px solid var(--border);
          display: flex;
          justify-content: space-between;
          align-items: center;
        }
        .code-header span {
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
          color: var(--text-muted);
        }
        pre {
          padding: 1.5rem;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.8rem;
          line-height: 1.8;
          overflow-x: auto;
          color: var(--text-secondary);
        }
        pre .comment { color: #6a737d; }
        pre .keyword { color: #ff7b72; }
        pre .string { color: #a5d6ff; }
        pre .func { color: #d2a8ff; }
        pre .const { color: #79c0ff; }

        .live-stats-banner {
          background: rgba(52,211,153,0.08);
          border: 1px solid rgba(52,211,153,0.2);
          border-radius: 10px;
          padding: 1.5rem;
          margin-bottom: 3rem;
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 2rem;
        }
        .live-stat {
          text-align: center;
        }
        .live-stat .value {
          font-family: 'JetBrains Mono', monospace;
          font-size: 1.75rem;
          font-weight: 700;
          color: var(--accent-emerald);
          display: block;
          margin-bottom: 0.25rem;
        }
        .live-stat .label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }

        @media (max-width: 768px) {
          .hero h1 { font-size: 2.25rem; }
          .hero-stats { flex-direction: column; gap: 1.5rem; }
          .live-stats-banner { grid-template-columns: 1fr 1fr; }
        }
      `}</style>

      {/* Hero */}
      <section className="hero" id="overview">
        <div className="container">
          <div className="hero-eyebrow">FINANCIAL COMPLIANCE API</div>
          <h1>
            Compliance infrastructure that <span className="highlight">scales with you</span>
          </h1>
          <p className="hero-sub">
            Immutable evidence chains for SOC 2, PCI DSS, and multi-jurisdiction licensing —
            built for fintech teams that ship weekly, not quarterly.
          </p>

          <div className="hero-rotate">
            <span className="rotate-item">→ ROE evaluates {stats?.obligations_total || 21} regulatory obligations automatically</span>
            <span className="rotate-item">→ Evidence V3 creates cryptographic proof chains with SHA-256 hashing</span>
            <span className="rotate-item">→ Bias & drift engines monitor {stats?.models_tracked || 1}+ AI models for compliance</span>
            <span className="rotate-item">→ Multi-jurisdiction compliance tracking across all US states</span>
          </div>

          <div className="hero-actions">
            <Link href="/docs/api" className="btn btn-primary">
              View API Docs →
            </Link>
            <a className="btn btn-secondary" href="#api">See Examples</a>
          </div>

          <div className="hero-stats">
            <div className="hero-stat">
              <span className="mono">5 min</span>
              <span>Quickstart</span>
            </div>
            <div className="hero-stat">
              <span className="mono">21+</span>
              <span>Obligations</span>
            </div>
            <div className="hero-stat">
              <span className="mono">SHA-256</span>
              <span>Hash Verification</span>
            </div>
            <div className="hero-stat">
              <span className="mono">{stats?.decisions_recorded || 0}</span>
              <span>Decisions Tracked</span>
            </div>
          </div>
        </div>
      </section>

      {/* Error Banners */}
      {(statsError || snapshotError) && (
        <section className="section" style={{ paddingTop: '2rem', paddingBottom: 0 }}>
          <div className="container">
            {statsError && (
              <div style={{
                background: 'rgba(248, 113, 113, 0.1)',
                border: '1px solid rgba(248, 113, 113, 0.3)',
                borderRadius: '8px',
                padding: '1rem 1.25rem',
                marginBottom: '1rem',
                color: 'var(--accent-red)',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem'
              }}>
                <span style={{ fontSize: '1.25rem' }}>⚠️</span>
                <span>{statsError}</span>
              </div>
            )}
            {snapshotError && (
              <div style={{
                background: 'rgba(251, 191, 36, 0.1)',
                border: '1px solid rgba(251, 191, 36, 0.3)',
                borderRadius: '8px',
                padding: '1rem 1.25rem',
                color: 'var(--accent-amber)',
                fontSize: '0.875rem',
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.75rem'
              }}>
                <span style={{ fontSize: '1.25rem' }}>⚠️</span>
                <span>{snapshotError}</span>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Live Stats Banner */}
      {snapshot && (
        <section className="section pt-0">
          <div className="container">
            <div className="section-label">LIVE COMPLIANCE SNAPSHOT</div>
            <div className="live-stats-banner">
              <div className="live-stat">
                <span className="value">{snapshot.total_compliance_score?.toFixed(1) || '—'}</span>
                <span className="label">Total Compliance</span>
              </div>
              <div className="live-stat">
                <span className="value">{snapshot.bias_score?.toFixed(0) || '—'}</span>
                <span className="label">Bias Score</span>
              </div>
              <div className="live-stat">
                <span className="value">{snapshot.drift_score?.toFixed(0) || '—'}</span>
                <span className="label">Drift Score</span>
              </div>
              <div className="live-stat">
                <span className="value">
                  <span className={`badge badge-${snapshot.risk_level === 'low' ? 'low' : snapshot.risk_level === 'medium' ? 'medium' : 'high'}`}>
                    {snapshot.risk_level?.toUpperCase() || 'N/A'}
                  </span>
                </span>
                <span className="label">Risk Level</span>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Challenges */}
      <section className="section" id="challenges">
        <div className="container">
          <div className="section-label">Why Emerging Fintech Has It Harder</div>
          <h2 className="section-title">Fast-moving companies. Slow-moving regulators.</h2>
          <p className="section-subtitle">
            You're building the future of finance while navigating regulations designed
            for bank branches. The gap between your velocity and their expectations is where risk lives.
          </p>

          <div className="challenge-grid">
            <div className="challenge-card">
              <span className="badge badge-high severity">HIGH</span>
              <h3>AI Model Bias Detection</h3>
              <p>ECOA requires proving your credit models don't discriminate. Our Bias Engine evaluates DIR,
                80% rule, and statistical significance across protected classes — automatically on every model version.</p>
            </div>
            <div className="challenge-card">
              <span className="badge badge-high severity">HIGH</span>
              <h3>Model Drift Monitoring</h3>
              <p>SR 11-7 model risk management requires continuous monitoring. Our Drift Engine tracks PSI,
                KL/JS divergence across features — alerting when models deviate from training distribution.</p>
            </div>
            <div className="challenge-card">
              <span className="badge badge-high severity">HIGH</span>
              <h3>Regulatory Obligation Coverage</h3>
              <p>{stats?.obligations_total || 21} obligations across ECOA, TILA, FCRA, UDAAP, and OCC AI/ML guidance.
                Our ROE evaluates every decision against applicable requirements — zero manual mapping.</p>
            </div>
            <div className="challenge-card">
              <span className="badge badge-medium severity">MEDIUM</span>
              <h3>Evidence Chain Integrity</h3>
              <p>Auditors need proof controls existed at specific timestamps. Evidence V3 creates cryptographic
                hash chains with Merkle roots — tamper detection built-in.</p>
            </div>
            <div className="challenge-card">
              <span className="badge badge-hot severity">LIVE</span>
              <h3>Real-Time Compliance Scoring</h3>
              <p>Snapshot service computes weighted compliance across bias (30%), drift (20%), documentation (25%),
                and regulatory mapping (25%) — from your API, not quarterly reports.</p>
            </div>
            <div className="challenge-card">
              <span className="badge badge-new severity">NEW</span>
              <h3>Graph-Based Audit Trails</h3>
              <p>Neo4j persistence with decision → model → obligation → evidence relationships.
                Cypher queries for chain traversal and violation analysis.</p>
            </div>
          </div>
        </div>
      </section>



      {/* API Example */}
      <section className="section" id="api" style={{ background: 'var(--bg-secondary)' }}>
        <div className="container">
          <div className="section-label">Developer Experience</div>
          <h2 className="section-title">Compliance evidence from your deploy pipeline.</h2>
          <p className="section-subtitle">
            Record credit decisions, evaluate obligations, create evidence envelopes — all from your code.
          </p>

          {(() => {
            const codeHtml = [
              '<span style="color:#ff7b72">import</span> requests',
              '',
              '<span style="color:#8b949e"># Record a credit denial decision with full compliance workflow</span>',
              'response = requests.<span style="color:#d2a8ff">post</span>(<span style="color:#a5d6ff">"http://localhost:8000/v1/finance/decision/record"</span>, json={',
              '    <span style="color:#a5d6ff">"decision_id"</span>: <span style="color:#a5d6ff">"dec_001"</span>,',
              '    <span style="color:#a5d6ff">"decision_type"</span>: <span style="color:#a5d6ff">"credit_denial"</span>,',
              '    <span style="color:#a5d6ff">"evidence"</span>: {',
              '        <span style="color:#a5d6ff">"adverse_action_notice"</span>: <span style="color:#a5d6ff">"Application denied..."</span>,',
              '        <span style="color:#a5d6ff">"reason_codes"</span>: [<span style="color:#a5d6ff">"insufficient_credit_history"</span>],',
              '        <span style="color:#a5d6ff">"notification_timing"</span>: <span style="color:#a5d6ff">"within_30_days"</span>,',
              '        <span style="color:#a5d6ff">"applicant_id"</span>: <span style="color:#a5d6ff">"app_12345"</span>',
              '    },',
              '    <span style="color:#a5d6ff">"metadata"</span>: {',
              '        <span style="color:#a5d6ff">"model_id"</span>: <span style="color:#a5d6ff">"credit_model_v1"</span>,',
              '        <span style="color:#a5d6ff">"model_version"</span>: <span style="color:#a5d6ff">"1.0.0"</span>',
              '    }',
              '})',
              '',
              'result = response.<span style="color:#d2a8ff">json</span>()',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Decision: {result[\'decision_id\']}"</span>)',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Coverage: {result[\'coverage_percent\']}%"</span>)',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Risk Level: {result[\'risk_level\']}"</span>)',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Eval ID: {result[\'evaluation_id\']}"</span>)',
              '',
              '<span style="color:#8b949e"># Get real-time compliance snapshot</span>',
              'snapshot = requests.<span style="color:#d2a8ff">get</span>(<span style="color:#a5d6ff">"http://localhost:8000/v1/finance/snapshot"</span>).<span style="color:#d2a8ff">json</span>()',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Compliance: {snapshot[\'total_compliance_score\']}"</span>)',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Bias Score: {snapshot[\'bias_score\']}"</span>)',
              '<span style="color:#ff7b72">print</span>(f<span style="color:#a5d6ff">"Drift Score: {snapshot[\'drift_score\']}"</span>)',
            ].join('\n');
            return (
              <div className="code-block">
                <div className="code-header">
                  <span>record_credit_decision.py</span>
                </div>
                <pre dangerouslySetInnerHTML={{ __html: codeHtml }} />
              </div>
            );
          })()}
        </div>
      </section>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid var(--border)', padding: '3rem 0', marginTop: '4rem' }}>
        <div className="container">
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: '3rem' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '1.1rem', marginBottom: '1rem' }}>
                REG<span style={{ color: 'var(--accent-emerald)' }}>ENGINE</span>
              </div>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                API-first regulatory compliance for Finance. Built on cryptographic evidence chains,
                real-time analytics, and immutable audit trails.
              </p>
            </div>
            <div>
              <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>
                Product
              </h4>
              <Link href="/docs/api" className="text-re-text-muted no-underline block py-[0.2rem]">
                API Docs
              </Link>
              <Link href="/verticals/finance#api" className="text-re-text-muted no-underline block py-[0.2rem]">
                Finance API
              </Link>
            </div>
            <div>
              <h4 style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '1rem' }}>
                Verticals
              </h4>
              <Link href="/verticals/finance" className="text-re-text-muted no-underline block py-[0.2rem]">
                Finance
              </Link>
              <Link href="/" className="text-re-text-muted no-underline block py-[0.2rem]">
                All Verticals
              </Link>
            </div>
          </div>
          <div style={{ marginTop: '2rem', paddingTop: '1.5rem', borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            <span>© 2026 RegEngine Inc. All rights reserved.</span>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '0.75rem' }}>
              verify_chain.py — don't trust, verify
            </span>
          </div>
        </div>
      </footer>
    </>
  );
}
