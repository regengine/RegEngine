'use client';

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Search, X, ArrowRight, FileText, Wrench, BarChart3, BookOpen, Shield, Zap } from 'lucide-react';

/* ─── Search Index ─── */

interface SearchItem {
    title: string;
    description: string;
    href: string;
    category: 'page' | 'tool' | 'dashboard' | 'docs' | 'compliance';
    keywords: string[];
}

const SEARCH_INDEX: SearchItem[] = [
    // Marketing pages
    { title: 'Home', description: 'RegEngine homepage', href: '/', category: 'page', keywords: ['home', 'landing', 'main'] },
    { title: 'Product Tour', description: 'FSMA 204 compliance in three moves', href: '/product', category: 'page', keywords: ['product', 'features', 'tour', 'how it works'] },
    { title: 'Pricing', description: 'Base, Standard, Premium plans', href: '/pricing', category: 'page', keywords: ['pricing', 'plans', 'cost', 'price', 'billing', 'partner'] },
    { title: 'Retailer Readiness', description: 'Retailer-ready in 30 days or less', href: '/retailer-readiness', category: 'page', keywords: ['retailer', 'walmart', 'kroger', 'costco', 'supplier', 'shelf'] },
    { title: 'FSMA 204 Guide', description: 'The FDA food traceability rule in plain English', href: '/fsma-204', category: 'docs', keywords: ['fsma', '204', 'fda', 'guide', 'rule', 'traceability', 'compliance', 'deadline'] },
    { title: 'Integrations', description: 'Connect your existing stack', href: '/integrations', category: 'page', keywords: ['integrations', 'api', 'connect', 'sap', 'oracle', 'quickbooks', 'webhook'] },
    { title: 'Sample Export Package', description: 'Download and inspect a real FDA export with EPCIS, CSV, and verification', href: '/sample-export', category: 'page', keywords: ['sample', 'export', 'download', 'fda', 'epcis', 'csv', 'package', 'proof', 'artifact'] },
    { title: 'Walkthrough: CSV to Export', description: 'Complete workflow from messy data to audit-ready FDA package', href: '/walkthrough', category: 'page', keywords: ['walkthrough', 'workflow', 'csv', 'upload', 'ingest', 'validate', 'export', 'demo', 'how it works'] },
    { title: 'Security', description: 'Trust center, RLS, SHA-256 integrity', href: '/security', category: 'page', keywords: ['security', 'trust', 'rls', 'sha256', 'encryption', 'audit'] },
    { title: 'About', description: 'About RegEngine and the founder', href: '/about', category: 'page', keywords: ['about', 'founder', 'christopher', 'sellers', 'team'] },
    { title: 'Contact', description: 'Get in touch', href: '/contact', category: 'page', keywords: ['contact', 'email', 'support', 'help'] },
    { title: 'Founding Design Partners', description: 'Early access program — 50% off for life', href: '/founding-design-partners', category: 'page', keywords: ['founding', 'design', 'partner', 'alpha', 'early access', 'program'] },
    { title: 'Verify', description: 'Verify record integrity with SHA-256', href: '/verify', category: 'page', keywords: ['verify', 'merkle', 'hash', 'sha256', 'integrity', 'proof'] },
    { title: 'Privacy Policy', description: 'How we handle your data', href: '/privacy', category: 'page', keywords: ['privacy', 'data', 'gdpr', 'policy'] },
    { title: 'Terms of Service', description: 'Terms and conditions', href: '/terms', category: 'page', keywords: ['terms', 'service', 'legal', 'agreement'] },

    // Free tools
    { title: 'FTL Coverage Checker', description: 'Check if your products are on the Food Traceability List', href: '/ftl-checker', category: 'tool', keywords: ['ftl', 'checker', 'food traceability list', 'covered', 'products', 'categories'] },
    { title: 'Retailer Readiness Assessment', description: 'Score your Walmart supplier audit readiness', href: '/tools/retailer-readiness', category: 'tool', keywords: ['readiness', 'assessment', 'score', 'retailer', 'walmart', 'audit'] },
    { title: 'Recall Readiness Score', description: 'Grade your 24-hour recall response capability', href: '/tools/recall-readiness', category: 'tool', keywords: ['recall', 'readiness', 'drill', 'response', '24 hour', 'fda'] },
    { title: 'CTE Mapper', description: 'Map supply chain events to FSMA CTE structure', href: '/tools/cte-mapper', category: 'tool', keywords: ['cte', 'mapper', 'critical tracking event', 'mapping'] },
    { title: 'KDE Checker', description: 'Validate Key Data Element completeness', href: '/tools/kde-checker', category: 'tool', keywords: ['kde', 'key data element', 'validation', 'completeness'] },
    { title: 'TLC Validator', description: 'Validate Traceability Lot Code format', href: '/tools/tlc-validator', category: 'tool', keywords: ['tlc', 'traceability lot code', 'validator', 'format'] },
    { title: 'ROI Calculator', description: 'Calculate compliance cost vs risk', href: '/tools/roi-calculator', category: 'tool', keywords: ['roi', 'calculator', 'cost', 'savings', 'return'] },
    { title: 'FDA Recall Drill', description: 'Simulate an FDA records request', href: '/tools/drill-simulator', category: 'tool', keywords: ['drill', 'simulator', 'recall', 'fda', 'simulation', 'exercise'] },
    { title: 'Scan → Ingest', description: 'Scan GS1 barcodes and auto-fill CTE fields', href: '/tools/scan', category: 'tool', keywords: ['scan', 'barcode', 'gs1', 'qr', 'ingest', 'camera'] },
    { title: 'Ask → Answer', description: 'Natural language traceability queries', href: '/tools/ask', category: 'tool', keywords: ['ask', 'query', 'search', 'natural language', 'question'] },
    { title: 'Export → Comply', description: 'Generate FDA-ready export packages', href: '/tools/export', category: 'tool', keywords: ['export', 'fda', 'package', 'csv', 'epcis', 'comply'] },
    { title: 'Data Import', description: 'Bulk upload CSV or XLSX files', href: '/onboarding/bulk-upload', category: 'tool', keywords: ['import', 'upload', 'csv', 'xlsx', 'bulk', 'data', 'spreadsheet'] },
    { title: 'Label Scanner', description: 'Analyze food labels with AI', href: '/tools/label-scanner', category: 'tool', keywords: ['label', 'scanner', 'vision', 'ai', 'image'] },

    // Dashboard pages
    { title: 'Dashboard', description: 'Compliance overview and metrics', href: '/dashboard', category: 'dashboard', keywords: ['dashboard', 'overview', 'home', 'metrics'] },
    { title: 'Heartbeat', description: 'Daily compliance pulse check', href: '/dashboard/heartbeat', category: 'dashboard', keywords: ['heartbeat', 'daily', 'pulse', 'score', 'morning'] },
    { title: 'Compliance', description: 'FSMA 204 readiness score and breakdown', href: '/dashboard/compliance', category: 'dashboard', keywords: ['compliance', 'score', 'grade', 'readiness', 'gaps'] },
    { title: 'Alerts', description: 'Compliance issues and notifications', href: '/dashboard/alerts', category: 'dashboard', keywords: ['alerts', 'notifications', 'issues', 'warnings'] },
    { title: 'Suppliers', description: 'Manage facilities and supplier compliance', href: '/dashboard/suppliers', category: 'dashboard', keywords: ['suppliers', 'facilities', 'locations', 'management'] },
    { title: 'Products', description: 'Product catalog with FTL coverage', href: '/dashboard/products', category: 'dashboard', keywords: ['products', 'catalog', 'ftl', 'items', 'sku'] },
    { title: 'Audit Log', description: 'Immutable SHA-256 verified event log', href: '/dashboard/audit-log', category: 'dashboard', keywords: ['audit', 'log', 'events', 'history', 'trail', 'hash'] },
    { title: 'Recall Report', description: 'Recall investigation and lot tracing', href: '/dashboard/recall-report', category: 'dashboard', keywords: ['recall', 'report', 'investigation', 'lot', 'trace'] },
    { title: 'Recall Drills', description: 'Practice recall response workflows', href: '/dashboard/recall-drills', category: 'dashboard', keywords: ['recall', 'drills', 'practice', 'exercise', 'response'] },
    { title: 'Export Jobs', description: 'Schedule FDA exports and compliance reports', href: '/dashboard/export-jobs', category: 'dashboard', keywords: ['export', 'jobs', 'schedule', 'fda', 'epcis', 'reports'] },
    { title: 'Integrations', description: 'Connected systems and data sources', href: '/dashboard/integrations', category: 'dashboard', keywords: ['integrations', 'connections', 'systems', 'data sources'] },
    { title: 'Receiving Dock', description: 'Log receiving events with barcode scanning', href: '/dashboard/receiving', category: 'dashboard', keywords: ['receiving', 'dock', 'inbound', 'shipment', 'barcode'] },
    { title: 'Field Capture', description: 'Mobile QR/barcode scanning', href: '/dashboard/scan', category: 'dashboard', keywords: ['field', 'capture', 'mobile', 'scan', 'qr'] },
    { title: 'Team', description: 'Manage team members and roles', href: '/dashboard/team', category: 'dashboard', keywords: ['team', 'members', 'roles', 'users', 'invite'] },
    { title: 'Settings', description: 'Account and workspace settings', href: '/dashboard/settings', category: 'dashboard', keywords: ['settings', 'account', 'profile', 'preferences'] },
    { title: 'Notifications', description: 'Notification preferences and channels', href: '/dashboard/notifications', category: 'dashboard', keywords: ['notifications', 'preferences', 'email', 'alerts'] },

    // FSMA compliance content
    { title: 'Critical Tracking Events (CTEs)', description: '7 event types: harvesting, cooling, initial packing, first land-based receiving, shipping, receiving, transformation', href: '/fsma-204#ctes', category: 'compliance', keywords: ['cte', 'critical tracking event', 'harvesting', 'cooling', 'packing', 'first land-based receiving', 'shipping', 'receiving', 'transformation'] },
    { title: 'Key Data Elements (KDEs)', description: 'Required data fields for each CTE type', href: '/fsma-204#kdes', category: 'compliance', keywords: ['kde', 'key data element', 'fields', 'required', 'data points'] },
    { title: 'Food Traceability List (FTL)', description: 'FDA food categories covered by FSMA 204', href: '/fsma-204#ftl', category: 'compliance', keywords: ['ftl', 'food traceability list', 'categories', 'leafy greens', 'seafood', 'cheese', 'eggs'] },
    { title: '24-Hour Response Rule', description: 'FDA can request records and you must respond within 24 hours', href: '/fsma-204#24-hour', category: 'compliance', keywords: ['24 hour', 'response', 'fda request', 'records', 'deadline'] },
    { title: 'EPCIS 2.0', description: 'GS1 traceability event messaging standard', href: '/fsma-204#epcis', category: 'compliance', keywords: ['epcis', 'gs1', 'standard', 'format', 'interoperability'] },
    { title: 'July 2028 Deadline', description: 'FDA enforcement begins July 20, 2028', href: '/fsma-204#deadline', category: 'compliance', keywords: ['deadline', 'july 2028', 'enforcement', 'date', 'timeline'] },
];

const CATEGORY_ICONS: Record<string, typeof Search> = {
    page: FileText,
    tool: Wrench,
    dashboard: BarChart3,
    docs: BookOpen,
    compliance: Shield,
};

const CATEGORY_LABELS: Record<string, string> = {
    page: 'Pages',
    tool: 'Tools',
    dashboard: 'Dashboard',
    docs: 'Docs',
    compliance: 'FSMA 204',
};

/* ─── Supabase Search Logging ─── */

async function logSearchQuery(query: string, resultCount: number, selectedResult?: string) {
    try {
        const { createSupabaseBrowserClient } = await import('@/lib/supabase/client');
        const supabase = createSupabaseBrowserClient();
        await supabase.from('search_queries').insert({
            query: query.trim().toLowerCase(),
            result_count: resultCount,
            selected_result: selectedResult || null,
            page_url: typeof window !== 'undefined' ? window.location.pathname : null,
            user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 200) : null,
        });
    } catch {
        // Silently fail — search analytics shouldn't break the UX
    }
}

/* ─── Component ─── */

export function GlobalSearch() {
    const [query, setQuery] = useState('');
    const [isOpen, setIsOpen] = useState(false);
    const [selectedIndex, setSelectedIndex] = useState(0);
    const inputRef = useRef<HTMLInputElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const router = useRouter();
    const debounceRef = useRef<ReturnType<typeof setTimeout>>();

    const results = useMemo(() => {
        if (!query.trim()) return [];
        const q = query.toLowerCase().trim();
        const words = q.split(/\s+/);

        return SEARCH_INDEX
            .map(item => {
                let score = 0;
                const titleLower = item.title.toLowerCase();
                const descLower = item.description.toLowerCase();

                // Exact title match
                if (titleLower === q) score += 100;
                // Title starts with query
                else if (titleLower.startsWith(q)) score += 80;
                // Title contains query
                else if (titleLower.includes(q)) score += 60;

                // Word-level matching
                for (const word of words) {
                    if (titleLower.includes(word)) score += 20;
                    if (descLower.includes(word)) score += 10;
                    if (item.keywords.some(k => k.includes(word))) score += 15;
                }

                return { ...item, score };
            })
            .filter(item => item.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, 8);
    }, [query]);

    // Log search queries (debounced)
    useEffect(() => {
        if (!query.trim() || query.trim().length < 2) return;
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            logSearchQuery(query, results.length);
        }, 1500);
        return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
    }, [query, results.length]);

    // Keyboard shortcut: Cmd+K or /
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                inputRef.current?.focus();
                setIsOpen(true);
            }
            if (e.key === '/' && !['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
                e.preventDefault();
                inputRef.current?.focus();
                setIsOpen(true);
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    // Close on click outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleSelect = useCallback((item: SearchItem) => {
        logSearchQuery(query, results.length, item.href);
        setIsOpen(false);
        setQuery('');
        router.push(item.href);
    }, [query, results.length, router]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setSelectedIndex(prev => Math.max(prev - 1, 0));
        } else if (e.key === 'Enter' && results[selectedIndex]) {
            handleSelect(results[selectedIndex]);
        } else if (e.key === 'Escape') {
            setIsOpen(false);
            inputRef.current?.blur();
        }
    };

    return (
        <div ref={containerRef} style={{ position: 'relative' }}>
            {/* Search Input */}
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    background: 'var(--re-search-bg, rgba(255,255,255,0.06))',
                    border: '1px solid var(--re-search-border, rgba(255,255,255,0.08))',
                    borderRadius: 8,
                    padding: '6px 12px',
                    minWidth: 200,
                    maxWidth: 280,
                    transition: 'all 0.2s',
                    ...(isOpen ? { borderColor: 'var(--re-brand)', boxShadow: '0 0 0 2px var(--re-brand-muted)' } : {}),
                }}
            >
                <Search size={14} style={{ color: 'var(--re-text-disabled)', flexShrink: 0 }} />
                <input
                    ref={inputRef}
                    type="text"
                    placeholder="Search..."
                    value={query}
                    onChange={e => { setQuery(e.target.value); setIsOpen(true); setSelectedIndex(0); }}
                    onFocus={() => setIsOpen(true)}
                    onKeyDown={handleKeyDown}
                    style={{
                        background: 'transparent',
                        border: 'none',
                        outline: 'none',
                        color: 'var(--re-text-primary)',
                        fontSize: 13,
                        width: '100%',
                        fontFamily: 'inherit',
                    }}
                />
                {query ? (
                    <button
                        onClick={() => { setQuery(''); setIsOpen(false); }}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--re-text-disabled)' }}
                    >
                        <X size={14} />
                    </button>
                ) : (
                    <kbd style={{
                        fontSize: 10,
                        color: 'var(--re-text-disabled)',
                        background: 'var(--re-surface-elevated)',
                        borderRadius: 4,
                        padding: '2px 5px',
                        border: '1px solid var(--re-surface-border)',
                        fontFamily: 'inherit',
                        whiteSpace: 'nowrap',
                    }}>
                        ⌘K
                    </kbd>
                )}
            </div>

            {/* Results Dropdown */}
            {isOpen && query.trim().length > 0 && (
                <div
                    style={{
                        position: 'absolute',
                        top: '100%',
                        left: 0,
                        right: 0,
                        marginTop: 8,
                        background: 'var(--re-nav-dropdown-bg, var(--re-surface-card))',
                        border: '1px solid var(--re-nav-dropdown-border, var(--re-surface-border))',
                        borderRadius: 12,
                        boxShadow: 'var(--re-nav-dropdown-shadow, 0 16px 48px rgba(0,0,0,0.2))',
                        backdropFilter: 'blur(24px)',
                        zIndex: 200,
                        overflow: 'hidden',
                        minWidth: 340,
                    }}
                >
                    {results.length > 0 ? (
                        <div style={{ padding: '6px 0', maxHeight: 400, overflowY: 'auto' }}>
                            {results.map((item, i) => {
                                const Icon = CATEGORY_ICONS[item.category] || FileText;
                                return (
                                    <button
                                        key={item.href}
                                        onClick={() => handleSelect(item)}
                                        onMouseEnter={() => setSelectedIndex(i)}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 12,
                                            width: '100%',
                                            padding: '10px 16px',
                                            background: i === selectedIndex ? 'var(--re-nav-hover, rgba(255,255,255,0.04))' : 'transparent',
                                            border: 'none',
                                            cursor: 'pointer',
                                            textAlign: 'left',
                                            transition: 'background 0.1s',
                                        }}
                                    >
                                        <div style={{
                                            width: 32, height: 32, borderRadius: 8,
                                            background: 'var(--re-brand-muted, rgba(16,185,129,0.1))',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            flexShrink: 0,
                                        }}>
                                            <Icon size={14} style={{ color: 'var(--re-brand)' }} />
                                        </div>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--re-text-primary)' }}>
                                                {item.title}
                                            </div>
                                            <div style={{ fontSize: 11, color: 'var(--re-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                {item.description}
                                            </div>
                                        </div>
                                        <span style={{
                                            fontSize: 9, fontWeight: 600, color: 'var(--re-text-disabled)',
                                            background: 'var(--re-surface-elevated)',
                                            padding: '2px 6px', borderRadius: 4,
                                            textTransform: 'uppercase', letterSpacing: '0.04em',
                                            whiteSpace: 'nowrap',
                                        }}>
                                            {CATEGORY_LABELS[item.category]}
                                        </span>
                                        {i === selectedIndex && (
                                            <ArrowRight size={12} style={{ color: 'var(--re-text-disabled)', flexShrink: 0 }} />
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    ) : (
                        <div style={{ padding: '24px 16px', textAlign: 'center' }}>
                            <p style={{ fontSize: 13, color: 'var(--re-text-muted)' }}>
                                No results for &ldquo;{query}&rdquo;
                            </p>
                            <p style={{ fontSize: 11, color: 'var(--re-text-disabled)', marginTop: 4 }}>
                                Try searching for tools, pages, or FSMA terms
                            </p>
                        </div>
                    )}

                    {/* Footer */}
                    <div style={{
                        borderTop: '1px solid var(--re-nav-divider, var(--re-surface-border))',
                        padding: '8px 16px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                    }}>
                        <span style={{ fontSize: 10, color: 'var(--re-text-disabled)' }}>
                            {results.length} result{results.length !== 1 ? 's' : ''}
                        </span>
                        <div style={{ display: 'flex', gap: 8, fontSize: 10, color: 'var(--re-text-disabled)' }}>
                            <span>↑↓ navigate</span>
                            <span>↵ select</span>
                            <span>esc close</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
