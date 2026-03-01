'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

import { PageContainer } from '@/components/layout/page-container';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
    Terminal,
    Key,
    Database,
    Shield,
    Users,
    FileText,
    AlertCircle,
    CheckCircle,
    Copy,
    Play,
    Code,
    Book,
    Zap,
    Lock,
    Globe,
    Layers,
    Activity,
    Settings,
    Film,
    Heart,
    DollarSign,
    Gamepad2,
    Cpu,
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
    { method: 'POST', path: '/auth/login', description: 'User login', requiresAuth: false, category: 'Authentication' },
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

    // PCOS (Production Compliance OS)
    { method: 'POST', path: '/pcos/projects', description: 'Create project', requiresAuth: true, category: 'PCOS' },
    { method: 'GET', path: '/pcos/projects', description: 'List projects', requiresAuth: true, category: 'PCOS' },
    { method: 'POST', path: '/pcos/companies', description: 'Create company', requiresAuth: true, category: 'PCOS' },
    { method: 'GET', path: '/pcos/projects/{project_id}/gate-status', description: 'Get regulatory gate status', requiresAuth: true, category: 'PCOS' },
    { method: 'POST', path: '/pcos/budgets/{budget_id}/validate-rates', description: 'Validate union rates', requiresAuth: true, category: 'PCOS' },

    // Verticals
    { method: 'POST', path: '/verticals/healthcare-enterprise/projects', description: 'Create healthcare project', requiresAuth: true, category: 'Verticals' },
    { method: 'POST', path: '/verticals/finance/reconcile', description: 'Run finance reconciliation', requiresAuth: true, category: 'Verticals' },
    { method: 'POST', path: '/verticals/gaming/risk-score', description: 'Calculate player risk', requiresAuth: true, category: 'Verticals' },
    { method: 'POST', path: '/verticals/energy/validate-firmware', description: 'Validate energy assets', requiresAuth: true, category: 'Verticals' },
];

const categoryIcons: Record<string, any> = {
    'Health & Metrics': Activity,
    'Authentication': Lock,
    'API Keys': Key,
    'Tenants': Users,
    'Overlay': Layers,
    'Compliance': Shield,
    'PCOS': Film,
    'Verticals': Globe,
};

const categoryColors: Record<string, string> = {
    'Health & Metrics': 'from-green-500 to-emerald-600',
    'Authentication': 'from-purple-500 to-indigo-600',
    'API Keys': 'from-orange-500 to-amber-600',
    'Tenants': 'from-blue-500 to-cyan-600',
    'Overlay': 'from-pink-500 to-rose-600',
    'Compliance': 'from-red-500 to-orange-600',
    'PCOS': 'from-violet-500 to-purple-600',
    'Verticals': 'from-teal-500 to-green-600',
};

const methodColors = {
    GET: 'bg-blue-500/10 text-blue-600 border-blue-500/30',
    POST: 'bg-green-500/10 text-green-600 border-green-500/30',
    PUT: 'bg-orange-500/10 text-orange-600 border-orange-500/30',
    DELETE: 'bg-red-500/10 text-red-600 border-red-500/30',
    PATCH: 'bg-purple-500/10 text-purple-600 border-purple-500/30',
};

export default function AdminAPIConsolePage() {
    const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
    const [selectedEndpoint, setSelectedEndpoint] = useState<Endpoint | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [apiKey, setApiKey] = useState('');
    const [testResponse, setTestResponse] = useState<any>(null);

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
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-950">

            {/* Animated background */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 -left-48 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl animate-pulse" />
                <div className="absolute bottom-1/4 -right-48 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse delay-1000" />
                <div className="absolute top-3/4 left-1/3 w-96 h-96 bg-pink-500/10 rounded-full blur-3xl animate-pulse delay-500" />
            </div>

            <PageContainer>
                <div className="relative z-10">
                    {/* Hero Section */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-center mb-12 pt-8"
                    >
                        <motion.div
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            transition={{ type: "spring", stiffness: 200, delay: 0.1 }}
                            className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-purple-500 to-pink-600 mb-6 shadow-2xl shadow-purple-500/50"
                        >
                            <Terminal className="w-10 h-10 text-white" />
                        </motion.div>

                        <h1 className="text-6xl font-bold mb-4 bg-gradient-to-r from-purple-400 via-pink-400 to-blue-400 bg-clip-text text-transparent">
                            Admin API Console
                        </h1>
                        <p className="text-xl text-gray-300 max-w-3xl mx-auto">
                            Explore, test, and integrate with RegEngine&apos;s powerful regulatory intelligence platform
                        </p>

                        {/* Quick Stats */}
                        <div className="flex items-center justify-center gap-6 mt-8">
                            <div className="px-6 py-3 rounded-xl bg-white/5 backdrop-blur-sm border border-white/10">
                                <div className="text-3xl font-bold text-white">{endpoints.length}</div>
                                <div className="text-sm text-gray-400">Endpoints</div>
                            </div>
                            <div className="px-6 py-3 rounded-xl bg-white/5 backdrop-blur-sm border border-white/10">
                                <div className="text-3xl font-bold text-white">{categories.length}</div>
                                <div className="text-sm text-gray-400">Categories</div>
                            </div>
                            <div className="px-6 py-3 rounded-xl bg-white/5 backdrop-blur-sm border border-white/10">
                                <div className="flex items-center gap-2">
                                    <CheckCircle className="w-5 h-5 text-green-400" />
                                    <span className="text-sm text-gray-400">Live</span>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Search and Authentication */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
                        <Card className="lg:col-span-2 bg-white/5 backdrop-blur-sm border-white/10">
                            <CardContent className="pt-6">
                                <div className="relative">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                    <Input
                                        placeholder="Search endpoints by path or description..."
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        className="pl-10 bg-white/5 border-white/10 text-white placeholder:text-gray-500"
                                    />
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="bg-gradient-to-br from-orange-500/10 to-amber-500/10 border-orange-500/20 backdrop-blur-sm">
                            <CardContent className="pt-6">
                                <div className="flex items-center gap-3">
                                    <Key className="w-5 h-5 text-orange-400" />
                                    <Input
                                        type="password"
                                        placeholder="API Key (optional)"
                                        value={apiKey}
                                        onChange={(e) => setApiKey(e.target.value)}
                                        className="bg-white/5 border-white/10 text-white placeholder:text-gray-500"
                                    />
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Category Filter Pills */}
                    <div className="flex items-center gap-3 mb-8 overflow-x-auto pb-2">
                        <Button
                            variant={selectedCategory === null ? "default" : "outline"}
                            size="sm"
                            onClick={() => setSelectedCategory(null)}
                            className={selectedCategory === null ? "bg-gradient-to-r from-purple-500 to-pink-600" : "bg-white/5 border-white/10 text-white"}
                        >
                            All Categories
                        </Button>
                        {categories.map((category) => {
                            const Icon = categoryIcons[category];
                            return (
                                <Button
                                    key={category}
                                    variant={selectedCategory === category ? "default" : "outline"}
                                    size="sm"
                                    onClick={() => setSelectedCategory(category)}
                                    className={selectedCategory === category
                                        ? `bg-gradient-to-r ${categoryColors[category]}`
                                        : "bg-white/5 border-white/10 text-white hover:bg-white/10"
                                    }
                                >
                                    <Icon className="w-4 h-4 mr-2" />
                                    {category}
                                    <Badge variant="secondary" className="ml-2 bg-white/20">
                                        {endpoints.filter(e => e.category === category).length}
                                    </Badge>
                                </Button>
                            );
                        })}
                    </div>

                    {/* Main Content Grid */}
                    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        {/* Endpoints List */}
                        <div className="lg:col-span-2 space-y-6">
                            {Object.entries(groupedEndpoints).map(([category, categoryEndpoints]) => {
                                const Icon = categoryIcons[category];
                                const colorClass = categoryColors[category];

                                return (
                                    <motion.div
                                        key={category}
                                        initial={{ opacity: 0, y: 20 }}
                                        animate={{ opacity: 1, y: 0 }}
                                    >
                                        <Card className="bg-white/5 backdrop-blur-sm border-white/10 overflow-hidden">
                                            <CardHeader className={`bg-gradient-to-r ${colorClass} border-b border-white/10`}>
                                                <div className="flex items-center gap-3">
                                                    <div className="p-2 rounded-lg bg-white/20 backdrop-blur-sm">
                                                        <Icon className="w-5 h-5 text-white" />
                                                    </div>
                                                    <div>
                                                        <CardTitle className="text-white">{category}</CardTitle>
                                                        <CardDescription className="text-white/70">
                                                            {categoryEndpoints.length} endpoint{categoryEndpoints.length !== 1 ? 's' : ''}
                                                        </CardDescription>
                                                    </div>
                                                </div>
                                            </CardHeader>
                                            <CardContent className="p-0">
                                                <div className="divide-y divide-white/10">
                                                    {categoryEndpoints.map((endpoint, idx) => (
                                                        <motion.div
                                                            key={endpoint.path}
                                                            initial={{ opacity: 0, x: -20 }}
                                                            animate={{ opacity: 1, x: 0 }}
                                                            transition={{ delay: idx * 0.05 }}
                                                            onClick={() => setSelectedEndpoint(endpoint)}
                                                            className={`p-4 cursor-pointer transition-all hover:bg-white/10 ${selectedEndpoint?.path === endpoint.path ? 'bg-white/10 border-l-4 border-purple-500' : ''
                                                                }`}
                                                        >
                                                            <div className="flex items-start justify-between gap-4">
                                                                <div className="flex-1 min-w-0">
                                                                    <div className="flex items-center gap-3 mb-2">
                                                                        <Badge className={`${methodColors[endpoint.method]} border font-mono text-xs px-2 py-0.5`}>
                                                                            {endpoint.method}
                                                                        </Badge>
                                                                        <code className="text-sm text-gray-300 font-mono truncate">
                                                                            {endpoint.path}
                                                                        </code>
                                                                    </div>
                                                                    <p className="text-sm text-gray-400">{endpoint.description}</p>
                                                                </div>
                                                                <div className="flex items-center gap-2 flex-shrink-0">
                                                                    {endpoint.requiresAuth && (
                                                                        <Lock className="w-4 h-4 text-amber-400" />
                                                                    )}
                                                                    <ChevronRight className="w-4 h-4 text-gray-500" />
                                                                </div>
                                                            </div>
                                                        </motion.div>
                                                    ))}
                                                </div>
                                            </CardContent>
                                        </Card>
                                    </motion.div>
                                );
                            })}

                            {filteredEndpoints.length === 0 && (
                                <Card className="bg-white/5 backdrop-blur-sm border-white/10">
                                    <CardContent className="py-12 text-center">
                                        <Search className="w-12 h-12 text-gray-500 mx-auto mb-4" />
                                        <h3 className="text-lg font-semibold text-white mb-2">No endpoints found</h3>
                                        <p className="text-gray-400">Try adjusting your search or filter</p>
                                    </CardContent>
                                </Card>
                            )}
                        </div>

                        {/* Endpoint Details Panel */}
                        <div className="lg:sticky lg:top-6 h-fit">
                            <AnimatePresence mode="wait">
                                {selectedEndpoint ? (
                                    <motion.div
                                        key={selectedEndpoint.path}
                                        initial={{ opacity: 0, scale: 0.95 }}
                                        animate={{ opacity: 1, scale: 1 }}
                                        exit={{ opacity: 0, scale: 0.95 }}
                                    >
                                        <Card className="bg-white/5 backdrop-blur-sm border-white/10">
                                            <CardHeader className="border-b border-white/10">
                                                <div className="flex items-center gap-2 mb-2">
                                                    <Badge className={`${methodColors[selectedEndpoint.method]} border font-mono`}>
                                                        {selectedEndpoint.method}
                                                    </Badge>
                                                    {selectedEndpoint.requiresAuth && (
                                                        <Badge className="bg-amber-500/10 text-amber-400 border-amber-500/30">
                                                            <Lock className="w-3 h-3 mr-1" />
                                                            Auth Required
                                                        </Badge>
                                                    )}
                                                </div>
                                                <CardTitle className="text-white font-mono text-lg break-all">
                                                    {selectedEndpoint.path}
                                                </CardTitle>
                                                <CardDescription className="text-gray-400">
                                                    {selectedEndpoint.description}
                                                </CardDescription>
                                            </CardHeader>

                                            <CardContent className="space-y-4 pt-6">
                                                <div>
                                                    <h4 className="text-sm font-semibold text-white mb-2">Request Example</h4>
                                                    <pre className="bg-black/50 p-4 rounded-lg text-xs text-gray-300 overflow-x-auto border border-white/10">
                                                        <code>{`curl -X ${selectedEndpoint.method} \\
  http://localhost:8400${selectedEndpoint.path} \\${selectedEndpoint.requiresAuth ? '\n  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\' : ''}
  -H "Content-Type: application/json"`}</code>
                                                    </pre>
                                                </div>

                                                <div className="flex gap-2">
                                                    <Button className="flex-1 bg-gradient-to-r from-purple-500 to-pink-600 hover:from-purple-600 hover:to-pink-700">
                                                        <Play className="w-4 h-4 mr-2" />
                                                        Try it out
                                                    </Button>
                                                    <Button variant="outline" className="bg-white/5 border-white/10 text-white hover:bg-white/10">
                                                        <Copy className="w-4 h-4" />
                                                    </Button>
                                                </div>

                                                <div className="pt-4 border-t border-white/10">
                                                    <a
                                                        href={`http://localhost:8400/docs#${selectedEndpoint.path.replace(/\//g, '-')}`}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="flex items-center gap-2 text-sm text-purple-400 hover:text-purple-300 transition-colors"
                                                    >
                                                        <Book className="w-4 h-4" />
                                                        View full documentation
                                                        <ExternalLink className="w-3 h-3" />
                                                    </a>
                                                </div>
                                            </CardContent>
                                        </Card>
                                    </motion.div>
                                ) : (
                                    <motion.div
                                        initial={{ opacity: 0 }}
                                        animate={{ opacity: 1 }}
                                        exit={{ opacity: 0 }}
                                    >
                                        <Card className="bg-white/5 backdrop-blur-sm border-white/10">
                                            <CardContent className="py-12 text-center">
                                                <Code className="w-12 h-12 text-gray-500 mx-auto mb-4" />
                                                <h3 className="text-lg font-semibold text-white mb-2">Select an endpoint</h3>
                                                <p className="text-gray-400">Click on any endpoint to view details and test it</p>
                                            </CardContent>
                                        </Card>
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* Quick Links */}
                            <Card className="mt-6 bg-gradient-to-br from-blue-500/10 to-purple-500/10 border-blue-500/20 backdrop-blur-sm">
                                <CardHeader>
                                    <CardTitle className="text-white flex items-center gap-2">
                                        <Zap className="w-5 h-5 text-yellow-400" />
                                        Quick Links
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-2">
                                    <a
                                        href="http://localhost:8400/docs"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors border border-white/10 group"
                                    >
                                        <span className="text-sm text-white">Swagger UI</span>
                                        <ExternalLink className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
                                    </a>
                                    <a
                                        href="http://localhost:8400/redoc"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors border border-white/10 group"
                                    >
                                        <span className="text-sm text-white">ReDoc</span>
                                        <ExternalLink className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
                                    </a>
                                    <a
                                        href="/admin"
                                        className="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors border border-white/10 group"
                                    >
                                        <span className="text-sm text-white">API Key Management</span>
                                        <ChevronRight className="w-4 h-4 text-gray-400 group-hover:text-white transition-colors" />
                                    </a>
                                </CardContent>
                            </Card>
                        </div>
                    </div>
                </div>
            </PageContainer>
        </div>
    );
}
