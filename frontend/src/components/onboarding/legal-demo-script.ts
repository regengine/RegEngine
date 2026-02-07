import { DriveStep } from 'driver.js';

export interface DemoPageStep {
    path: string;
    driverSteps: DriveStep[];
}

/**
 * LEGAL DEMO SCRIPT
 * 
 * This provides narrated, play-by-play guidance through the RegEngine demo.
 * Each step is designed to clearly explain WHAT is happening and WHY it matters.
 */
export const LEGAL_DEMO_SCRIPT: Record<string, DriveStep[]> = {
    '/': [
        {
            element: 'header',
            popover: {
                title: '🎯 Step 1: Welcome to RegEngine',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> The RegEngine Regulatory Intelligence Platform.</p>
                        <p style="margin-top: 8px;"><strong>Why it matters:</strong> This replaces hundreds of hours of manual regulatory review with automated compliance intelligence.</p>
                        <p style="margin-top: 8px; color: #6b7280;">👉 The navigation above shows the complete workflow: Ingest → Review → Compliance → Opportunities</p>
                    </div>
                `,
                side: 'bottom',
                align: 'start',
            },
        },
        {
            element: '#onboarding-tenant-switcher',
            popover: {
                title: '🏢 Step 2: Multi-Tenant Architecture',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> The tenant switcher for managing multiple organizations.</p>
                        <p style="margin-top: 8px;"><strong>Why it matters:</strong> Each company has completely isolated data. Switch between different tenants — their data never mixes.</p>
                        <p style="margin-top: 8px; color: #6b7280;">🔒 This is enterprise-grade multi-tenancy with Row-Level Security.</p>
                    </div>
                `,
                side: 'left',
                align: 'start',
            },
        },
        {
            element: '#demo-ingestion-section',
            popover: {
                title: '📄 Step 3: Document Ingestion',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> The Live Interaction panel for ingesting regulations.</p>
                        <p style="margin-top: 8px;"><strong>What happens next:</strong> We'll fetch the EU DORA regulation directly from EUR-Lex and process it through our NLP pipeline.</p>
                        <p style="margin-top: 12px; padding: 8px; background: #f0fdf4; border-radius: 4px;">
                            <strong>👆 ACTION:</strong> Click "Quick Ingest Only" to start processing!
                        </p>
                    </div>
                `,
                side: 'top',
            },
        },
    ],
    '/ingest': [
        {
            element: 'h1',
            popover: {
                title: '⚙️ Step 4: Processing in Action',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What's happening now:</strong> The NLP engine is reading the DORA regulation (200+ pages).</p>
                        <p style="margin-top: 8px;"><strong>What it extracts:</strong></p>
                        <ul style="margin-left: 16px; margin-top: 4px;">
                            <li>✓ Obligations (MUST, MUST NOT, SHOULD)</li>
                            <li>✓ Deadlines and thresholds</li>
                            <li>✓ Jurisdictional scope</li>
                            <li>✓ Regulatory citations</li>
                        </ul>
                        <p style="margin-top: 8px; color: #6b7280;">⏱️ What takes lawyers days, happens in seconds.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
        {
            element: '[data-testid="upload-area"]',
            popover: {
                title: '📁 Step 5: Upload Your Own Regulations',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> The document upload zone.</p>
                        <p style="margin-top: 8px;"><strong>Supported formats:</strong> PDF, DOCX, HTML, or direct URL fetch from regulatory sources.</p>
                        <p style="margin-top: 8px; color: #6b7280;">💡 Drag any regulation here and watch it get auto-parsed.</p>
                    </div>
                `,
                side: 'right',
            },
        },
    ],
    '/review': [
        {
            element: 'h1',
            popover: {
                title: '👁️ Step 6: Human-in-the-Loop Review',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> Items flagged for expert review.</p>
                        <p style="margin-top: 8px;"><strong>Why this matters:</strong> AI extractions below 85% confidence come here. You verify before they become compliance requirements.</p>
                        <p style="margin-top: 8px; color: #6b7280;">⚖️ You stay in control. AI assists, you decide.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
        {
            element: '[data-testid="review-card-0"]',
            popover: {
                title: '✅ Step 7: Approve or Reject',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> An extracted obligation awaiting your review.</p>
                        <p style="margin-top: 8px;"><strong>Your options:</strong></p>
                        <ul style="margin-left: 16px; margin-top: 4px;">
                            <li><strong>Approve</strong> → Becomes a verified compliance requirement</li>
                            <li><strong>Edit</strong> → Fix any extraction errors</li>
                            <li><strong>Reject</strong> → Mark as false positive</li>
                        </ul>
                        <p style="margin-top: 8px; padding: 8px; background: #f0fdf4; border-radius: 4px;">
                            <strong>👆 TRY IT:</strong> Click Approve to see it flow to the graph!
                        </p>
                    </div>
                `,
                side: 'top',
            },
        },
    ],
    '/compliance': [
        {
            element: 'h1',
            popover: {
                title: '📊 Step 8: Compliance Scorecard',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> Your compliance status dashboard.</p>
                        <p style="margin-top: 8px;"><strong>Key metrics:</strong></p>
                        <ul style="margin-left: 16px; margin-top: 4px;">
                            <li>✅ COMPLIANT - Requirements met</li>
                            <li>⚠️ AT_RISK - Action needed soon</li>
                            <li>🚨 NON_COMPLIANT - Overdue items</li>
                        </ul>
                        <p style="margin-top: 8px; color: #6b7280;">📈 Executive-ready at a glance.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
        {
            element: '[data-testid="compliance-score"]',
            popover: {
                title: '🎯 Step 9: Readiness Score',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> Your overall compliance readiness percentage.</p>
                        <p style="margin-top: 8px;"><strong>How it's calculated:</strong> (Verified Requirements ÷ Total Requirements) × 100</p>
                        <p style="margin-top: 8px; color: #6b7280;">📋 Show this to auditors. Show this to the board.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
    ],
    '/trace': [
        {
            element: 'h1',
            popover: {
                title: '🕸️ Step 10: Knowledge Graph',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> The regulatory knowledge graph.</p>
                        <p style="margin-top: 8px;"><strong>Connections shown:</strong></p>
                        <ul style="margin-left: 16px; margin-top: 4px;">
                            <li>Acts → Articles → Provisions</li>
                            <li>Provisions → Controls → Products</li>
                            <li>Cross-regulation dependencies</li>
                        </ul>
                        <p style="margin-top: 8px; color: #6b7280;">🔍 See how one regulation change ripples across your entire compliance program.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
    ],
    '/opportunities': [
        {
            element: 'h1',
            popover: {
                title: '💡 Step 11: Gap Analysis & Opportunities',
                description: `
                    <div style="font-size: 14px; line-height: 1.6;">
                        <p><strong>What you're seeing:</strong> Identified compliance gaps and arbitrage opportunities.</p>
                        <p style="margin-top: 8px;"><strong>Value delivered:</strong></p>
                        <ul style="margin-left: 16px; margin-top: 4px;">
                            <li>🔴 Critical gaps requiring immediate action</li>
                            <li>🟡 Areas where you can optimize controls</li>
                            <li>🟢 Cross-regulation synergies to exploit</li>
                        </ul>
                        <p style="margin-top: 8px; color: #6b7280;">💰 Turn compliance from cost center to competitive advantage.</p>
                    </div>
                `,
                side: 'bottom',
            },
        },
    ],
};
