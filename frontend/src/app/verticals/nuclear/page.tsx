'use client';

import Link from 'next/link';
import styles from './nuclear.module.css';

export default function NuclearPage() {
  return (
    <div className={styles.nuclearPage}>
      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={`${styles.container} ${styles.navInner}`}>
          <div className={styles.navLogo}>
            REG<span>ENGINE</span>
          </div>
          <div className={styles.navLinks}>
            <a href="#overview" className={styles.navLink}>
              Overview
            </a>
            <a href="#smr" className={styles.navLink}>
              SMR Challenges
            </a>
            <a href="#framework" className={styles.navLink}>
              Regulations
            </a>
            <a href="#api" className={styles.navLink}>
              API
            </a>
            <Link href="/api-keys" className={`${styles.btn} ${styles.btnPrimary}`}>
              Get API Key
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className={styles.hero} id="overview">
        <div className={styles.container}>
          <div className={styles.heroEyebrow}>NUCLEAR COMPLIANCE API</div>
          <h1>
            Compliance infrastructure for the{' '}
            <span className={styles.heroHighlight}>next generation</span> of nuclear
          </h1>
          <p className={styles.heroSub}>
            Tamper-evident evidence chains for SMR licensing, multi-module QA coordination, and
            ITAAC closure tracking — delivered as an API.
          </p>

          <div className={styles.heroRotate}>
            <span className={styles.rotateItem}>
              → Track 924 ITAAC items across 12 modules. Programmatically.
            </span>
            <span className={styles.rotateItem}>
              → Design Certification evidence chains that survive NRC review.
            </span>
            <span className={styles.rotateItem}>
              → Legal discovery export in minutes, not weeks.
            </span>
            <span className={styles.rotateItem}>
              → First NRC-compliant evidence record in 5 minutes. Not 5 weeks.
            </span>
          </div>

          <div className={styles.heroActions}>
            <Link href="/api-keys" className={`${styles.btn} ${styles.btnPrimary}`}>
              Get API Key →
            </Link>
            <Link href="/docs/nuclear" className={`${styles.btn} ${styles.btnSecondary}`}>
              Read the Docs
            </Link>
          </div>

          <div className={styles.heroStats}>
            <div className={styles.heroStat}>
              <span className={styles.mono}>5 min</span>
              <span>Quickstart</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.mono}>Part 52</span>
              <span>Design Cert Ready</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.mono}>SHA-256</span>
              <span>Hash Verification</span>
            </div>
            <div className={styles.heroStat}>
              <span className={styles.mono}>60+ yr</span>
              <span>Retention Architecture</span>
            </div>
          </div>
        </div>
      </section>

      {/* SMR-Specific Challenges */}
      <section className={styles.section} id="smr">
        <div className={styles.container}>
          <div className={styles.sectionLabel}>Why SMRs Have It Harder</div>
          <h2 className={styles.sectionTitle}>Small reactors. Outsized compliance burden.</h2>
          <p className={styles.sectionSubtitle}>
            Advanced reactors face every legacy compliance requirement plus first-of-a-kind
            licensing complexity that traditional plants never encountered.
          </p>

          <div className={styles.smrGrid}>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeHigh} ${styles.severity}`}>HIGH</span>
              <h3>First-of-a-Kind Licensing</h3>
              <p>
                No precedent documentation to reference. Every evidence chain is novel. Design
                Certification under 10 CFR Part 52 requires demonstrating compliance against
                criteria that were written for gigawatt-scale PWRs — not modular architectures.
              </p>
            </div>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeHigh} ${styles.severity}`}>HIGH</span>
              <h3>Multi-Module QA Coordination</h3>
              <p>
                A 12-module VOYGR-style plant creates N modules × M shared systems of documentation.
                Each module has independent safety records, but shared balance-of-plant systems
                create cross-reference dependencies that compound exponentially.
              </p>
            </div>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeHigh} ${styles.severity}`}>HIGH</span>
              <h3>ITAAC Closure at Scale</h3>
              <p>
                Hundreds of Inspections, Tests, Analyses, and Acceptance Criteria must be closed
                before fuel load — each requiring cryptographically verifiable evidence. A single
                unresolved ITAAC blocks your entire commissioning timeline.
              </p>
            </div>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeMedium} ${styles.severity}`}>
                MEDIUM
              </span>
              <h3>Factory Fabrication QA</h3>
              <p>
                SMR economics depend on factory-built modules shipped to site. Your supply chain QA
                now extends to off-site manufacturing facilities — each needing its own 10 CFR 50
                Appendix B evidence chain tied back to the Combined License.
              </p>
            </div>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeMedium} ${styles.severity}`}>
                MEDIUM
              </span>
              <h3>Accelerated Timelines</h3>
              <p>
                SMR business cases assume faster licensing than legacy plants. You can&apos;t afford
                36-month license amendments. Every week of NRC back-and-forth on documentation gaps
                erodes the economic advantage modular design was supposed to deliver.
              </p>
            </div>
            <div className={styles.smrCard}>
              <span className={`${styles.badge} ${styles.badgeNew} ${styles.severity}`}>NEW</span>
              <h3>Risk-Informed Classification</h3>
              <p>
                10 CFR 50.69 lets SMR vendors reduce documentation burden on non-safety-significant
                SSCs — but only if you can prove the categorization with auditable evidence. The
                cost savings require upfront compliance investment.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ITAAC Tracker Preview */}
      <section className={styles.section} style={{ paddingTop: 0 }}>
        <div className={styles.container}>
          <div className={styles.sectionLabel}>ITAAC Closure Tracking</div>
          <h2 className={styles.sectionTitle}>
            Every acceptance criterion. Every module. One API.
          </h2>
          <p className={styles.sectionSubtitle}>
            Model projection: a 6-module SMR deployment generates ~4,200 evidence records during
            ITAAC closure. All searchable in &lt;30 seconds.
          </p>

          <div className={styles.itaacDemo}>
            <div className={styles.itaacHeader}>
              <h4>ITAAC Status — VOYGR-6 Demo Plant</h4>
              <span className={`${styles.badge} ${styles.badgeNew}`}>DEMO</span>
            </div>
            <table className={styles.itaacTable}>
              <thead>
                <tr>
                  <th>ITAAC ID</th>
                  <th>Module</th>
                  <th>System</th>
                  <th>Description</th>
                  <th>Status</th>
                  <th>Evidence Hash</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className={styles.mono}>ITAAC-2.1.01</td>
                  <td>NPM-01</td>
                  <td>RCS</td>
                  <td>Reactor coolant system pressure boundary integrity test</td>
                  <td>
                    <span className={`${styles.statusDot} ${styles.statusClosed}`}></span>Closed
                  </td>
                  <td className={`${styles.mono} text-xs text-re-text-muted`}>
                    a3f8c9…d41e
                  </td>
                </tr>
                <tr>
                  <td className={styles.mono}>ITAAC-2.1.02</td>
                  <td>NPM-01</td>
                  <td>DHRS</td>
                  <td>Decay heat removal system functional test</td>
                  <td>
                    <span className={`${styles.statusDot} ${styles.statusClosed}`}></span>Closed
                  </td>
                  <td className={`${styles.mono} text-xs text-re-text-muted`}>
                    7b2e01…f83a
                  </td>
                </tr>
                <tr>
                  <td className={styles.mono}>ITAAC-3.4.07</td>
                  <td>NPM-02</td>
                  <td>ECCS</td>
                  <td>Emergency core cooling valve stroke time verification</td>
                  <td>
                    <span className={`${styles.statusDot} ${styles.statusOpen}`}></span>Open
                  </td>
                  <td className={`${styles.mono} text-xs text-re-text-muted`}>
                    —
                  </td>
                </tr>
                <tr>
                  <td className={styles.mono}>ITAAC-5.2.01</td>
                  <td>Shared</td>
                  <td>BOP</td>
                  <td>Balance-of-plant turbine island seismic qualification</td>
                  <td>
                    <span className={`${styles.statusDot} ${styles.statusBlocked}`}></span>Blocked
                  </td>
                  <td className={`${styles.mono} text-xs text-re-text-muted`}>
                    —
                  </td>
                </tr>
                <tr>
                  <td className={styles.mono}>ITAAC-6.1.03</td>
                  <td>NPM-03</td>
                  <td>I&C</td>
                  <td>Module protection system independence verification</td>
                  <td>
                    <span className={`${styles.statusDot} ${styles.statusOpen}`}></span>Open
                  </td>
                  <td className={`${styles.mono} text-xs text-re-text-muted`}>
                    —
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className={styles.finalCta}>
        <div className={styles.container}>
          <h2>Ready to build?</h2>
          <p>
            Get your API key and create your first NRC-compliant evidence record in under 5 minutes.
          </p>
          <div className={styles.finalCtaActions}>
            <Link href="/api-keys" className={`${styles.btn} ${styles.btnPrimary}`}>
              Get Free API Key →
            </Link>
            <Link href="/verticals/nuclear/pricing" className={`${styles.btn} ${styles.btnSecondary}`}>
              View Pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
