"use client";

import { useState } from "react";
import { X, Clock, AlertTriangle, CheckCircle, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from "@/components/ui/dialog";

import { type ComplianceAlert } from "@/components/dashboard/compliance-status-widget";

interface AlertDetailDialogProps {
    alert: ComplianceAlert | null;
    open: boolean;
    onClose: () => void;
    onAcknowledge: (alertId: string) => Promise<void>;
    onResolve: (alertId: string, notes: string) => Promise<void>;
    userId: string;
}

const SEVERITY_STYLES: Record<string, { bg: string; text: string; border: string }> = {
    CRITICAL: { bg: "bg-red-100", text: "text-red-800", border: "border-red-200" },
    HIGH: { bg: "bg-amber-100", text: "text-amber-800", border: "border-amber-200" },
    MEDIUM: { bg: "bg-blue-100", text: "text-blue-800", border: "border-blue-200" },
    LOW: { bg: "bg-gray-100", text: "text-gray-800", border: "border-gray-200" },
};

export function AlertDetailDialog({
    alert,
    open,
    onClose,
    onAcknowledge,
    onResolve,
    userId,
}: AlertDetailDialogProps) {
    const [resolveNotes, setResolveNotes] = useState("");
    const [loading, setLoading] = useState(false);

    if (!alert) return null;

    const styles = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.MEDIUM;
    const isActive = alert.status === "ACTIVE";
    const isAcknowledged = alert.status === "ACKNOWLEDGED";

    const handleAcknowledge = async () => {
        setLoading(true);
        try {
            await onAcknowledge(alert.id);
        } finally {
            setLoading(false);
        }
    };

    const handleResolve = async () => {
        setLoading(true);
        try {
            await onResolve(alert.id, resolveNotes);
            setResolveNotes("");
            onClose();
        } finally {
            setLoading(false);
        }
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="max-w-2xl">
                <DialogHeader>
                    <div className="flex items-start gap-3">
                        <div className={`p-2 rounded-lg ${styles.bg}`}>
                            <AlertTriangle className={`h-6 w-6 ${styles.text}`} />
                        </div>
                        <div className="flex-1">
                            <DialogTitle className="text-xl">{alert.title}</DialogTitle>
                            <DialogDescription className="mt-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Badge className={`${styles.bg} ${styles.text} ${styles.border}`}>
                                        {alert.severity_emoji} {alert.severity}
                                    </Badge>
                                    <Badge variant="outline">{alert.source_type}</Badge>
                                    {alert.is_expired && <Badge variant="destructive">EXPIRED</Badge>}
                                    {alert.status === "RESOLVED" && (
                                        <Badge className="bg-green-100 text-green-800">RESOLVED</Badge>
                                    )}
                                </div>
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Countdown */}
                    {!alert.is_expired && (isActive || isAcknowledged) && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                    <Clock className="h-5 w-5 text-amber-600" />
                                    <span className="font-medium text-amber-800">Time Remaining</span>
                                </div>
                                <div className="text-2xl font-mono font-bold text-amber-700">
                                    {alert.countdown_display}
                                </div>
                            </div>
                            {alert.countdown_end && (
                                <p className="text-sm text-amber-600 mt-1">
                                    Deadline: {new Date(alert.countdown_end).toLocaleString()}
                                </p>
                            )}
                        </div>
                    )}

                    {/* Summary */}
                    {alert.summary && (
                        <div>
                            <h4 className="font-semibold text-gray-900 mb-1">Details</h4>
                            <p className="text-gray-600">{alert.summary}</p>
                        </div>
                    )}

                    {/* Match Reason */}
                    {alert.match_reason?.matched_by && (
                        <div>
                            <h4 className="font-semibold text-gray-900 mb-1">Why This Applies to You</h4>
                            <div className="flex flex-wrap gap-2">
                                {alert.match_reason.matched_by.map((reason, i) => (
                                    <Badge key={i} variant="secondary">{reason}</Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Required Actions */}
                    {alert.required_actions.length > 0 && (
                        <div>
                            <h4 className="font-semibold text-gray-900 mb-2">Required Actions</h4>
                            <div className="space-y-2">
                                {alert.required_actions.map((action, i) => (
                                    <div
                                        key={i}
                                        className={`flex items-center gap-3 p-3 rounded-lg border ${action.completed
                                            ? "bg-green-50 border-green-200"
                                            : "bg-gray-50 border-gray-200"
                                            }`}
                                    >
                                        {action.completed ? (
                                            <CheckCircle className="h-5 w-5 text-green-600" />
                                        ) : (
                                            <div className="h-5 w-5 rounded-full border-2 border-gray-300" />
                                        )}
                                        <span className={action.completed ? "text-green-800" : "text-gray-700"}>
                                            {action.action}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Resolution Notes */}
                    {(isActive || isAcknowledged) && (
                        <div>
                            <h4 className="font-semibold text-gray-900 mb-2">Resolution Notes</h4>
                            <Textarea
                                placeholder="Describe what actions were taken to resolve this alert..."
                                value={resolveNotes}
                                onChange={(e) => setResolveNotes(e.target.value)}
                                rows={3}
                            />
                        </div>
                    )}

                    {/* Acknowledgment Info */}
                    {alert.acknowledged_at && (
                        <div className="text-sm text-gray-500">
                            Acknowledged by {alert.acknowledged_by} on{" "}
                            {new Date(alert.acknowledged_at).toLocaleString()}
                        </div>
                    )}
                </div>

                <DialogFooter className="gap-2">
                    <Button variant="outline" onClick={onClose}>
                        Close
                    </Button>

                    {isActive && (
                        <>
                            <Button
                                variant="secondary"
                                onClick={handleAcknowledge}
                                disabled={loading}
                            >
                                Acknowledge
                            </Button>
                            <Button
                                onClick={handleResolve}
                                disabled={loading || !resolveNotes.trim()}
                            >
                                Mark as Resolved
                            </Button>
                        </>
                    )}

                    {isAcknowledged && (
                        <Button
                            onClick={handleResolve}
                            disabled={loading || !resolveNotes.trim()}
                        >
                            Mark as Resolved
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
