"use client";

import { useState } from "react";
import { motion } from "framer-motion";

import { PageContainer } from "@/components/layout/page-container";
import { ComplianceStatusWidget, type ComplianceAlert } from "@/components/dashboard/compliance-status-widget";
import { AlertDetailDialog } from "@/components/dashboard/alert-detail-dialog";
import { useTenantContext } from "@/lib/tenant-context";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { AlertCircle, Clock, Shield, Settings } from "lucide-react";
import Link from "next/link";

export default function ComplianceStatusPage() {
    const { selectedTenant } = useTenantContext();
    const { user, apiKey } = useAuth();
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
        try {
            const response = await fetch(`/api/ingestion/api/v1/compliance/alerts/${tenantId}/${alertId}/acknowledge`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-RegEngine-API-Key": apiKey || "" },
                body: JSON.stringify({ user_id: userId }),
            });
            if (!response.ok) throw new Error("Failed to acknowledge");
            window.location.reload();
        } catch (error) {
            console.error("Acknowledge failed:", error);
        }
    };

    const handleResolve = async (alertId: string, notes: string) => {
        try {
            const response = await fetch(`/api/ingestion/api/v1/compliance/alerts/${tenantId}/${alertId}/resolve`, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-RegEngine-API-Key": apiKey || "" },
                body: JSON.stringify({ user_id: userId, notes }),
            });
            if (!response.ok) throw new Error("Failed to resolve");
            window.location.reload();
        } catch (error) {
            console.error("Resolve failed:", error);
        }
    };

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    {/* Page Header */}
                    <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-8">
                        <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
                            <Shield className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="flex-1">
                            <h1 className="text-3xl sm:text-4xl font-bold">Compliance Status</h1>
                            <p className="text-muted-foreground mt-1">
                                Real-time monitoring of your FSMA 204 compliance status and regulatory alerts
                            </p>
                        </div>
                        <Link href="/compliance/profile">
                            <Button variant="outline" size="sm">
                                <Settings className="h-4 w-4 mr-2" />
                                Configure Profile
                            </Button>
                        </Link>
                    </div>

                    {/* Main Status Widget */}
                    <div className="max-w-3xl mb-8">
                        <ComplianceStatusWidget
                            tenantId={tenantId}
                            onAlertClick={handleAlertClick}
                        />
                    </div>

                    {/* Info Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Clock className="h-5 w-5 text-amber-500" />
                                    24-Hour Response
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">
                                    FSMA 204 requires trace data within 24 hours of FDA request.
                                    RegEngine monitors for recalls and alerts you immediately.
                                </p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <AlertCircle className="h-5 w-5 text-red-500" />
                                    FDA Recall Monitoring
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">
                                    Automatic monitoring of FDA recalls, warning letters,
                                    and import alerts. Get notified when issues affect your supply chain.
                                </p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="pb-3">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <Shield className="h-5 w-5 text-green-500" />
                                    Audit Trail
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">
                                    Every status change, alert, and action is logged
                                    for complete audit compliance and regulatory review.
                                </p>
                            </CardContent>
                        </Card>
                    </div>
                </motion.div>

                <AlertDetailDialog
                    alert={selectedAlert}
                    open={dialogOpen}
                    onClose={() => setDialogOpen(false)}
                    onAcknowledge={handleAcknowledge}
                    onResolve={handleResolve}
                    userId={userId}
                />
            </PageContainer>
        </div>
    );
}
