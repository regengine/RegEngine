'use client';

import { useState } from 'react';
import { useDriftAlerts, useAcknowledgeAlert } from '@/hooks/use-fsma';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    AlertTriangle,
    CheckCircle,
    Search,
    Filter,
    Shield,
    Clock,
    LayoutGrid
} from 'lucide-react';
import { AlertCard } from './alert-card';
import { AlertFilters } from './alert-filters';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';

export default function AdminAlertsPage() {
    if (!experimentalFeaturesEnabled()) {
        return (
            <FeatureNotEnabled
                featureName="Alert Center"
                backHref="/admin"
                backLabel="Back to admin"
            />
        );
    }
    return <AdminAlertsContent />;
}

function AdminAlertsContent() {
    // #2999: this page used to destructure only { data, isLoading } and feed
    // `alertsData?.alerts.filter(...) || []` into the empty state, so a failed
    // fetch rendered "System is operating within compliance thresholds" — an
    // affirmative all-clear at precisely the moment the alert state was
    // unknown. Error/no-data now renders an explicit unavailable state,
    // following DriftAlertsWidget's precedent (#2837).
    const { data: alertsData, isLoading, isError, error } = useDriftAlerts();
    const alertsUnavailable = !isLoading && (isError || !alertsData);
    const acknowledge = useAcknowledgeAlert();

    const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
    const [filterType, setFilterType] = useState<string>('ALL');
    const [searchQuery, setSearchQuery] = useState('');

    const handleAcknowledge = async (id: string) => {
        try {
            await acknowledge.mutateAsync(id);
        } catch (error) {
            console.error('Failed to acknowledge alert:', error);
        }
    };

    const filteredAlerts = alertsData?.alerts.filter(alert => {
        // Filter by Severity
        if (filterSeverity !== 'ALL' && alert.severity !== filterSeverity) return false;
        // Filter by Type (assuming metric serves as type proxy or added type field)
        if (filterType !== 'ALL' && alert.metric !== filterType) return false;
        // Search
        if (searchQuery) {
            const q = searchQuery.toLowerCase();
            return (
                alert.message.toLowerCase().includes(q) ||
                (alert.metric?.toLowerCase() || '').includes(q) ||
                alert.id.toLowerCase().includes(q)
            );
        }
        return true;
    }) || [];

    return (
        <div className="space-y-6 p-4 sm:p-6 lg:p-8">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-3">
                        <Shield className="h-8 w-8 text-re-info" />
                        Compliance Alerts
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Monitor and resolve FSMA 204 compliance drift
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    {alertsUnavailable ? (
                        <Badge variant="outline" className="px-3 py-1 text-muted-foreground">
                            Unavailable
                        </Badge>
                    ) : (
                        <Badge variant="outline" className="px-3 py-1">
                            {filteredAlerts.length} Active Alerts
                        </Badge>
                    )}
                </div>
            </div>

            {/* Filters & Search */}
            <Card>
                <CardContent className="pt-6">
                    <div className="flex flex-col md:flex-row gap-4">
                        <div className="relative flex-1">
                            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                            <Input
                                placeholder="Search alerts by message or ID..."
                                className="pl-8"
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                            />
                        </div>
                        <AlertFilters
                            severity={filterSeverity}
                            setSeverity={setFilterSeverity}
                            type={filterType}
                            setType={setFilterType}
                        />
                    </div>
                </CardContent>
            </Card>

            {/* Alerts Grid */}
            {isLoading ? (
                <div className="flex justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
            ) : alertsUnavailable ? (
                // #2999: "could not fetch alerts" and "there are no alerts" are
                // opposite conditions — never collapse the former into the
                // all-clear copy below. The data source (GET /api/fsma/drift/
                // alerts) has no backend router (#2980), so this is phrased as
                // an unconnected capability rather than a retryable blip,
                // matching DriftAlertsWidget.
                <Card className="border-dashed">
                    <CardContent role="status" className="py-12 text-center text-muted-foreground">
                        <AlertTriangle className="h-12 w-12 mx-auto mb-4 text-re-warning" />
                        <p className="text-lg font-medium">Alerts unavailable</p>
                        <p>
                            Compliance alerts could not be loaded, so the current alert state is
                            unknown. This is not an all-clear.
                        </p>
                        {isError && error instanceof Error && error.message ? (
                            <p className="mt-2 text-xs opacity-80">Details: {error.message}</p>
                        ) : null}
                    </CardContent>
                </Card>
            ) : filteredAlerts.length === 0 ? (
                <Card className="border-dashed">
                    <CardContent className="py-12 text-center text-muted-foreground">
                        <CheckCircle className="h-12 w-12 mx-auto mb-4 text-re-success opacity-50" />
                        <p className="text-lg font-medium">No alerts found</p>
                        <p>System is operating within compliance thresholds.</p>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filteredAlerts.map(alert => (
                        <AlertCard
                            key={alert.id}
                            alert={alert}
                            onAcknowledge={handleAcknowledge}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}
