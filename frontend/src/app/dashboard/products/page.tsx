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
    Eye,
    Edit3,
    Save,
    Trash2,
    X,
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

async function apiFetchProducts(tenantId: string): Promise<ProductCatalogResponse> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}`, {
        credentials: 'include',
        signal: AbortSignal.timeout(8000),
        headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
        console.error(`Products fetch failed: ${res.status} ${res.statusText}`);
        throw new Error("Couldn't load your product catalog. Check your connection and retry.");
    }
    return res.json();
}

async function apiAddProduct(tenantId: string, name: string, category: string, sku: string): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}`, {
        method: 'POST',
        credentials: 'include',
        signal: AbortSignal.timeout(12000),
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, category, sku: sku || undefined }),
    });
    if (!res.ok) {
        console.error(`Product add failed: ${res.status} ${res.statusText}`);
        throw new Error("Couldn't add the product — retry.");
    }
}

async function apiUpdateProduct(tenantId: string, product: Product, updates: { name: string; category: string; sku: string }): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}/${product.id}`, {
        method: 'PUT',
        credentials: 'include',
        signal: AbortSignal.timeout(12000),
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: updates.name,
            category: updates.category,
            sku: updates.sku || '',
            gtin: product.gtin || '',
            description: product.description || '',
            suppliers: product.suppliers || [],
            facilities: product.facilities || [],
        }),
    });
    if (!res.ok) {
        console.error(`Product update failed: ${res.status} ${res.statusText}`);
        throw new Error("Couldn't save your changes — retry.");
    }
}

async function apiDeleteProduct(tenantId: string, productId: string): Promise<void> {
    const { getServiceURL } = await import('@/lib/api-config');
    const base = getServiceURL('ingestion');
    const res = await fetchWithCsrf(`${base}/api/v1/products/${tenantId}/${productId}`, {
        method: 'DELETE',
        credentials: 'include',
        signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) {
        console.error(`Product delete failed: ${res.status} ${res.statusText}`);
        throw new Error("Couldn't delete the product — retry.");
    }
}

export default function ProductCatalogPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId, isSystemTenant } = useTenant();

    const isLoggedIn = isAuthenticated;
    const effectiveTenantId = isSystemTenant ? null : tenantId;

    const productsQueryClient = useQueryClient();

    const [showAdd, setShowAdd] = useState(false);
    const [newName, setNewName] = useState('');
    const [newCategory, setNewCategory] = useState(FTL_CATEGORIES[0]);
    const [newSku, setNewSku] = useState('');
    const [filterCategory, setFilterCategory] = useState<string>('all');
    const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
    const [editingProductId, setEditingProductId] = useState<string | null>(null);
    const [editName, setEditName] = useState('');
    const [editCategory, setEditCategory] = useState(FTL_CATEGORIES[0]);
    const [editSku, setEditSku] = useState('');

    const { data: productsData, isLoading: loading, error: productsError, refetch: loadProducts } = useQuery({
        queryKey: ['products', effectiveTenantId],
        queryFn: async () => {
            const data = await apiFetchProducts(effectiveTenantId!);
            const fetchedProducts = data.products || [];
            return { products: fetchedProducts, categories: data.categories || [], totalFtl: data.ftl_covered || 0 };
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
        mutationFn: () => apiAddProduct(effectiveTenantId!, newName, newCategory, newSku),
        onSuccess: () => {
            setNewName(''); setNewSku(''); setShowAdd(false);
            productsQueryClient.invalidateQueries({ queryKey: ['products', effectiveTenantId] });
        },
    });

    const adding = addProductMutation.isPending;

    const updateProductMutation = useMutation({
        mutationFn: (product: Product) => apiUpdateProduct(effectiveTenantId!, product, {
            name: editName,
            category: editCategory,
            sku: editSku,
        }),
        onSuccess: () => {
            setEditingProductId(null);
            productsQueryClient.invalidateQueries({ queryKey: ['products', effectiveTenantId] });
        },
    });

    const deleteProductMutation = useMutation({
        mutationFn: (productId: string) => apiDeleteProduct(effectiveTenantId!, productId),
        onSuccess: () => {
            setSelectedProductId(null);
            setEditingProductId(null);
            productsQueryClient.invalidateQueries({ queryKey: ['products', effectiveTenantId] });
        },
    });

    const selectedProduct = products.find(product => product.id === selectedProductId) ?? null;
    const savingProduct = updateProductMutation.isPending;
    const deletingProduct = deleteProductMutation.isPending;

    const handleAdd = () => {
        if (!newName) return;
        addProductMutation.mutate();
    };

    const handleOpenProduct = (product: Product) => {
        setSelectedProductId(product.id);
        setEditingProductId(null);
    };

    const handleEditProduct = (product: Product) => {
        setSelectedProductId(product.id);
        setEditingProductId(product.id);
        setEditName(product.name);
        setEditCategory(product.category || FTL_CATEGORIES[0]);
        setEditSku(product.sku || '');
    };

    const handleSaveProduct = (product: Product) => {
        if (!editName.trim()) return;
        updateProductMutation.mutate(product);
    };

    const handleDeleteProduct = (product: Product) => {
        if (!window.confirm(`Delete ${product.name}?`)) return;
        deleteProductMutation.mutate(product.id);
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
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-3 text-orange-600 dark:text-orange-400">
                                    <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                    <p className="text-sm">{error}</p>
                                </div>
                                <Button variant="outline" size="sm" className="rounded-xl text-xs flex-shrink-0 min-h-[44px]" onClick={() => loadProducts()} disabled={loading}>
                                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Retry
                                </Button>
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
                                        {addProductMutation.isError && (
                                            <p className="mt-2 text-xs text-re-danger flex items-center gap-1.5">
                                                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                                                {addProductMutation.error?.message || "Couldn't add the product — retry."}
                                            </p>
                                        )}
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

                        {selectedProduct && (
                            <Card role="region" aria-label="Product detail" className="border-[var(--re-brand)]">
                                <CardContent className="py-4 space-y-4">
                                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                                        <div className="min-w-0">
                                            <div className="flex items-center gap-2 flex-wrap">
                                                <Leaf className="h-4 w-4 text-[var(--re-brand)] flex-shrink-0" />
                                                <h2 className="text-base sm:text-lg font-semibold">{selectedProduct.name}</h2>
                                                {selectedProduct.ftl_covered && (
                                                    <Badge className="text-[10px] bg-re-brand-muted text-re-brand">
                                                        <ShieldCheck className="h-3 w-3 mr-0.5" /> FTL
                                                    </Badge>
                                                )}
                                            </div>
                                            <div className="mt-1 text-xs text-muted-foreground">
                                                {selectedProduct.category || 'Uncategorized'} · {selectedProduct.sku || 'No SKU'}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <Button variant="outline" size="sm" className="rounded-xl min-h-[44px]" onClick={() => handleEditProduct(selectedProduct)}>
                                                <Edit3 className="h-3.5 w-3.5 mr-1" /> Edit Product
                                            </Button>
                                            <Button variant="outline" size="sm" className="rounded-xl min-h-[44px]" onClick={() => handleDeleteProduct(selectedProduct)} disabled={deletingProduct}>
                                                <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete Product
                                            </Button>
                                            <Button variant="outline" size="sm" className="rounded-xl min-h-[44px]" onClick={() => setSelectedProductId(null)}>
                                                <X className="h-3.5 w-3.5 mr-1" /> Close
                                            </Button>
                                        </div>
                                    </div>

                                    {editingProductId === selectedProduct.id ? (
                                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
                                            <div>
                                                <label htmlFor="edit-product-name" className="text-xs font-medium text-muted-foreground mb-1 block">Product Name</label>
                                                <Input id="edit-product-name" value={editName} onChange={e => setEditName(e.target.value)} className="rounded-xl min-h-[44px]" />
                                            </div>
                                            <div>
                                                <label htmlFor="edit-product-category" className="text-xs font-medium text-muted-foreground mb-1 block">Category</label>
                                                <select id="edit-product-category" value={editCategory} onChange={e => setEditCategory(e.target.value)} className="flex h-10 min-h-[44px] w-full rounded-xl border border-input bg-background px-3 text-sm">
                                                    {FTL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                                </select>
                                            </div>
                                            <div>
                                                <label htmlFor="edit-product-sku" className="text-xs font-medium text-muted-foreground mb-1 block">SKU</label>
                                                <Input id="edit-product-sku" value={editSku} onChange={e => setEditSku(e.target.value)} className="rounded-xl min-h-[44px]" />
                                            </div>
                                            <div className="flex items-end gap-2">
                                                <Button onClick={() => handleSaveProduct(selectedProduct)} disabled={savingProduct || !editName.trim()} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl min-h-[44px] flex-1">
                                                    {savingProduct ? <Spinner size="sm" /> : <><Save className="h-4 w-4 mr-1" /> Save</>}
                                                </Button>
                                                <Button variant="outline" onClick={() => setEditingProductId(null)} className="rounded-xl min-h-[44px]">
                                                    <X className="h-4 w-4" />
                                                </Button>
                                            </div>
                                            {updateProductMutation.isError && (
                                                <p className="sm:col-span-2 md:col-span-4 text-xs text-re-danger flex items-center gap-1.5">
                                                    <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                                                    {updateProductMutation.error?.message || "Couldn't save your changes — retry."}
                                                </p>
                                            )}
                                        </div>
                                    ) : (
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                                            <div className="rounded-xl border border-[var(--re-border-default)] p-3">
                                                <div className="text-muted-foreground">Suppliers</div>
                                                <div className="font-medium">{selectedProduct.suppliers.length}</div>
                                            </div>
                                            <div className="rounded-xl border border-[var(--re-border-default)] p-3">
                                                <div className="text-muted-foreground">Facilities</div>
                                                <div className="font-medium">{selectedProduct.facilities.length}</div>
                                            </div>
                                            <div className="rounded-xl border border-[var(--re-border-default)] p-3">
                                                <div className="text-muted-foreground">CTEs</div>
                                                <div className="font-medium">{selectedProduct.cte_count}</div>
                                            </div>
                                            <div className="rounded-xl border border-[var(--re-border-default)] p-3">
                                                <div className="text-muted-foreground">GTIN</div>
                                                <div className="font-medium truncate">{selectedProduct.gtin || 'Not set'}</div>
                                            </div>
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        )}

                        {deleteProductMutation.isError && (
                            <p className="text-xs text-re-danger flex items-center gap-1.5">
                                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                                {deleteProductMutation.error?.message || "Couldn't delete the product — retry."}
                            </p>
                        )}

                        {/* Product List */}
                        <div className="space-y-3">
                            {filtered.map((product, i) => (
                                <motion.div key={product.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}>
                                    <Card role="region" aria-label={`Product ${product.name}`} className="border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all">
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
                                                <div className="flex flex-col sm:items-end gap-2">
                                                    {product.suppliers.length > 0 && (
                                                        <div className="flex gap-1 flex-wrap justify-start sm:justify-end">
                                                            {product.suppliers.slice(0, 3).map(s => (
                                                                <Badge key={s} variant="outline" className="text-[9px] py-0">{s}</Badge>
                                                            ))}
                                                            {product.suppliers.length > 3 && (
                                                                <Badge variant="outline" className="text-[9px] py-0">+{product.suppliers.length - 3}</Badge>
                                                            )}
                                                        </div>
                                                    )}
                                                    <div className="flex gap-1.5 flex-wrap">
                                                        <Button variant="outline" size="sm" className="rounded-xl min-h-[40px]" onClick={() => handleOpenProduct(product)}>
                                                            <Eye className="h-3.5 w-3.5 mr-1" /> Open
                                                        </Button>
                                                        <Button variant="outline" size="sm" className="rounded-xl min-h-[40px]" onClick={() => handleEditProduct(product)}>
                                                            <Edit3 className="h-3.5 w-3.5 mr-1" /> Edit
                                                        </Button>
                                                        <Button variant="outline" size="sm" className="rounded-xl min-h-[40px]" onClick={() => handleDeleteProduct(product)} disabled={deletingProduct}>
                                                            <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
                                                        </Button>
                                                    </div>
                                                </div>
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
