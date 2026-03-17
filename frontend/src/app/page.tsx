import Link from "next/link";
import { ArrowRight, Leaf, ShieldCheck, BookOpen, Thermometer } from "lucide-react";
import { getTranslations } from "next-intl/server";

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const EVIDENCE_KEYS = [
  { value: "23", key: "evidence.categories" },
  { value: "1", key: "evidence.apiCall" },
  { value: "24hr", key: "evidence.recallWindow" },
  { value: "EPCIS 2.0", key: "evidence.nativeFormat" },
];

const FREE_TOOLS = [
  { titleKey: "freeTools.ftlChecker", descKey: "freeTools.ftlDesc", href: "/tools/ftl-checker", tagKey: null, icon: Leaf },
  { titleKey: "freeTools.retailerReadiness", descKey: "freeTools.retailerDesc", href: "/retailer-readiness", tagKey: "freeTools.popular", icon: ShieldCheck },
  { titleKey: "freeTools.complianceGuide", descKey: "freeTools.guideDesc", href: "/fsma-204", tagKey: null, icon: BookOpen },
  { titleKey: "freeTools.coldChain", descKey: "freeTools.coldChainDesc", href: "/tools/drill-simulator", tagKey: null, icon: Thermometer },
];

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default async function RegEngineLanding() {
  const t = await getTranslations();
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

      {/* ── HERO ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-12 sm:pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 lg:gap-12 items-center">

          {/* Left — copy */}
          <div>
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-5">
              {t('hero.badge')}
            </p>
            <h1 className="font-serif text-[clamp(1.75rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
              {t('hero.title')}{" "}
              <em className="font-medium text-[var(--re-brand-dark)]">{t('hero.titleEmphasis')}</em>
            </h1>
            <p className="text-[1.05rem] text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[480px]">
              {t('hero.subtitle')}
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <Link
                href="/alpha"
                className="group relative inline-flex items-center justify-center gap-2.5 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.3)] active:translate-y-0 active:shadow-[0_2px_8px_rgba(16,185,129,0.2)] overflow-hidden min-h-[48px]"
              >
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
                <span className="relative">{t('hero.ctaPrimary')}</span>
                <ArrowRight className="relative h-4 w-4 transition-transform duration-300 ease-out group-hover:translate-x-1" />
              </Link>
              <Link
                href="/retailer-readiness"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(16,185,129,0.08)] min-h-[48px]"
              >
                {t('hero.ctaSecondary')}
              </Link>
            </div>
          </div>

          {/* Right — Walmart audit scenario card */}
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden shadow-re-md">
            {/* Card header */}
            <div className="px-4 sm:px-5 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[var(--re-warning)] flex-shrink-0" />
              <span className="font-mono text-[0.65rem] sm:text-[0.72rem] font-medium text-[var(--re-text-muted)] tracking-wide">
                {t('auditCard.header')}
              </span>
            </div>

            {/* Card body */}
            <div className="p-4 sm:p-5">
              <p className="font-serif text-[0.95rem] sm:text-[1.05rem] font-medium text-[var(--re-text-primary)] leading-snug mb-5">
                &ldquo;{t('auditCard.body')}&rdquo;
              </p>

              <div className="border-t border-[var(--re-surface-border)] pt-4 mt-4">
                <p className="font-mono text-[0.65rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-3">
                  {t('auditCard.responseLabel')}
                </p>
                <div className="space-y-2.5">
                  {[
                    { label: t('auditCard.ctesFound'), value: "12 of 12", badge: t('auditCard.passed'), badgeColor: "emerald" },
                    { label: t('auditCard.coverage'), value: "100%", badge: t('auditCard.complete'), badgeColor: "emerald" },
                    { label: t('auditCard.format'), value: "EPCIS 2.0 + PDF", badge: t('auditCard.exportReady'), badgeColor: "blue" },
                    { label: t('auditCard.cryptoVerification'), value: "SHA-256", badge: t('auditCard.verified'), badgeColor: "emerald" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-2">
                      <span className="text-[0.75rem] sm:text-[0.8rem] text-[var(--re-text-secondary)] shrink-0">{row.label}</span>
                      <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                        <span className="font-mono text-[0.75rem] sm:text-[0.8rem] font-medium text-[var(--re-brand-dark)] truncate">{row.value}</span>
                        <span className={`text-[0.55rem] sm:text-[0.6rem] font-semibold px-1.5 py-0.5 rounded-full border whitespace-nowrap ${
                          row.badgeColor === "blue"
                            ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        }`}>{row.badge}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Card footer */}
            <div className="px-4 sm:px-5 py-3 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2 sm:gap-3">
              <span className="text-[0.8rem] text-[var(--re-text-muted)] hidden sm:inline">
                {t('auditCard.footerReady')}
              </span>
              <Link
                href="/alpha"
                className="group font-mono text-[0.72rem] font-semibold bg-[var(--re-brand)] text-white px-4 py-2.5 rounded-md transition-all duration-300 ease-out hover:bg-[var(--re-brand-dark)] hover:-translate-y-[1px] hover:shadow-[0_4px_12px_rgba(16,185,129,0.25)] text-center min-h-[44px] flex items-center justify-center"
              >
                {t('hero.ctaPrimary')} <span className="inline-block transition-transform duration-300 group-hover:translate-x-0.5 ml-1">→</span>
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── EVIDENCE STRIP ── */}
      <div className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1100px] mx-auto px-4 sm:px-6 py-6 sm:py-8 grid grid-cols-2 sm:flex sm:flex-wrap items-center justify-between gap-4 sm:gap-6">
          {EVIDENCE_KEYS.map((e) => (
            <div key={e.key} className="flex items-baseline gap-2">
              <span className="font-serif text-[clamp(1.25rem,3vw,1.75rem)] font-bold text-[var(--re-brand-dark)] tracking-tight">
                {e.value}
              </span>
              <span className="text-[0.75rem] sm:text-[0.85rem] text-[var(--re-text-secondary)] max-w-[180px] leading-snug">
                {t(e.key)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* ── FREE TOOLS ── */}
      <section className="max-w-[1100px] mx-auto px-4 sm:px-6 py-12 sm:py-20">
        <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand)] uppercase tracking-[0.08em] mb-4">
          {t('freeTools.badge')}
        </p>
        <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
          {t('freeTools.title')}
        </h2>
        <p className="text-[1.05rem] text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed mb-10">
          {t('freeTools.subtitle')}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {FREE_TOOLS.map((tool) => (
            <Link
              key={tool.titleKey}
              href={tool.href}
              className="group flex items-start gap-3 sm:gap-4 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-4 sm:p-5 shadow-sm transition-all duration-300 hover:border-[var(--re-brand)] hover:shadow-re-md hover:-translate-y-0.5 min-h-[72px]"
            >
              <div className="w-11 h-11 sm:w-10 sm:h-10 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                <tool.icon className="h-5 w-5 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-serif text-[0.95rem] sm:text-[1.05rem] font-medium text-[var(--re-text-primary)]">
                    {t(tool.titleKey)}
                  </h3>
                  {tool.tagKey && (
                    <span className="font-mono text-[0.6rem] font-medium text-[var(--re-brand)] bg-[var(--re-brand-muted)] px-2 py-0.5 rounded whitespace-nowrap">
                      {t(tool.tagKey)}
                    </span>
                  )}
                </div>
                <p className="text-[0.8rem] sm:text-[0.85rem] text-[var(--re-text-secondary)] leading-relaxed">
                  {t(tool.descKey)}
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-[var(--re-text-muted)] mt-1.5 flex-shrink-0 group-hover:translate-x-1 group-hover:text-[var(--re-brand)] transition-all duration-300" />
            </Link>
          ))}
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="bg-[var(--re-text-primary)] text-white py-12 sm:py-20 px-4 sm:px-6">
        <div className="max-w-[1100px] mx-auto text-center">
          <p className="font-mono text-[0.72rem] font-medium text-[var(--re-brand-light)] uppercase tracking-[0.08em] mb-4">
            {t('cta.badge')}
          </p>
          <h2 className="font-serif text-[1.75rem] sm:text-[2.25rem] font-bold text-white tracking-tight leading-tight mb-4 max-w-[640px] mx-auto">
            {t('cta.title')}
          </h2>
          <p className="text-[1.05rem] text-[#aaa] max-w-[560px] mx-auto leading-relaxed mb-8">
            {t('cta.subtitle')}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/retailer-readiness"
              className="group relative inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-semibold transition-all duration-300 ease-out hover:bg-[#0BAE78] hover:-translate-y-[2px] hover:shadow-[0_8px_30px_rgba(16,185,129,0.35)] active:translate-y-0 overflow-hidden min-h-[48px]"
            >
              <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.08] to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-700 ease-in-out" />
              <span className="relative">{t('cta.primary')}</span>
            </Link>
            <Link
              href="/alpha"
              className="inline-flex items-center justify-center gap-2 border border-[#444] text-white px-7 py-3.5 rounded-xl text-[0.95rem] font-medium transition-all duration-300 ease-out hover:border-[var(--re-brand)] hover:text-[var(--re-brand-light)] hover:-translate-y-[2px] min-h-[48px]"
            >
              {t('cta.secondary')}
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
