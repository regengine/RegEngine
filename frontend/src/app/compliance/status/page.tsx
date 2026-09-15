"use client";

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { getServiceURL } from "@/lib/api-config";
import { ComplianceStatusWidget, type ComplianceAlert } from "@/components/dashboard/compliance-status-widget";
import { AlertDetailDialog } from "@/components/dashboard/alert-detail-dialog";
import { useTenantContext } from "@/lib/tenant-context";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { AlertCircle, Clock, Shield, Settings } from "lucide-react";
import Link from "next/link";

export default function ComplianceStatusPage() {
    const { selectedTenant } = useTenantContext();
    const { user } = useAuth();
    const [selectedAlert, setSelectedAlert] = useState<ComplianceAlert | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);

    // Use selected tenant — no demo fallback
    const tenantId = selectedTenant?.id || "";
    const userId = user?.id || user?.email || "anonymous";

    const handleAlertClick = (alert: ComplianceAlert) => {
        setSelectedAlert(alert);
        setDialogOpen(true);
    };

    const handleAcknowledge = async (alertId: string) => {
        if (!tenantId) return;
        try {
            const response = await fetchWithCsrf(`${getServiceURL('admin')}/v1/compliance/alerts/${tenantId}/${alertId}/acknowledge`, {
                method: "POST",
                credentials: 'include',
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({}),
            });
            if (!response.ok) throw new Error("Failed to acknowledge");
            window.location.reload();
        } catch (error) {
            console.error("Acknowledge failed:", error);
        }
    };

    const handleResolve = async (alertId: string, notes: string) => {
        if (!tenantId) return;
        try {
            const response = await fetchWithCsrf(`${getServiceURL('admin')}/v1/compliance/alerts/${tenantId}/${alertId}/resolve`, {
                method: "POST",
                credentials: 'include',
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ notes }),
            });
            if (!response.ok) throw new Error("Failed to resolve");
            window.location.reload();
        } catch (error) {
            console.error("Resolve failed:", error);
        }
    };

    return (
        <PageContainer>
            <PageHeader
                title="Compliance Status"
                description="Real-time monitoring of your FSMA 204 compliance status and regulatory alerts"
                secondaryActions={
                    <Button variant="secondary" size="sm" asChild>
                        <Link href="/compliance/profile">
                            <Settings className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            Configure Profile
                        </Link>
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Main Status Widget */}
                {tenantId ? (
                    <div className="max-w-3xl">
                        <ComplianceStatusWidget
                            tenantId={tenantId}
                            onAlertClick={handleAlertClick}
                        />
                    </div>
                ) : (
                    <EmptyState
                        icon={Shield}
                        title="No workspace selected"
                        description="Select a workspace to monitor its compliance status and regulatory alerts."
                        action={
                            <Button variant="secondary" size="sm" asChild>
                                <Link href="/compliance/profile">
                                    <Settings className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    Configure Profile
                                </Link>
                            </Button>
                        }
                    />
                )}

                {/* Info Cards */}
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Clock className="h-4 w-4 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                24-Hour Response
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-ui text-re-text-secondary">
                                FSMA 204 requires trace data within 24 hours of FDA request.
                                RegEngine monitors for recalls and alerts you immediately.
                            </p>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <AlertCircle className="h-4 w-4 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                                FDA Recall Monitoring
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-ui text-re-text-secondary">
                                Automatic monitoring of FDA recalls, warning letters,
                                and import alerts. Get notified when issues affect your supply chain.
                            </p>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Shield className="h-4 w-4 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                Audit Trail
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <p className="text-ui text-re-text-secondary">
                                Every status change, alert, and action is logged
                                for complete audit compliance and regulatory review.
                            </p>
                        </CardContent>
                    </Card>
                </div>
            </div>

            <AlertDetailDialog
                alert={selectedAlert}
                open={dialogOpen}
                onClose={() => setDialogOpen(false)}
                onAcknowledge={handleAcknowledge}
                onResolve={handleResolve}
                userId={userId}
            />
        </PageContainer>
    );
}
