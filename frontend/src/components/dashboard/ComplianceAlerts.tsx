"use client";

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

/**
 * Compliance alert type for TLC validation
 */
type ComplianceAlert = {
  id: string;
  type: 'error' | 'warning' | 'success';
  title: string;
  message: string;
  tlc?: string;
  timestamp?: string;
};

type ComplianceAlertsProps = {
  alerts: ComplianceAlert[];
  onDismiss?: (id: string) => void;
};

/**
 * ComplianceAlerts Component
 * 
 * Renders compliance alerts for FSMA 204 TLC validation.
 * Shows red card for missing/invalid TLC based on compliance API response.
 */
export function ComplianceAlerts({ alerts, onDismiss }: ComplianceAlertsProps) {
  if (!alerts || alerts.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {alerts.map((alert) => (
        <Card
          key={alert.id}
          className={`border-l-4 ${
            alert.type === 'error'
              ? 'border-l-red-500 bg-red-50 dark:bg-red-950/20'
              : alert.type === 'warning'
              ? 'border-l-yellow-500 bg-yellow-50 dark:bg-yellow-950/20'
              : 'border-l-green-500 bg-green-50 dark:bg-green-950/20'
          }`}
        >
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="flex items-center gap-3">
              {alert.type === 'error' && (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              {alert.type === 'warning' && (
                <AlertTriangle className="h-5 w-5 text-yellow-500" />
              )}
              {alert.type === 'success' && (
                <CheckCircle className="h-5 w-5 text-green-500" />
              )}
              <CardTitle className="text-sm font-medium">{alert.title}</CardTitle>
            </div>
            <Badge
              variant={
                alert.type === 'error'
                  ? 'destructive'
                  : alert.type === 'warning'
                  ? 'secondary'
                  : 'default'
              }
            >
              {alert.type === 'error'
                ? 'Critical'
                : alert.type === 'warning'
                ? 'Warning'
                : 'Resolved'}
            </Badge>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{alert.message}</p>
            {alert.tlc && (
              <p className="mt-2 text-xs font-mono bg-background/50 p-2 rounded">
                TLC: {alert.tlc}
              </p>
            )}
            {alert.timestamp && (
              <p className="mt-2 text-xs text-muted-foreground">
                Detected: {new Date(alert.timestamp).toLocaleString()}
              </p>
            )}
            {onDismiss && (
              <button
                onClick={() => onDismiss(alert.id)}
                className="mt-3 text-xs text-primary hover:underline"
              >
                Dismiss
              </button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/**
 * TLC Validation Alert Card
 * 
 * Renders a red card for invalid or missing TLC.
 * Use this for individual TLC validation results.
 */
type TLCValidationAlertProps = {
  tlc: string | null;
  isValid: boolean;
  errorMessage?: string;
};

export function TLCValidationAlert({ tlc, isValid, errorMessage }: TLCValidationAlertProps) {
  if (isValid) {
    return (
      <Card className="border-l-4 border-l-green-500 bg-green-50 dark:bg-green-950/20">
        <CardContent className="flex items-center gap-3 py-4">
          <CheckCircle className="h-5 w-5 text-green-500" />
          <div>
            <p className="font-medium text-sm">TLC Format Valid</p>
            <p className="text-xs font-mono text-muted-foreground">{tlc}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-l-4 border-l-red-500 bg-red-50 dark:bg-red-950/20">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <XCircle className="h-5 w-5 text-red-500" />
          <CardTitle className="text-sm font-medium text-red-700 dark:text-red-400">
            {tlc ? 'Invalid TLC Format' : 'Missing TLC'}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-red-600 dark:text-red-400">
          {errorMessage || 'Traceability Lot Code is missing or does not match FSMA 204 format.'}
        </p>
        {tlc && (
          <p className="mt-2 text-xs font-mono bg-red-100 dark:bg-red-900/30 p-2 rounded">
            TLC: {tlc}
          </p>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          Expected format: GTIN-14 (14 digits) followed by alphanumeric lot code
        </p>
        <p className="text-xs text-muted-foreground">
          Example: 00012345678901-LOT-2025-A
        </p>
      </CardContent>
    </Card>
  );
}

export default ComplianceAlerts;
