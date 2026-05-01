import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Interactive Demo — RegEngine FSMA 204 Compliance Platform",
  description:
    "See RegEngine in action with real compliance data. No signup required. Explore the dashboard, rule engine, supplier portal, and recall simulation.",
};

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen re-app-shell">
      {/* Demo banner */}
      <div className="bg-[var(--re-brand)] text-[var(--re-surface-base)] text-center py-2 px-4 text-[0.75rem] font-medium">
        This is an interactive demo with sample data.{" "}
        <a href="/signup" className="underline font-semibold hover:text-[var(--re-surface-base)]">
          Start your free 14-day trial
        </a>{" "}
        to see your own data.
      </div>
      {children}
    </div>
  );
}
