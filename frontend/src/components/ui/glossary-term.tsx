'use client';

import * as React from 'react';
import { Tooltip } from './tooltip';

/**
 * Centralized glossary for FSMA 204 / RegEngine terminology.
 * Every acronym or domain term that a non-technical user might
 * not understand should be defined here exactly once.
 */
export const GLOSSARY: Record<string, string> = {
    CTE: 'Critical Tracking Event — each time you receive, ship, or transform a product.',
    KDE: 'Key Data Element — the required data fields for each tracking event (lot code, date, location, etc.).',
    TLC: 'Traceability Lot Code — the unique identifier for a batch of product (like a lot number).',
    GLN: 'Global Location Number — a standardized 13-digit code that identifies a facility or location.',
    GTIN: 'Global Trade Item Number — the barcode number on a product (like a UPC or EAN).',
    EPCIS: 'Electronic Product Code Information Services — the GS1 standard format for sharing tracking events.',
    GS1: 'GS1 is the organization that manages barcode and product identification standards worldwide.',
    'FSMA 204': 'FDA Food Safety Modernization Act Section 204 — the federal rule requiring food traceability recordkeeping.',
    FEI: 'FDA Establishment Identifier — the number FDA assigns to each registered food facility.',
    'FDA Export': 'A downloadable file formatted to meet FDA inspection requirements.',
    'Chain Hash': 'A cryptographic fingerprint (SHA-256) that proves your records haven\'t been tampered with.',
    'Recall Drill': 'A practice run of your recall process — tests how fast you can trace a product backward through your supply chain.',
    SLA: 'Service Level Agreement — your committed response time (e.g., 24 hours for a recall trace).',
    RBAC: 'Role-Based Access Control — permissions that limit what each team member can see and do.',
};

interface GlossaryTermProps {
    term: string;
    children?: React.ReactNode;
    className?: string;
}

/**
 * Wraps a term in a dotted underline with a hover tooltip
 * that explains what it means in plain English.
 *
 * Usage:
 *   <Term term="CTE" />           → renders "CTE" with tooltip
 *   <Term term="CTE">events</Term> → renders "events" with tooltip
 */
export function Term({ term, children, className }: GlossaryTermProps) {
    const definition = GLOSSARY[term];
    if (!definition) {
        return <span className={className}>{children || term}</span>;
    }
    return (
        <Tooltip content={definition} side="top">
            <span
                className={`cursor-help border-b border-dotted border-current opacity-90 hover:opacity-100 ${className || ''}`}
                tabIndex={0}
                aria-label={`${term}: ${definition}`}
            >
                {children || term}
            </span>
        </Tooltip>
    );
}
