"use client";

import { PageContainer } from "@/components/layout/page-container";
import { TargetMarketBrowser } from "@/components/fsma/target-market-browser";
import { motion } from "framer-motion";
import { Building2, ArrowLeft, Users, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function TargetMarketPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <PageContainer>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-6"
        >
          {/* Back Navigation */}
          <Link href="/fsma">
            <Button variant="ghost" size="sm" className="mb-4">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to FSMA Dashboard
            </Button>
          </Link>

          {/* Page Header */}
          <div className="flex items-center gap-4 mb-8 border-b border-[var(--re-surface-border)] pb-6">
            <div className="flex h-14 w-14 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
              <Building2 className="h-7 w-7 text-[var(--re-brand)]" />
            </div>
            <div>
              <h1 className="text-3xl font-bold">FSMA 204 Target Market</h1>
              <p className="text-muted-foreground mt-1">
                75+ companies subject to FDA Food Traceability requirements
              </p>
            </div>
          </div>

          {/* Info Banner */}
          <section className="border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
            <div className="py-4 px-5">
              <div className="flex flex-col md:flex-row gap-6">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
                    <Target className="h-5 w-5 text-[var(--re-brand)]" />
                  </div>
                  <div>
                    <p className="font-medium">Compliance Deadline</p>
                    <p className="text-sm text-muted-foreground">July 2028</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]">
                    <Users className="h-5 w-5 text-[var(--re-text-secondary)]" />
                  </div>
                  <div>
                    <p className="font-medium">Key Personas</p>
                    <p className="text-sm text-muted-foreground">
                      Food Safety Managers, QA Directors, VP Compliance
                    </p>
                  </div>
                </div>
                <div className="flex-1">
                  <p className="text-sm">
                    These companies handle products on the FDA Food Traceability
                    List (FTL) and must implement full-chain traceability
                    including CTEs, KDEs, and 24-hour FDA response capabilities.
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Target Market Browser */}
          <TargetMarketBrowser />
        </motion.div>
      </PageContainer>
    </div>
  );
}
