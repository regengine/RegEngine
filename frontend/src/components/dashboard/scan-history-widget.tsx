'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
    ArrowRight,
    Package,
    ScanLine,
    Truck,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/lib/auth-context';
import { getServiceURL } from '@/lib/api-config';

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
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}

export function ScanHistoryWidget() {
    const { tenantId } = useAuth();
    const [events, setEvents] = useState<RecentEvent[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!tenantId) { setLoading(false); return; }
        const load = async () => {
            try {
                const res = await fetch(
                    `${getServiceURL('ingestion')}/api/v1/webhooks/recent?tenant_id=${tenantId}&limit=8`,
                    { credentials: 'include' },
                );
                if (res.ok) {
                    const data = await res.json();
                    setEvents(data.events || []);
                }
            } catch { /* silent */ }
            setLoading(false);
        };
        void load();
    }, [tenantId]);

    return (
        <Card className="h-full">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                        <ScanLine className="h-4 w-4" />
                        Recent Scans
                    </CardTitle>
                    <Link href="/dashboard/scan" className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1">
                        View all <ArrowRight className="h-3 w-3" />
                    </Link>
                </div>
            </CardHeader>
            <CardContent>
                {loading ? (
                    <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">Loading...</div>
                ) : events.length === 0 ? (
                    <div className="text-center py-8">
                        <ScanLine className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                        <p className="text-sm text-muted-foreground">No scans yet</p>
                        <Link href="/dashboard/scan" className="text-xs text-primary hover:underline mt-1 inline-block">
                            Start scanning →
                        </Link>
                    </div>
                ) : (
                    <div className="space-y-1.5">
                        {events.map(evt => {
                            const Icon = EVENT_ICONS[evt.event_type] || Package;
                            return (
                                <div key={evt.event_id} className="flex items-center gap-2.5 py-2 px-2 rounded-lg hover:bg-muted/50 transition-colors">
                                    <div className="p-1.5 rounded-md bg-muted flex-shrink-0">
                                        <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="text-sm font-medium truncate">{evt.product_description}</div>
                                        <div className="text-[11px] text-muted-foreground font-mono truncate">
                                            {evt.traceability_lot_code}
                                        </div>
                                    </div>
                                    <div className="flex flex-col items-end flex-shrink-0">
                                        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                                            {evt.event_type}
                                        </Badge>
                                        {evt.ingested_at && (
                                            <span className="text-[10px] text-muted-foreground mt-0.5">
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
