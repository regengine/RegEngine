"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Clock, CheckCircle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
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

/** Severity is a Badge tone, not a bespoke bg/text/border class triple. */
const SEVERITY_TONES: Record<string, BadgeTone> = {
    CRITICAL: "danger",
    HIGH: "warning",
    MEDIUM: "info",
    LOW: "neutral",
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
    const router = useRouter();

    if (!alert) return null;

    /** Determine an action-specific deep link, or null for generic actions. */
    const getActionUrl = (actionText: string): string | null => {
        const lower = actionText.toLowerCase();
        if (lower.includes("trace")) {
            // Pre-fill the ask/trace tool with context from the alert
            const q = encodeURIComponent(`trace lot codes from recall ${alert.source_id ?? alert.title}`);
            return `/dashboard/tools/ask?q=${q}`;
        }
        if (lower.includes("fda") || lower.includes("response")) {
            return `/dashboard/fda-export`;
        }
        if (lower.includes("lot code") || lower.includes("review")) {
            return `/dashboard/traceability`;
        }
        return null;
    };

    const severityTone = SEVERITY_TONES[alert.severity] ?? SEVERITY_TONES.MEDIUM;
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
                    <DialogTitle className="text-heading text-re-text-primary">{alert.title}</DialogTitle>
                    <DialogDescription className="mt-1">
                        <div className="flex flex-wrap items-center gap-2">
                            <Badge tone={severityTone} size="sm">
                                {alert.severity_emoji} {alert.severity}
                            </Badge>
                            <Badge tone="neutral" size="sm">{alert.source_type}</Badge>
                            {alert.is_expired && <Badge tone="danger" size="sm">EXPIRED</Badge>}
                            {alert.status === "RESOLVED" && (
                                <Badge tone="success" size="sm">RESOLVED</Badge>
                            )}
                        </div>
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Countdown */}
                    {!alert.is_expired && (isActive || isAcknowledged) && (
                        <Card variant="inset" padding="compact">
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2">
                                    <Clock className="h-4 w-4 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                    <span className="text-ui font-medium text-re-text-primary">Time Remaining</span>
                                </div>
                                <div className="font-mono text-title tabular-nums text-re-text-primary">
                                    {alert.countdown_display}
                                </div>
                            </div>
                            {alert.countdown_end && (
                                <p className="mt-1 text-small text-re-text-tertiary">
                                    Deadline: {new Date(alert.countdown_end).toLocaleString()}
                                </p>
                            )}
                        </Card>
                    )}

                    {/* Summary */}
                    {alert.summary && (
                        <div>
                            <h4 className="mb-1 text-subheading text-re-text-primary">Details</h4>
                            <p className="text-ui text-re-text-secondary">{alert.summary}</p>
                        </div>
                    )}

                    {/* Match Reason */}
                    {alert.match_reason?.matched_by && (
                        <div>
                            <h4 className="mb-1 text-subheading text-re-text-primary">Why This Applies to You</h4>
                            <div className="flex flex-wrap gap-2">
                                {alert.match_reason.matched_by.map((reason, i) => (
                                    <Badge key={i} tone="neutral" size="sm">{reason}</Badge>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Required Actions */}
                    {alert.required_actions.length > 0 && (
                        <div>
                            <h4 className="mb-2 text-subheading text-re-text-primary">Required Actions</h4>
                            <div className="space-y-2">
                                {alert.required_actions.map((action, i) => {
                                    const actionUrl = !action.completed ? getActionUrl(action.action) : null;
                                    const marker = action.completed ? (
                                        <CheckCircle
                                            className="h-5 w-5 shrink-0 text-re-success"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <span
                                            className="h-5 w-5 shrink-0 rounded-full border-2 border-re-border-strong"
                                            aria-hidden="true"
                                        />
                                    );
                                    const body = (
                                        <>
                                            {marker}
                                            <span
                                                className={cn(
                                                    'flex-1',
                                                    action.completed
                                                        ? 'text-re-text-tertiary'
                                                        : 'text-re-text-primary'
                                                )}
                                            >
                                                {action.action}
                                            </span>
                                            {actionUrl && (
                                                <ArrowRight
                                                    className="h-4 w-4 shrink-0 text-re-text-muted"
                                                    strokeWidth={1.75}
                                                    aria-hidden="true"
                                                />
                                            )}
                                        </>
                                    );

                                    const rowClasses =
                                        'flex w-full items-center gap-3 rounded-md border border-re-border-subtle bg-re-surface-inset p-3 text-left text-ui';

                                    return actionUrl ? (
                                        <button
                                            key={i}
                                            type="button"
                                            className={cn(
                                                rowClasses,
                                                'transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none'
                                            )}
                                            onClick={() => { router.push(actionUrl); onClose(); }}
                                        >
                                            {body}
                                        </button>
                                    ) : (
                                        <div key={i} className={rowClasses}>
                                            {body}
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}

                    {/* Resolution Notes */}
                    {(isActive || isAcknowledged) && (
                        <div>
                            <h4 className="mb-2 text-subheading text-re-text-primary">Resolution Notes</h4>
                            <label htmlFor="alert-resolution-notes" className="sr-only">
                                Resolution Notes
                            </label>
                            <Textarea
                                id="alert-resolution-notes"
                                placeholder="Describe what actions were taken to resolve this alert..."
                                value={resolveNotes}
                                onChange={(e) => setResolveNotes(e.target.value)}
                                rows={3}
                            />
                        </div>
                    )}

                    {/* Acknowledgment Info */}
                    {alert.acknowledged_at && (
                        <div className="text-small text-re-text-tertiary">
                            Acknowledged by {alert.acknowledged_by} on{" "}
                            {new Date(alert.acknowledged_at).toLocaleString()}
                        </div>
                    )}
                </div>

                <DialogFooter className="gap-2">
                    <Button variant="ghost" onClick={onClose}>
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
