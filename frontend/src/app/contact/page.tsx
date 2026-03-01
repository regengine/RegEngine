import Link from "next/link";
import { Mail, MessageSquare, PhoneCall } from "lucide-react";

export default function ContactPage() {
  return (
    <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[900px] mx-auto px-6 py-20">
        <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-brand)] mb-3">Contact</p>
        <h1 className="text-[clamp(32px,4.5vw,48px)] font-bold text-[var(--re-text-primary)] leading-tight">
          Talk with the RegEngine team
        </h1>
        <p className="mt-4 text-[var(--re-text-muted)] max-w-[620px] leading-relaxed">
          Reach out for FSMA 204 implementation support, pilot onboarding, or enterprise pricing.
        </p>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4">
          <a
            href="mailto:chris@regengine.com"
            className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]"
          >
            <Mail className="h-5 w-5 text-[var(--re-brand)] mb-2" />
            <p className="text-sm font-semibold text-[var(--re-text-primary)]">Email</p>
            <p className="text-sm text-[var(--re-text-muted)] mt-1">chris@regengine.com</p>
          </a>

          <div className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
            <MessageSquare className="h-5 w-5 text-[var(--re-brand)] mb-2" />
            <p className="text-sm font-semibold text-[var(--re-text-primary)]">Assessment Intake</p>
            <p className="text-sm text-[var(--re-text-muted)] mt-1">Submit retailer readiness and receive founder review.</p>
            <Link href="/retailer-readiness" className="text-xs text-[var(--re-brand)] mt-3 inline-block">
              Open assessment
            </Link>
          </div>

          <div className="p-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
            <PhoneCall className="h-5 w-5 text-[var(--re-brand)] mb-2" />
            <p className="text-sm font-semibold text-[var(--re-text-primary)]">Response Window</p>
            <p className="text-sm text-[var(--re-text-muted)] mt-1">Typical response within one business day.</p>
          </div>
        </div>
      </section>
    </main>
  );
}
