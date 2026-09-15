"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Package, ScanLine, Truck } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/lib/auth-context";
import { getServiceURL } from "@/lib/api-config";

interface RecentEvent {
  event_id: string;
  event_type: string;
  traceability_lot_code: string;
  product_description: string;
  quantity: number;
  unit_of_measure: string;
  location_name: string | null;
  source: string | null;
  ingested_at: string | null;
}

const EVENT_ICONS: Record<string, typeof Package> = {
  receiving: Truck,
  shipping: Truck,
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function ScanHistoryWidget() {
  const { tenantId, isAuthenticated } = useAuth();
  const [events, setEvents] = useState<RecentEvent[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!tenantId || !isAuthenticated) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      const search = new URLSearchParams({ tenant_id: tenantId, limit: "8" });
      try {
        const res = await fetch(
          `${getServiceURL("ingestion")}/api/v1/webhooks/recent?${search}`,
          {
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
            },
            signal: AbortSignal.timeout(8000),
          },
        );
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) setEvents(data.events || []);
        }
      } catch {
        /* silent */
      }
      if (!cancelled) setLoading(false);
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, tenantId]);
  const isLoading = Boolean(tenantId && isAuthenticated) && loading;

  return (
    <Card className="min-h-[260px]">
      <CardHeader>
        <CardTitle>Recent Scans</CardTitle>
        <Link
          href="/ingest"
          className="inline-flex shrink-0 items-center gap-1 text-small text-re-text-tertiary no-underline transition-colors duration-120 hover:text-re-brand"
        >
          Import data <ArrowRight className="h-3 w-3" aria-hidden="true" />
        </Link>
      </CardHeader>
      <CardContent className="min-h-[196px]">
        {isLoading ? (
          <div className="space-y-2" aria-busy="true">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <EmptyState
            bare
            size="sm"
            icon={ScanLine}
            title="No scans yet"
            action={
              <Link
                href="/ingest"
                className="inline-flex items-center gap-1 text-ui text-re-brand no-underline hover:underline"
              >
                Import data
                <ArrowRight className="h-3 w-3" aria-hidden="true" />
              </Link>
            }
          />
        ) : (
          <div>
            {events.map((evt) => {
              const Icon = EVENT_ICONS[evt.event_type] || Package;
              return (
                <div
                  key={evt.event_id}
                  className="flex items-center gap-3 border-b border-re-border-subtle py-2.5 transition-colors duration-120 last:border-b-0"
                >
                  <Icon className="h-4 w-4 shrink-0 text-re-text-muted" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-ui font-medium text-re-text-primary">
                      {evt.product_description}
                    </div>
                    <div className="truncate font-mono text-small text-re-text-tertiary">
                      {evt.traceability_lot_code}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <Badge size="sm" mono>
                      {evt.event_type}
                    </Badge>
                    {evt.ingested_at && (
                      <span className="text-small text-re-text-tertiary">
                        {timeAgo(evt.ingested_at)}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
