'use client';

import { useState } from 'react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Input } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { getServiceURL } from '@/lib/api-config';
import type { LucideIcon } from 'lucide-react';
import {
    Key,
    Shield,
    Users,
    Copy,
    Play,
    Code,
    Book,
    Lock,
    Globe,
    Layers,
    Activity,
    Search,
    ChevronRight,
    ExternalLink,
} from 'lucide-react';

interface Endpoint {
    method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    path: string;
    description: string;
    requiresAuth: boolean;
    category: string;
}

const endpoints: Endpoint[] = [
    // Health & Metrics
    { method: 'GET', path: '/health', description: 'Health check endpoint', requiresAuth: false, category: 'Health & Metrics' },
    { method: 'GET', path: '/health/consumer', description: 'Consumer health status', requiresAuth: false, category: 'Health & Metrics' },
    { method: 'GET', path: '/metrics', description: 'System metrics', requiresAuth: true, category: 'Health & Metrics' },

    // Authentication
    { method: 'POST', path: '/auth/challenges', description: 'Start email code sign-in', requiresAuth: false, category: 'Authentication' },
    { method: 'POST', path: '/auth/webauthn/login/generate-options', description: 'Start passkey sign-in', requiresAuth: false, category: 'Authentication' },
    { method: 'POST', path: '/auth/register', description: 'Register initial admin', requiresAuth: false, category: 'Authentication' },
    { method: 'POST', path: '/auth/refresh', description: 'Refresh session token', requiresAuth: true, category: 'Authentication' },
    { method: 'GET', path: '/auth/me', description: 'Get current user info', requiresAuth: true, category: 'Authentication' },
    { method: 'POST', path: '/auth/logout-all', description: 'Revoke all sessions', requiresAuth: true, category: 'Authentication' },

    // API Key Management
    { method: 'POST', path: '/v1/admin/keys', description: 'Create API key', requiresAuth: true, category: 'API Keys' },
    { method: 'GET', path: '/v1/admin/keys', description: 'List API keys', requiresAuth: true, category: 'API Keys' },
    { method: 'DELETE', path: '/v1/admin/keys/{key_id}', description: 'Revoke API key', requiresAuth: true, category: 'API Keys' },

    // Tenant Management
    { method: 'POST', path: '/v1/admin/tenants', description: 'Create tenant', requiresAuth: true, category: 'Tenants' },
    { method: 'GET', path: '/v1/admin/users', description: 'List users', requiresAuth: true, category: 'Tenants' },
    { method: 'PATCH', path: '/v1/admin/users/{user_id}/role', description: 'Update user role', requiresAuth: true, category: 'Tenants' },

    // Content Overlay
    { method: 'POST', path: '/v1/overlay/controls', description: 'Create control framework', requiresAuth: true, category: 'Overlay' },
    { method: 'GET', path: '/v1/overlay/controls', description: 'List controls', requiresAuth: true, category: 'Overlay' },
    { method: 'POST', path: '/v1/overlay/products', description: 'Create product', requiresAuth: true, category: 'Overlay' },
    { method: 'GET', path: '/v1/overlay/products', description: 'List products', requiresAuth: true, category: 'Overlay' },
    { method: 'POST', path: '/v1/overlay/mappings', description: 'Create provision mapping', requiresAuth: true, category: 'Overlay' },
    { method: 'GET', path: '/v1/overlay/products/{product_id}/requirements', description: 'Get product requirements', requiresAuth: true, category: 'Overlay' },
    { method: 'GET', path: '/v1/overlay/products/{product_id}/compliance-gaps', description: 'Get compliance gaps', requiresAuth: true, category: 'Overlay' },

    // Compliance
    { method: 'GET', path: '/v1/compliance/status/{tenant_id}', description: 'Get compliance status', requiresAuth: true, category: 'Compliance' },
    { method: 'POST', path: '/v1/compliance/snapshots/{tenant_id}', description: 'Create snapshot', requiresAuth: true, category: 'Compliance' },
    { method: 'GET', path: '/v1/compliance/snapshots/{tenant_id}', description: 'List snapshots', requiresAuth: true, category: 'Compliance' },
    { method: 'GET', path: '/v1/compliance/alerts/{tenant_id}', description: 'List alerts', requiresAuth: true, category: 'Compliance' },

];


const categoryIcons: Record<string, LucideIcon> = {
    'Health & Metrics': Activity,
    'Authentication': Lock,
    'API Keys': Key,
    'Tenants': Users,
    'Overlay': Layers,
    'Compliance': Shield,
    'Verticals': Globe,
};

/**
 * HTTP verb tones. The seven per-category gradients this file used to carry
 * are gone: a category is an ordering device, not a state, and the only colour
 * left on the page is the verb pill (SPEC §1.6).
 */
const methodTones: Record<Endpoint['method'], BadgeTone> = {
    GET: 'info',
    POST: 'success',
    PUT: 'warning',
    DELETE: 'danger',
    PATCH: 'corrected',
};

export default function AdminAPIConsolePage() {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [apiKey, setApiKey] = useState('');

    const categories = Array.from(new Set(endpoints.map(e => e.category)));

    const filteredEndpoints = endpoints.filter(endpoint => {
        const matchesSearch = endpoint.path.toLowerCase().includes(searchQuery.toLowerCase()) ||
            endpoint.description.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = !selectedCategory || endpoint.category === selectedCategory;
        return matchesSearch && matchesCategory;
    });

    const groupedEndpoints = filteredEndpoints.reduce((acc, endpoint) => {
        if (!acc[endpoint.category]) acc[endpoint.category] = [];
        acc[endpoint.category].push(endpoint);
        return acc;
    }, {} as Record<string, Endpoint[]>);

    return (
        <PageContainer>
            <PageHeader
                title="Admin API Console"
                description={'Explore, test, and integrate with RegEngine’s tenant, traceability, and compliance APIs'}
            />

            <div className="space-y-6">
                {/* Quick Stats */}
                <div className="grid grid-cols-2 gap-4 sm:max-w-md">
                    <StatTile label="Endpoints" value={endpoints.length} />
                    <StatTile label="Categories" value={categories.length} />
                </div>

                {/* Search and Authentication */}
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
                    <Card padding="compact" className="lg:col-span-2">
                        <label htmlFor="api-console-search" className="sr-only">Search endpoints by path or description</label>
                        <Input
                            id="api-console-search"
                            type="search"
                            placeholder="Search endpoints by path or description..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            leadingIcon={<Search strokeWidth={1.75} />}
                        />
                    </Card>

                    <Card padding="compact">
                        <label htmlFor="api-console-key" className="sr-only">API Key (optional)</label>
                        <Input
                            id="api-console-key"
                            type="password"
                            placeholder="API Key (optional)"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                            leadingIcon={<Key strokeWidth={1.75} />}
                        />
                    </Card>
                </div>

                {/* Category Filter Pills */}
                <div className="-mx-1 flex items-center gap-2 overflow-x-auto scrollbar-none no-scrollbar px-1 pb-2">
                    <Button
                        variant={selectedCategory === null ? 'secondary' : 'ghost'}
                        size="sm"
                        aria-pressed={selectedCategory === null}
                        className="shrink-0"
                        onClick={() => setSelectedCategory(null)}
                    >
                        All Categories
                    </Button>
                    {categories.map((category) => {
                        const Icon = categoryIcons[category];
                        return (
                            <Button
                                key={category}
                                variant={selectedCategory === category ? 'secondary' : 'ghost'}
                                size="sm"
                                aria-pressed={selectedCategory === category}
                                className="shrink-0"
                                onClick={() => setSelectedCategory(category)}
                                leadingIcon={Icon ? <Icon strokeWidth={1.75} aria-hidden="true" /> : undefined}
                            >
                                {category}
                                <Badge size="sm" className="ml-1">
                                    {endpoints.filter(e => e.category === category).length}
                                </Badge>
                            </Button>
                        );
                    })}
                </div>

                {/* Main Content Grid */}
                <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                    {/* Endpoints List */}
                    <div className="space-y-6 lg:col-span-2">
                        {Object.entries(groupedEndpoints).map(([category, categoryEndpoints]) => (
                            <Card key={category}>
                                <CardHeader>
                                    <div className="min-w-0">
                                        <CardTitle>{category}</CardTitle>
                                        <CardDescription>
                                            {categoryEndpoints.length} endpoint{categoryEndpoints.length !== 1 ? 's' : ''}
                                        </CardDescription>
                                    </div>
                                </CardHeader>
                                <CardContent className="p-0">
                                    <ul className="divide-y divide-re-border-subtle">
                                        {categoryEndpoints.map((endpoint) => {
                                            const isSelected = selectedEndpoint?.path === endpoint.path;
                                            return (
                                                <li key={endpoint.path}>
                                                    <button
                                                        type="button"
                                                        aria-pressed={isSelected}
                                                        onClick={() => setSelectedEndpoint(endpoint)}
                                                        className={`flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition-colors duration-120 motion-reduce:transition-none ${isSelected ? 'bg-re-brand-muted' : 'hover:bg-re-surface-inset'}`}
                                                    >
                                                        <div className="min-w-0 flex-1">
                                                            <div className="mb-2 flex flex-wrap items-center gap-3">
                                                                <Badge tone={methodTones[endpoint.method]} size="sm" mono>
                                                                    {endpoint.method}
                                                                </Badge>
                                                                <code className="truncate font-mono text-[0.8125rem] text-re-text-primary">
                                                                    {endpoint.path}
                                                                </code>
                                                            </div>
                                                            <p className="text-small text-re-text-tertiary">{endpoint.description}</p>
                                                        </div>
                                                        <div className="flex shrink-0 items-center gap-2">
                                                            {endpoint.requiresAuth && (
                                                                <Lock className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                            )}
                                                            <ChevronRight className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                                        </div>
                                                    </button>
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </CardContent>
                            </Card>
                        ))}

                        {filteredEndpoints.length === 0 && (
                            <EmptyState
                                icon={Search}
                                title="No endpoints found"
                                description="Try adjusting your search or filter"
                            />
                        )}
                    </div>

                    {/* Endpoint Details Panel */}
                    <div className="h-fit space-y-6 lg:sticky lg:top-6">
                        {selectedEndpoint ? (
                            <Card>
                                <CardHeader>
                                    <div className="min-w-0">
                                        <div className="mb-2 flex flex-wrap items-center gap-2">
                                            <Badge tone={methodTones[selectedEndpoint.method]} size="sm" mono>
                                                {selectedEndpoint.method}
                                            </Badge>
                                            {selectedEndpoint.requiresAuth && (
                                                <Badge tone="warning" size="sm">
                                                    <Lock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    Auth Required
                                                </Badge>
                                            )}
                                        </div>
                                        <CardTitle className="break-all font-mono">
                                            {selectedEndpoint.path}
                                        </CardTitle>
                                        <CardDescription>
                                            {selectedEndpoint.description}
                                        </CardDescription>
                                    </div>
                                </CardHeader>

                                <CardContent className="space-y-4">
                                    <div>
                                        <h4 className="mb-2 text-subheading text-re-text-primary">Request Example</h4>
                                        <pre className="overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-[0.8125rem] text-re-text-secondary">
                                            <code>{`curl -X ${selectedEndpoint.method} \\
  ${getServiceURL('admin')}${selectedEndpoint.path} \\${selectedEndpoint.requiresAuth ? '\n  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\' : ''}
  -H "Content-Type: application/json"`}</code>
                                        </pre>
                                    </div>

                                    <div className="flex gap-2">
                                        <Button
                                            disabled
                                            title="Coming Soon"
                                            className="flex-1"
                                            leadingIcon={<Play strokeWidth={1.75} aria-hidden="true" />}
                                        >
                                            Try it out
                                        </Button>
                                        <Button
                                            disabled
                                            title="Coming Soon"
                                            variant="outline"
                                            size="icon"
                                            aria-label="Copy request example"
                                            className="shrink-0"
                                        >
                                            <Copy className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                        </Button>
                                    </div>

                                    <div className="border-t border-re-border-subtle pt-4">
                                        <a
                                            href={`${getServiceURL('admin')}/docs#${selectedEndpoint.path.replace(/\//g, '-')}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-2 text-ui text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
                                        >
                                            <Book className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            View full documentation
                                            <ExternalLink className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        </a>
                                    </div>
                                </CardContent>
                            </Card>
                        ) : (
                            <EmptyState
                                icon={Code}
                                title="Select an endpoint"
                                description="Click on any endpoint to view details"
                            />
                        )}

                        {/* Quick Links */}
                        <Card>
                            <CardHeader>
                                <div className="min-w-0">
                                    <CardTitle>Quick Links</CardTitle>
                                </div>
                            </CardHeader>
                            <CardContent className="p-0">
                                <ul className="divide-y divide-re-border-subtle">
                                    <li>
                                        <a
                                            href={`${getServiceURL('admin')}/docs`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center justify-between gap-3 px-5 py-3 transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                                        >
                                            <span className="text-ui text-re-text-primary">Swagger UI</span>
                                            <ExternalLink className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        </a>
                                    </li>
                                    <li>
                                        <a
                                            href={`${getServiceURL('admin')}/redoc`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center justify-between gap-3 px-5 py-3 transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                                        >
                                            <span className="text-ui text-re-text-primary">ReDoc</span>
                                            <ExternalLink className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        </a>
                                    </li>
                                    <li>
                                        <a
                                            href="/admin"
                                            className="flex items-center justify-between gap-3 px-5 py-3 transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                                        >
                                            <span className="text-ui text-re-text-primary">API Key Management</span>
                                            <ChevronRight className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        </a>
                                    </li>
                                </ul>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </div>
        </PageContainer>
    );
}
