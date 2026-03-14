'use client';

import React, { useState, useEffect, useCallback } from 'react';
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

async function apiFetchProducts(tenantId: string): Promise<ProductCatalogResponse> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/products/${tenantId}`, {
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
}

async function apiAddProduct(tenantId: string, name: string, category: string, sku: string): Promise<void> {
    const apiKey = typeof window !== 'undefined' ? localStorage.getItem('re-api-key') || '' : '';
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetch(`${base}/api/v1/products/${tenantId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey },
        body: JSON.stringify({ name, category, sku: sku || undefined }),
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
}

export default function ProductCatalogPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = Boolean(apiKey);

    const [products, setProducts] = useState<Product[]>([]);
    const [categories, setCategories] = useState<string[]>([]);
    const [totalFtl, setTotalFtl] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [showAdd, setShowAdd] = useState(false);
    const [newName, setNewName] = useState('');
    const [newCategory, setNewCategory] = useState(FTL_CATEGORIES[0]);
    const [newSku, setNewSku] = useState('');
    const [adding, setAdding] = useState(false);
    const [filterCategory, setFilterCategory] = useState<string>('all');

    const loadProducts = useCallback(async () => {
        if (!isLoggedIn || !tenantId) return;
        setLoading(true);
        setError(null);
        try {
            const data = await apiFetchProducts(tenantId);
            setProducts(data.products || []);
            setCategories(data.categories || []);
            setTotalFtl(data.ftl_covered || 0);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load products');
        } finally {
            setLoading(false);
        }
    }, [isLoggedIn, tenantId]);

    useEffect(() => { loadProducts(); }, [loadProducts]);

    const handleAdd = async () => {
        if (!newName) return;
        setAdding(true);
        try {
            await apiAddProduct(tenantId, newName, newCategory, newSku);
            setNewName(''); setNewSku(''); setShowAdd(false);
            await loadProducts();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to add product');
        } finally {
            setAdding(false);
        }
    };

    const filtered = filterCategory === 'all' ? products : products.filter(p => p.category === filterCategory);
    const totalCtes = products.reduce((s, p) => s + p.cte_count, 0);
    const uniqueCategories = [...new Set(products.map(p => p.category))].sort();

    return (
        <div className="min-h-screen bg-background py-8 sm:py-10 px-4 sm:px-6">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Package className="h-6 w-6 text-[var(--re-brand)]" />
                            Product Catalog
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            FTL-covered products in your traceability program
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline" size="sm" className="rounded-xl" onClick={loadProducts} disabled={loading}>
                            <RefreshCw className={`h-3 w-3 mr-1 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                        <Button onClick={() => setShowAdd(!showAdd)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
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
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {[
                                { label: 'Total Products', value: products.length, icon: Package },
                                { label: 'FTL Covered', value: totalFtl, icon: ShieldCheck },
                                { label: 'Categories', value: uniqueCategories.length, icon: Tag },
                                { label: 'Total CTEs', value: totalCtes, icon: Activity },
                            ].map((stat) => (
                                <Card key={stat.label} className="border-[var(--re-border-default)]">
                                    <CardContent className="py-4">
                                        <div className="flex items-center gap-2 mb-1">
                                            <stat.icon className="h-4 w-4 text-[var(--re-brand)]" />
                                            <span className="text-xs text-muted-foreground">{stat.label}</span>
                                        </div>
                                        <div className="text-2xl font-bold">{stat.value}</div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>

                        {/* Add Form */}
                        {showAdd && (
                            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
                                <Card className="border-[var(--re-brand)]">
                                    <CardContent className="py-4">
                                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                                            <Input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Product name" className="rounded-xl" />
                                            <select value={newCategory} onChange={e => setNewCategory(e.target.value)} className="flex h-10 rounded-xl border border-input bg-background px-3 text-sm">
                                                {FTL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                            </select>
                                            <Input value={newSku} onChange={e => setNewSku(e.target.value)} placeholder="SKU (optional)" className="rounded-xl" />
                                            <Button onClick={handleAdd} disabled={adding} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                                                {adding ? <Spinner size="sm" /> : <><Plus className="h-4 w-4 mr-1" /> Add</>}
                                            </Button>
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        )}

                        {/* Category Filter */}
                        <div className="flex gap-2 overflow-x-auto scrollbar-none pb-1 -mx-1 px-1">
                            <button
                                onClick={() => setFilterCategory('all')}
                                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
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
                                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
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
                                        <CardContent className="py-4">
                                            <div className="flex items-center justify-between flex-wrap gap-3">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <Leaf className="h-4 w-4 text-[var(--re-brand)]" />
                                                        <span className="font-medium">{product.name}</span>
                                                        {product.ftl_covered && (
                                                            <Badge className="text-[9px] px-1.5 py-0 bg-emerald-500/10 text-emerald-500">
                                                                <ShieldCheck className="h-2.5 w-2.5 mr-0.5" /> FTL
                                                            </Badge>
                                                        )}
                                                        <Badge variant="outline" className="text-[9px] py-0">{product.category}</Badge>
                                                    </div>
                                                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                                        {product.sku && <span className="flex items-center gap-1"><Barcode className="h-3 w-3" /> {product.sku}</span>}
                                                        <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {product.suppliers.length} supplier{product.suppliers.length !== 1 ? 's' : ''}</span>
                                                        <span className="flex items-center gap-1"><Activity className="h-3 w-3" /> {product.cte_count} CTEs</span>
                                                    </div>
                                                </div>
                                                {product.suppliers.length > 0 && (
                                                    <div className="flex gap-1 flex-wrap">
                                                        {product.suppliers.map(s => (
                                                            <Badge key={s} variant="outline" className="text-[9px] py-0">{s}</Badge>
                                                        ))}
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
