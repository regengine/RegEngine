'use client';

import { useState, useEffect } from "react";

/* ───────────────────────── ICON COMPONENTS ───────────────────────── */

function ShieldCheck({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L4 6V12C4 16.4 7.4 20.5 12 22C16.6 20.5 20 16.4 20 12V6L12 2Z" />
      <path d="M8.5 12L11 14.5L16 9" strokeWidth="2" />
    </svg>
  );
}

function Clock({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7V12L15 15" />
    </svg>
  );
}

function Hash({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 9H20M4 15H20M10 3L8 21M16 3L14 21" />
    </svg>
  );
}

function Database({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5V19C4 20.66 7.58 22 12 22C16.42 22 20 20.66 20 19V5" />
      <path d="M4 12C4 13.66 7.58 15 12 15C16.42 15 20 13.66 20 12" />
    </svg>
  );
}

function Terminal({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 17L10 11L4 5" />
      <path d="M12 19H20" />
    </svg>
  );
}

function FileCheck({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6C5.46957 2 4.96086 2.21071 4.58579 2.58579C4.21071 2.96086 4 3.46957 4 4V20C4 20.5304 4.21071 21.0391 4.58579 21.4142C4.96086 21.7893 5.46957 22 6 22H18C18.5304 22 19.0391 21.7893 19.4142 21.4142C19.7893 21.0391 20 20.5304 20 20V8L14 2Z" />
      <path d="M9 15L11 17L15 13" />
    </svg>
  );
}

function ArrowRight({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 12H19M12 5L19 12L12 19" />
    </svg>
  );
}

function Lock({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7C7 4.24 9.24 2 12 2C14.76 2 17 4.24 17 7V11" />
    </svg>
  );
}

function ChevronDown({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9L12 15L18 9" />
    </svg>
  );
}

/* ───────────────────────── INDUSTRY DATA ───────────────────────── */

const industries = [
  {
    name: "Food & Beverage",
    status: "live" as const,
    description: "FSMA 204 traceability, FDA Food Traceability List coverage, exemption analysis, and 24-hour recall response.",
    regulations: ["FSMA 204", "21 CFR Part 1 Subpart S", "FDA FTL"],
    link: "/ftl-checker",
    linkLabel: "Try FTL Checker →",
  },
  {
    name: "Energy",
    status: "coming" as const,
    description: "NERC CIP compliance, FERC regulatory tracking, pipeline safety (49 CFR 192/195), and emissions reporting.",
    regulations: ["NERC CIP", "FERC", "EPA Clean Air Act"],
  },
  {
    name: "Nuclear",
    status: "coming" as const,
    description: "NRC 10 CFR compliance, safety analysis reports, inspection readiness, and decommissioning requirements.",
    regulations: ["10 CFR 50", "NRC RG 1.174", "IAEA Safety Standards"],
  },
  {
    name: "Finance",
    status: "coming" as const,
    description: "SEC reporting, SOX compliance, AML/KYC regulatory tracking, and cross-jurisdiction harmonization.",
    regulations: ["SOX", "Dodd-Frank", "EU DORA", "Basel III"],
  },
  {
    name: "Healthcare",
    status: "coming" as const,
    description: "HIPAA compliance monitoring, FDA device regulations, CMS conditions of participation, and state licensure tracking.",
    regulations: ["HIPAA", "21 CFR 820", "CMS CoP", "HITECH"],
  },
  {
    name: "Manufacturing",
    status: "coming" as const,
    description: "OSHA compliance, EPA environmental permits, ISO standard tracking, and supply chain due diligence.",
    regulations: ["OSHA 29 CFR 1910", "EPA RCRA", "ISO 9001/14001"],
  },
  {
    name: "Automotive",
    status: "coming" as const,
    description: "NHTSA safety standards, EPA emissions compliance, IATF 16949, and EV battery regulations.",
    regulations: ["FMVSS", "EPA Tier 3", "EU Euro 7"],
  },
  {
    name: "Aerospace",
    status: "coming" as const,
    description: "FAA airworthiness directives, ITAR/EAR export controls, AS9100 quality, and EASA harmonization.",
    regulations: ["FAR Part 21", "ITAR", "AS9100", "EASA CS"],
  },
  {
    name: "Construction",
    status: "coming" as const,
    description: "OSHA construction standards, building code tracking, environmental permits, and prevailing wage compliance.",
    regulations: ["OSHA 29 CFR 1926", "IBC/IRC", "EPA Stormwater"],
  },
  {
    name: "Gaming",
    status: "coming" as const,
    description: "State gaming commission regulations, AML compliance, responsible gaming requirements, and multi-jurisdiction licensing.",
    regulations: ["State Gaming Acts", "FinCEN", "NIGC MICS"],
  },
  {
    name: "Entertainment",
    status: "coming" as const,
    description: "FCC broadcast compliance, content rating requirements, IP/licensing regulations, and labor law (SAG-AFTRA, IATSE).",
    regulations: ["FCC Rules", "COPPA", "DMCA", "State Film Incentives"],
  },
];

/* ───────────────────────── MAIN COMPONENT ───────────────────────── */

export default function RegEngineLanding() {
  const [animateIn, setAnimateIn] = useState(false);
  const [expandedIndustry, setExpandedIndustry] = useState<string | null>(null);
  const [waitlistEmail, setWaitlistEmail] = useState("");
  const [waitlistIndustry, setWaitlistIndustry] = useState<string | null>(null);
  const [waitlistSubmitted, setWaitlistSubmitted] = useState<Record<string, string>>({});

  useEffect(() => {
    setAnimateIn(true);
  }, []);

  const handleWaitlistSubmit = (industryName: string) => {
    if (waitlistEmail) {
      setWaitlistSubmitted((prev) => ({ ...prev, [industryName]: waitlistEmail }));
      setWaitlistEmail("");
      setWaitlistIndustry(null);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#06090f",
        fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
        color: "#c8d1dc",
        overflowX: "hidden",
      }}
    >
      <link
        href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
        rel="stylesheet"
      />

      {/* ─── NOISE TEXTURE OVERLAY ─── */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          opacity: 0.015,
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
          backgroundSize: "128px 128px",
          pointerEvents: "none",
          zIndex: 1,
        }}
      />


      {/* ─── HERO ─── */}
      <section
        style={{
          position: "relative",
          zIndex: 2,
          maxWidth: "1120px",
          margin: "0 auto",
          padding: "100px 24px 80px",
        }}
      >
        {/* Gradient glow */}
        <div
          style={{
            position: "absolute",
            top: "-80px",
            left: "50%",
            transform: "translateX(-50%)",
            width: "600px",
            height: "400px",
            background: "radial-gradient(ellipse, rgba(16,185,129,0.06) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />

        <div
          style={{
            opacity: animateIn ? 1 : 0,
            transform: animateIn ? "translateY(0)" : "translateY(20px)",
            transition: "all 0.8s cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          {/* Regulatory badge */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "6px 14px",
              background: "rgba(16,185,129,0.08)",
              border: "1px solid rgba(16,185,129,0.15)",
              borderRadius: "20px",
              marginBottom: "28px",
              fontSize: "12px",
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 500,
              color: "#10b981",
            }}
          >
            <span style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "#10b981",
              animation: "pulse 2s ease infinite",
            }} />
            FSMA 204 Deadline: July 20, 2028
          </div>

          <h1
            style={{
              fontSize: "clamp(36px, 5vw, 56px)",
              fontWeight: 700,
              color: "#f8fafc",
              lineHeight: 1.1,
              margin: "0 0 20px",
              maxWidth: "700px",
              letterSpacing: "-0.02em",
            }}
          >
            FDA wants your
            <br />
            traceability data
            <br />
            <span style={{ color: "#10b981" }}>in 24 hours.</span>
          </h1>

          <p
            style={{
              fontSize: "18px",
              color: "#64748b",
              lineHeight: 1.6,
              margin: "0 0 40px",
              maxWidth: "520px",
            }}
          >
            Most food companies can't deliver. RegEngine gives you API-first
            FSMA 204 compliance with cryptographic proof that your data is
            accurate — verifiable by anyone, including the FDA.
          </p>

          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <a
              href="/ftl-checker"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "14px 28px",
                background: "#10b981",
                color: "#06090f",
                borderRadius: "8px",
                fontSize: "15px",
                fontWeight: 600,
                textDecoration: "none",
                transition: "all 0.2s",
              }}
            >
              Check If You're Covered
              <ArrowRight size={16} />
            </a>
            <a
              href="/retailer-readiness"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "8px",
                padding: "14px 28px",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#c8d1dc",
                borderRadius: "8px",
                fontSize: "15px",
                fontWeight: 500,
                textDecoration: "none",
                transition: "all 0.2s",
              }}
            >
              Retailer Readiness →
            </a>
          </div>
        </div>
      </section>

      {/* ─── GS1 EPCIS ANNOUNCEMENT BANNER ─── */}
      <section
        style={{
          position: "relative",
          zIndex: 2,
          background: "linear-gradient(90deg, rgba(16,185,129,0.08) 0%, rgba(59,130,246,0.08) 100%)",
          borderTop: "1px solid rgba(16,185,129,0.2)",
          borderBottom: "1px solid rgba(16,185,129,0.2)",
        }}
      >
        <div
          style={{
            maxWidth: "1120px",
            margin: "0 auto",
            padding: "16px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "16px",
            flexWrap: "wrap",
          }}
        >
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              padding: "4px 12px",
              background: "rgba(16,185,129,0.15)",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 700,
              color: "#10b981",
              letterSpacing: "0.05em",
            }}
          >
            NEW
          </div>
          <span style={{ color: "#e2e8f0", fontSize: "14px", fontWeight: 500 }}>
            Now supporting <strong style={{ color: "#10b981" }}>GS1 EPCIS 2.0</strong> for major retailer supplier automation
          </span>
          <a
            href="/ftl-checker"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              padding: "6px 12px",
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: "4px",
              fontSize: "12px",
              color: "#c8d1dc",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Check Your Coverage →
          </a>
        </div>
      </section>

      {/* ─── PROOF STRIP ─── */}
      <section
        style={{
          position: "relative",
          zIndex: 2,
          borderTop: "1px solid rgba(255,255,255,0.04)",
          borderBottom: "1px solid rgba(255,255,255,0.04)",
          background: "rgba(255,255,255,0.01)",
        }}
      >
        <div
          style={{
            maxWidth: "1120px",
            margin: "0 auto",
            padding: "0 24px",
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "0",
          }}
        >
          {[
            { value: "23", label: "FDA categories", sublabel: "verified against FTL" },
            { value: "EPCIS 2.0", label: "GS1 Export", sublabel: "Retailer-ready" },
            { value: "SHA-256", label: "Audit trail", sublabel: "cryptographic hashing" },
            { value: "24hr", label: "FDA response", sublabel: "recall-ready export" },
          ].map((stat, i) => (
            <div
              key={i}
              style={{
                padding: "28px 20px",
                borderRight: i < 3 ? "1px solid rgba(255,255,255,0.04)" : "none",
                textAlign: "center",
                opacity: animateIn ? 1 : 0,
                transform: animateIn ? "translateY(0)" : "translateY(10px)",
                transition: `all 0.6s ease ${300 + i * 100}ms`,
              }}
            >
              <div
                style={{
                  fontSize: "24px",
                  fontWeight: 700,
                  color: "#10b981",
                  fontFamily: stat.value.includes("-") ? "'JetBrains Mono', monospace" : "inherit",
                  marginBottom: "4px",
                }}
              >
                {stat.value}
              </div>
              <div style={{ fontSize: "13px", fontWeight: 600, color: "#e2e8f0", marginBottom: "2px" }}>
                {stat.label}
              </div>
              <div style={{ fontSize: "11px", color: "#475569", fontFamily: "'JetBrains Mono', monospace" }}>
                {stat.sublabel}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ─── WHAT REGENGINE DOES ─── */}
      <section id="product" style={{ position: "relative", zIndex: 2, maxWidth: "1120px", margin: "0 auto", padding: "100px 24px" }}>
        <div style={{ marginBottom: "56px" }}>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 500,
              color: "#475569",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              display: "block",
              marginBottom: "12px",
            }}
          >
            How it works
          </span>
          <h2
            style={{
              fontSize: "32px",
              fontWeight: 700,
              color: "#f1f5f9",
              margin: "0 0 12px",
              letterSpacing: "-0.01em",
            }}
          >
            Compliance you can verify yourself
          </h2>
          <p style={{ fontSize: "16px", color: "#64748b", margin: 0, maxWidth: "520px", lineHeight: 1.6 }}>
            We don't ask you to trust our database. We give you the math and let you check it.
            Every fact is hashed, versioned, and independently auditable.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
          {[
            {
              icon: <Database size={22} />,
              title: "Ingest & Normalize",
              description: "Regulatory documents are fetched, parsed, and broken into structured facts with provenance tracking.",
              detail: "Sources: FDA.gov, eCFR, Federal Register",
            },
            {
              icon: <Hash size={22} />,
              title: "Hash & Version",
              description: "Every extracted fact gets a SHA-256 hash. Updates create new versions with immutable lineage — like git for regulations.",
              detail: "Tamper-proof, auditor-verifiable",
            },
            {
              icon: <ShieldCheck size={22} />,
              title: "Verify & Export",
              description: "Run our open verification script to confirm data integrity. Export FDA-ready reports in 24-hour recall format.",
              detail: "verify_chain.py — zero trust required",
            },
          ].map((card, i) => (
            <div
              key={i}
              style={{
                padding: "28px",
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.05)",
                borderRadius: "12px",
                transition: "all 0.3s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = "rgba(16,185,129,0.2)";
                e.currentTarget.style.background = "rgba(16,185,129,0.03)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = "rgba(255,255,255,0.05)";
                e.currentTarget.style.background = "rgba(255,255,255,0.02)";
              }}
            >
              <div style={{ color: "#10b981", marginBottom: "16px" }}>{card.icon}</div>
              <h3 style={{ fontSize: "16px", fontWeight: 600, color: "#e2e8f0", margin: "0 0 8px" }}>
                {card.title}
              </h3>
              <p style={{ fontSize: "14px", color: "#64748b", margin: "0 0 16px", lineHeight: 1.5 }}>
                {card.description}
              </p>
              <span
                style={{
                  fontSize: "11px",
                  fontFamily: "'JetBrains Mono', monospace",
                  color: "#475569",
                  padding: "4px 8px",
                  background: "rgba(255,255,255,0.03)",
                  borderRadius: "4px",
                }}
              >
                {card.detail}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ─── LIVE TOOLS ─── */}
      <section
        style={{
          position: "relative",
          zIndex: 2,
          background: "rgba(16,185,129,0.03)",
          borderTop: "1px solid rgba(16,185,129,0.08)",
          borderBottom: "1px solid rgba(16,185,129,0.08)",
        }}
      >
        <div style={{ maxWidth: "1120px", margin: "0 auto", padding: "60px 24px" }}>
          <div style={{ textAlign: "center", marginBottom: "40px" }}>
            <span
              style={{
                fontSize: "11px",
                fontFamily: "'JetBrains Mono', monospace",
                fontWeight: 500,
                color: "#10b981",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
              }}
            >
              Live now — no signup required
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
            {[
              {
                title: "FTL Coverage Checker",
                description: "Check if your products are on the FDA Food Traceability List. Includes all 23 categories with exclusion notes and CFR citations.",
                icon: <FileCheck size={20} />,
                href: "/ftl-checker",
                cta: "Check Your Products →",
                badge: "Free",
              },
              {
                title: "Supply Chain Explorer",
                description: "Explore 3 real-world recall scenarios with 430 cryptographically verified traceability records across dairy, seafood, and produce supply chains.",
                icon: <Database size={20} />,
                href: "/demo/supply-chains",
                cta: "Explore Supply Chains →",
                badge: "New",
              },
              {
                title: "Retailer Readiness Assessment",
                description: "Interactive FSMA 204 compliance checklist. Self-assess your gaps and get a founder-led analysis of what needs fixing.",
                icon: <ShieldCheck size={20} />,
                href: "/retailer-readiness",
                cta: "Assess Your Readiness →",
                badge: "Free",
              },
            ].map((tool, i) => (
              <a
                key={i}
                href={tool.href}
                style={{
                  display: "block",
                  padding: "28px",
                  background: "rgba(6,9,15,0.6)",
                  border: "1px solid rgba(255,255,255,0.06)",
                  borderRadius: "12px",
                  textDecoration: "none",
                  transition: "all 0.3s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = "rgba(16,185,129,0.3)";
                  e.currentTarget.style.transform = "translateY(-2px)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
                  e.currentTarget.style.transform = "translateY(0)";
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
                  <span style={{ color: "#10b981" }}>{tool.icon}</span>
                  <span style={{ fontSize: "16px", fontWeight: 600, color: "#f1f5f9" }}>{tool.title}</span>
                  <span
                    style={{
                      marginLeft: "auto",
                      fontSize: "10px",
                      fontWeight: 600,
                      color: "#10b981",
                      background: "rgba(16,185,129,0.1)",
                      padding: "3px 8px",
                      borderRadius: "4px",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {tool.badge}
                  </span>
                </div>
                <p style={{ fontSize: "14px", color: "#64748b", margin: "0 0 16px", lineHeight: 1.5 }}>
                  {tool.description}
                </p>
                <span style={{ fontSize: "13px", fontWeight: 600, color: "#10b981" }}>{tool.cta}</span>
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* ─── INDUSTRY VERTICALS ─── */}
      <section id="industries" style={{ position: "relative", zIndex: 2, maxWidth: "1120px", margin: "0 auto", padding: "100px 24px" }}>
        <div style={{ marginBottom: "48px" }}>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 500,
              color: "#475569",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              display: "block",
              marginBottom: "12px",
            }}
          >
            Industry Verticals
          </span>
          <h2 style={{ fontSize: "32px", fontWeight: 700, color: "#f1f5f9", margin: "0 0 12px" }}>
            One platform, every regulated industry
          </h2>
          <p style={{ fontSize: "16px", color: "#64748b", margin: 0, maxWidth: "520px", lineHeight: 1.6 }}>
            We're building RegEngine to work across every industry that deals with regulatory
            compliance. Food & Beverage is live. The rest are coming.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {industries.map((industry) => {
            const isExpanded = expandedIndustry === industry.name;
            const isLive = industry.status === "live";
            const hasSubmitted = waitlistSubmitted[industry.name];

            return (
              <div
                key={industry.name}
                style={{
                  border: `1px solid ${isLive ? "rgba(16,185,129,0.15)" : "rgba(255,255,255,0.04)"}`,
                  borderRadius: "10px",
                  overflow: "hidden",
                  background: isLive ? "rgba(16,185,129,0.03)" : "rgba(255,255,255,0.01)",
                  transition: "all 0.2s ease",
                }}
              >
                <button
                  onClick={() => setExpandedIndustry(isExpanded ? null : industry.name)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    padding: "16px 20px",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    color: "inherit",
                    fontFamily: "inherit",
                  }}
                >
                  <span
                    style={{
                      fontSize: "14px",
                      fontWeight: 600,
                      color: isLive ? "#10b981" : "#c8d1dc",
                      flex: 1,
                    }}
                  >
                    {industry.name}
                  </span>

                  {isLive ? (
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 600,
                        color: "#10b981",
                        background: "rgba(16,185,129,0.12)",
                        padding: "3px 10px",
                        borderRadius: "10px",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                      }}
                    >
                      ✓ Live
                    </span>
                  ) : hasSubmitted ? (
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 600,
                        color: "#60a5fa",
                        background: "rgba(96,165,250,0.1)",
                        padding: "3px 10px",
                        borderRadius: "10px",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                      }}
                    >
                      ✓ On waitlist
                    </span>
                  ) : (
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 500,
                        color: "#475569",
                        background: "rgba(255,255,255,0.03)",
                        padding: "3px 10px",
                        borderRadius: "10px",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                      }}
                    >
                      Coming Soon
                    </span>
                  )}

                  <span
                    style={{
                      color: "#475569",
                      transition: "transform 0.2s",
                      transform: isExpanded ? "rotate(180deg)" : "rotate(0deg)",
                    }}
                  >
                    <ChevronDown size={16} />
                  </span>
                </button>

                {isExpanded && (
                  <div
                    style={{
                      padding: "0 20px 20px",
                      animation: "fadeSlideIn 0.3s ease forwards",
                    }}
                  >
                    <p style={{ fontSize: "14px", color: "#94a3b8", margin: "0 0 14px", lineHeight: 1.6 }}>
                      {industry.description}
                    </p>

                    <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginBottom: "16px" }}>
                      {industry.regulations.map((reg) => (
                        <span
                          key={reg}
                          style={{
                            fontSize: "11px",
                            fontFamily: "'JetBrains Mono', monospace",
                            color: "#64748b",
                            background: "rgba(255,255,255,0.04)",
                            padding: "4px 10px",
                            borderRadius: "4px",
                            border: "1px solid rgba(255,255,255,0.04)",
                          }}
                        >
                          {reg}
                        </span>
                      ))}
                    </div>

                    {isLive && industry.link ? (
                      <a
                        href={industry.link}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "13px",
                          fontWeight: 600,
                          color: "#10b981",
                          textDecoration: "none",
                        }}
                      >
                        {industry.linkLabel}
                      </a>
                    ) : hasSubmitted ? (
                      <p style={{ fontSize: "13px", color: "#60a5fa", margin: 0 }}>
                        You're on the list. We'll email {hasSubmitted} when this vertical goes live.
                      </p>
                    ) : waitlistIndustry === industry.name ? (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <input
                          type="email"
                          placeholder="you@company.com"
                          value={waitlistEmail}
                          onChange={(e) => setWaitlistEmail(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && handleWaitlistSubmit(industry.name)}
                          autoFocus
                          style={{
                            flex: 1,
                            padding: "10px 14px",
                            background: "rgba(0,0,0,0.3)",
                            border: "1px solid rgba(255,255,255,0.08)",
                            borderRadius: "6px",
                            color: "#e2e8f0",
                            fontSize: "13px",
                            outline: "none",
                            fontFamily: "inherit",
                            maxWidth: "280px",
                          }}
                        />
                        <button
                          onClick={() => handleWaitlistSubmit(industry.name)}
                          disabled={!waitlistEmail}
                          style={{
                            padding: "10px 18px",
                            background: waitlistEmail ? "#2563eb" : "rgba(255,255,255,0.04)",
                            color: waitlistEmail ? "#fff" : "#475569",
                            border: "none",
                            borderRadius: "6px",
                            fontSize: "13px",
                            fontWeight: 600,
                            cursor: waitlistEmail ? "pointer" : "default",
                            fontFamily: "inherit",
                          }}
                        >
                          Join Waitlist
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setWaitlistIndustry(industry.name)}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          fontSize: "13px",
                          fontWeight: 600,
                          color: "#60a5fa",
                          background: "transparent",
                          border: "none",
                          cursor: "pointer",
                          padding: 0,
                          fontFamily: "inherit",
                        }}
                      >
                        Get Early Access →
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── DEVELOPER SECTION ─── */}
      <section
        id="developers"
        style={{
          position: "relative",
          zIndex: 2,
          borderTop: "1px solid rgba(255,255,255,0.04)",
          background: "rgba(255,255,255,0.01)",
        }}
      >
        <div style={{ maxWidth: "1120px", margin: "0 auto", padding: "80px 24px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "48px", alignItems: "center" }}>
            <div>
              <span
                style={{
                  fontSize: "11px",
                  fontFamily: "'JetBrains Mono', monospace",
                  fontWeight: 500,
                  color: "#475569",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  display: "block",
                  marginBottom: "12px",
                }}
              >
                For Developers
              </span>
              <h2 style={{ fontSize: "28px", fontWeight: 700, color: "#f1f5f9", margin: "0 0 12px" }}>
                API-first by design
              </h2>
              <p style={{ fontSize: "15px", color: "#64748b", margin: "0 0 24px", lineHeight: 1.6 }}>
                RegEngine is built for integration, not portals. Plug compliance data directly
                into your WMS, ERP, or supply chain system with a single API call.
              </p>
              <div style={{ display: "flex", gap: "12px" }}>
                <a
                  href="/docs"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "10px 20px",
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: "6px",
                    color: "#c8d1dc",
                    fontSize: "13px",
                    fontWeight: 500,
                    textDecoration: "none",
                  }}
                >
                  <Terminal size={14} /> API Docs
                </a>
              </div>
            </div>

            {/* Code block */}
            <div
              style={{
                background: "rgba(0,0,0,0.4)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: "10px",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  padding: "10px 16px",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#ef4444", opacity: 0.6 }} />
                <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#f59e0b", opacity: 0.6 }} />
                <div style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981", opacity: 0.6 }} />
                <span style={{ marginLeft: "8px", fontSize: "11px", color: "#475569", fontFamily: "'JetBrains Mono', monospace" }}>
                  verify_compliance.sh
                </span>
              </div>
              <pre
                style={{
                  padding: "20px",
                  margin: 0,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: "12px",
                  lineHeight: 1.7,
                  color: "#94a3b8",
                  overflow: "auto",
                }}
              >
                <span style={{ color: "#475569" }}>$ </span>
                <span style={{ color: "#c8d1dc" }}>curl</span>
                {" "}<span style={{ color: "#10b981" }}>api.regengine.co/v1/verify/doc_a1b2c3</span>
                {"\n\n"}
                <span style={{ color: "#475569" }}>{"{"}</span>
                {"\n  "}<span style={{ color: "#60a5fa" }}>"document_id"</span>: <span style={{ color: "#fbbf24" }}>"doc_a1b2c3"</span>,
                {"\n  "}<span style={{ color: "#60a5fa" }}>"status"</span>: <span style={{ color: "#fbbf24" }}>"verified"</span>,
                {"\n  "}<span style={{ color: "#60a5fa" }}>"hashes"</span>: {"{ "}<span style={{ color: "#60a5fa" }}>"content_sha256"</span>: <span style={{ color: "#fbbf24" }}>"a3f2..."</span>{" }"},
                {"\n  "}<span style={{ color: "#60a5fa" }}>"verified_at"</span>: <span style={{ color: "#fbbf24" }}>"2026-02-08T20:15:00Z"</span>
                {"\n"}<span style={{ color: "#475569" }}>{"}"}</span>
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* ─── FINAL CTA ─── */}
      <section
        style={{
          position: "relative",
          zIndex: 2,
          maxWidth: "1120px",
          margin: "0 auto",
          padding: "80px 24px",
          textAlign: "center",
        }}
      >
        <h2
          style={{
            fontSize: "28px",
            fontWeight: 700,
            color: "#f1f5f9",
            margin: "0 0 12px",
          }}
        >
          Stop trusting. Start verifying.
        </h2>
        <p style={{ fontSize: "16px", color: "#64748b", margin: "0 0 32px", maxWidth: "420px", marginLeft: "auto", marginRight: "auto", lineHeight: 1.6 }}>
          Check if your products are on the FDA Food Traceability List.
          Free, no signup, takes 2 minutes.
        </p>
        <a
          href="/ftl-checker"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "16px 32px",
            background: "#10b981",
            color: "#06090f",
            borderRadius: "8px",
            fontSize: "16px",
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          Try the FTL Checker
          <ArrowRight size={18} />
        </a>
      </section>

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        input::placeholder { color: #475569; }
        * { box-sizing: border-box; margin: 0; }
        a:hover { opacity: 0.9; }
      `}</style>
    </div>
  );
}
