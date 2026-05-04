'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Spinner } from '@/components/ui/spinner';
import {
    Package,
    Plus,
    ShieldCheck,
    Tag,
    Barcode,
    Users,
    Activity,
    Leaf,
    AlertTriangle,
    RefreshCw,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useDashboardRefresh } from '@/hooks/use-dashboard-refresh';

/* ── Types matching ProductCatalogResponse ── */

interface Product {
    id: string;
    name: string;
    category: string;
    ftl_covered: boolean;
    sku: string;
    gtin: string;
    description: string;
    suppliers: string[];
    facilities: string[];
    cte_count: number;
    last_cte: string | null;
    created_at: string;
}

interface ProductCatalogResponse {
    tenant_id: string;
    total: number;
    ftl_covered: number;
    categories: string[];
    products: Product[];
}

const FTL_CATEGORIES = [
    'Leafy Greens', 'Herbs', 'Fresh-Cut Fruits', 'Fresh-Cut Vegetables',
    'Finfish', 'Crustaceans', 'Molluscan Shellfish', 'Smoked Finfish',
    'Soft Cheeses', 'Shell Eggs', 'Nut Butters', 'Ready-to-Eat Deli Salads',
    'Fresh Tomatoes', 'Fresh Peppers', 'Fresh Cucumbers', 'Fresh Sprouts',
    'Tropical Tree Fruits', 'Fresh Melons',
];

async function apiFetchProducts(tenantId: string, apiKey: string): Promise<ProductCatalogResponse> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}`, {
        signal: AbortSignal.timeout(8000),
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiAddProduct(tenantId: string, apiKey: string, name: string, category: string, sku: string): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}`, {
        method: 'POST',
        signal: AbortSignal.timeout(12000),
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
        body: JSON.stringify({ name, category, sku: sku || undefined }),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

export default function ProductCatalogPage() {
    const { isAuthenticated, apiKey } = useAuth();
    const { tenantId } = useTenant();

    const isLoggedIn = isAuthenticated;
    const effectiveTenantId = tenantId;

    const productsQueryClient = useQueryClient();

    const [showAdd, setShowAdd] = useState(false);
    const [newName, setNewName] = useState('');
    const [newCategory, setNewCategory] = useState(FTL_CATEGORIES[0]);
    const [newSku, setNewSku] = useState('');
    const [filterCategory, setFilterCategory] = useState<string>('all');

    const { data: productsData, isLoading: loading, error: productsError, refetch: loadProducts } = useQuery({
        queryKey: ['products', effectiveTenantId],
        queryFn: async () => {
            const data = await apiFetchProducts(effectiveTenantId!, apiKey || '');
            const fetchedProducts = data.products || [];
            if (fetchedProducts.length > 0) {
                return { products: fetchedProducts, categories: data.categories || [], totalFtl: data.ftl_covered || 0 };
            }

            // Fallback: extract unique products from supplier TLCs (bulk upload data)
            try {
                const { apiClient } = await import('@/lib/api-client');
                const tlcs = await apiClient.listSupplierTLCs();
                if (tlcs && tlcs.length > 0) {
                    const productMap = new Map<string, Product>();
                    for (const tlc of tlcs) {
                        const name = tlc.product_description || tlc.tlc_code;
                        if (!productMap.has(name)) {
                            productMap.set(name, {
                                id: tlc.id || name,
                                name,
                                category: 'Uncategorized',
                                sku: tlc.tlc_code,
                                gtin: '',
                                description: tlc.product_description || '',
                                suppliers: [],
                                facilities: [],
                                cte_count: 1,
                                ftl_covered: false,
                                last_cte: null,
                                created_at: new Date().toISOString(),
                            });
                        } else {
                            const existing = productMap.get(name)!;
                            existing.cte_count += 1;
                        }
                    }
                    return { products: Array.from(productMap.values()), categories: ['Uncategorized'], totalFtl: 0 };
                }
            } catch {
                // Supplier fallback failed -- show empty state
            }
            return { products: [], categories: [], totalFtl: 0 };
        },
        enabled: isLoggedIn && !!effectiveTenantId,
        retry: false,
    });

    const products = productsData?.products ?? [];
    const categories = productsData?.categories ?? [];
    const totalFtl = productsData?.totalFtl ?? 0;
    const error = productsError?.message ?? null;

    // Re-fetch when data changes elsewhere (upload, bulk import, tab refocus)
    useDashboardRefresh(() => { loadProducts(); });

    const addProductMutation = useMutation({
        mutationFn: () => apiAddProduct(effectiveTenantId!, apiKey || '', newName, newCategory, newSku),
        onSuccess: () => {
            setNewName(''); setNewSku(''); setShowAdd(false);
            productsQueryClient.invalidateQueries({ queryKey: ['products', effectiveTenantId] });
        },
    });

    const adding = addProductMutation.isPending;

    const handleAdd = () => {
        if (!newName) return;
        addProductMutation.mutate();
    };

    const filtered = filterCategory === 'all' ? products : products.filter(p => p.category === filterCategory);
    const totalCtes = products.reduce((s, p) => s + p.cte_count, 0);
    const uniqueCategories = [...new Set(products.map(p => p.category))].sort();

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <Package className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Product Catalog
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            FTL-covered products in your traceability program
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" className="rounded-xl min-h-[44px]" onClick={() => loadProducts()} disabled={loading}>
                            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button onClick={() => setShowAdd(!showAdd)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[44px] active:scale-[0.97]">
                            <Plus className="h-4 w-4 mr-1" /> Add Product
                        </Button>
                    </div>
                </div>

                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to view your product catalog.
                        </CardContent>
                    </Card>
                )}

                {loading && products.length === 0 && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {error && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {isLoggedIn && products.length > 0 && (
                    <>
                        {/* Stats */}
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
                            {[
                                { label: 'Total Products', value: products.length, icon: Package },
                                { label: 'FTL Covered', value: totalFtl, icon: ShieldCheck },
                                { label: 'Categories', value: uniqueCategories.length, icon: Tag },
                                { label: 'Total CTEs', value: totalCtes, icon: Activity },
                            ].map((stat) => (
                                <Card key={stat.label} className="border-[var(--re-border-default)]">
                                    <CardContent className="py-3 sm:py-4">
                                        <div className="flex items-center gap-1.5 sm:gap-2 mb-1">
                                            <stat.icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                            <span className="text-[11px] sm:text-xs text-muted-foreground truncate">{stat.label}</span>
                                        </div>
                                        <div className="text-xl sm:text-2xl font-bold">{stat.value}</div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>

                        {/* Add Form */}
                        {showAdd && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                                <Card className="border-[var(--re-brand)]">
                                    <CardContent className="py-4">
                                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
                                            <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Product name" className="rounded-xl min-h-[44px]" />
                                            <select value={newCategory} onChange={e => setNewCategory(e.target.value)} className="flex h-10 min-h-[44px] rounded-xl border border-input bg-background px-3 text-sm">
                                                {FTL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                            </select>
                                            <Input value={newSku} onChange={e => setNewSku(e.target.value)} placeholder="SKU (optional)" className="rounded-xl min-h-[44px]" />
                                            <Button onClick={handleAdd} disabled={adding} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[48px] active:scale-[0.97]">
                                                {adding ? <Spinner size="sm" /> : <><Plus className="h-4 w-4 mr-1" /> Add</>}
                                            </Button>
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        )}

                        {/* Category Filter */}
                        <div className="flex gap-1.5 sm:gap-2 overflow-x-auto scrollbar-none no-scrollbar pb-1 -mx-1 px-1">
                            <button
                                onClick={() => setFilterCategory('all')}
                                className={`px-3 min-h-[44px] rounded-full text-xs font-medium border transition-all whitespace-nowrap active:scale-[0.96] ${
                                    filterCategory === 'all'
                                        ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                        : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                }`}
                            >
                                All ({products.length})
                            </button>
                            {uniqueCategories.map(cat => {
                                const count = products.filter(p => p.category === cat).length;
                                return (
                                    <button
                                        key={cat}
                                        onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
                                        className={`px-3 min-h-[44px] rounded-full text-xs font-medium border transition-all whitespace-nowrap active:scale-[0.96] ${
                                            filterCategory === cat
                                                ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                                : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                        }`}
                                    >
                                        {cat} ({count})
                                    </button>
                                );
                            })}
                        </div>

                        {/* Product List */}
                        <div className="space-y-3">
                            {filtered.map((product, i) => (
                                <motion.div key={product.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                                    <Card className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
                                        <CardContent className="py-3 sm:py-4">
                                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5 sm:gap-2 mb-1 flex-wrap">
                                                        <Leaf className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                        <span className="font-medium text-sm sm:text-base">{product.name}</span>
                                                        {product.ftl_covered && (
                                                            <Badge className="text-[9px] px-1.5 py-0 bg-re-brand-muted text-re-brand">
                                                                <ShieldCheck className="h-2.5 w-2.5 mr-0.5" /> FTL
                                                            </Badge>
                                                        )}
                                                        <Badge variant="outline" className="text-[9px] py-0 hidden sm:inline-flex">{product.category}</Badge>
                                                    </div>
                                                    <div className="flex items-center gap-3 sm:gap-4 text-[11px] sm:text-xs text-muted-foreground flex-wrap">
                                                        {product.sku && <span className="flex items-center gap-1"><Barcode className="h-3 w-3" /> {product.sku}</span>}
                                                        <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {product.suppliers.length} supplier{product.suppliers.length !== 1 ? 's' : ''}</span>
                                                        <span className="flex items-center gap-1"><Activity className="h-3 w-3" /> {product.cte_count} CTEs</span>
                                                    </div>
                                                </div>
                                                {product.suppliers.length > 0 && (
                                                    <div className="flex gap-1 flex-wrap">
                                                        {product.suppliers.slice(0, 3).map(s => (
                                                            <Badge key={s} variant="outline" className="text-[9px] py-0">{s}</Badge>
                                                        ))}
                                                        {product.suppliers.length > 3 && (
                                                            <Badge variant="outline" className="text-[9px] py-0">+{product.suppliers.length - 3}</Badge>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </CardContent>
                                    </Card>
                                </motion.div>
                            ))}
                        </div>
                    </>
                )}

                {isLoggedIn && !loading && products.length === 0 && !error && (
                    <div className="text-center py-12 text-muted-foreground">
                        <Package className="h-10 w-10 mx-auto mb-3 opacity-30" />
                        <div className="font-medium">No products yet</div>
                        <div className="text-sm">Add your first FTL product to start tracking</div>
                    </div>
                )}
            </div>
        </div>
    );
}
