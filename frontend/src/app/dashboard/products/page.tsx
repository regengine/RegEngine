'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { ErrorState } from '@/components/ui/error-state';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge } from '@/components/ui/status-badge';
import {
    Package,
    Plus,
    Barcode,
    Users,
    Activity,
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
        throw new Error("Couldn't load your product catalog.");
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
    const totalFtl = productsData?.totalFtl ?? 0;
    const error = productsError;

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
        if (!newName || error || !productsData) return;
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
        <PageContainer>
            <PageHeader
                title="Product Catalog"
                description="FTL-covered products in your traceability program"
                secondaryActions={
                    <Button
                        variant="outline"
                        size="icon"
                        aria-label="Refresh product catalog"
                        onClick={() => loadProducts()}
                        disabled={loading}
                    >
                        <RefreshCw
                            className={loading ? 'animate-spin motion-reduce:animate-none' : undefined}
                            strokeWidth={1.75}
                            aria-hidden="true"
                        />
                    </Button>
                }
                primaryAction={
                    <Button
                        onClick={() => setShowAdd(!showAdd)}
                        disabled={!productsData || !!error || loading}
                        aria-expanded={showAdd}
                        leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                    >
                        Add Product
                    </Button>
                }
            />

            <div className="space-y-6">
                {!isLoggedIn && (
                    <Callout tone="warning">
                        Sign in to view your product catalog.
                    </Callout>
                )}

                {loading && products.length === 0 && (
                    <div className="space-y-3" aria-busy="true">
                        {[0, 1, 2, 3].map((row) => (
                            <Skeleton key={row} className="h-20 w-full" />
                        ))}
                    </div>
                )}

                {error && <ErrorState message="We could not load this page." onRetry={() => loadProducts()} />}

                {isLoggedIn && !error && products.length > 0 && (
                    <>
                        {/* Stats */}
                        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                            <StatTile label="Total Products" value={products.length} />
                            <StatTile label="FTL Covered" value={totalFtl} />
                            <StatTile label="Categories" value={uniqueCategories.length} />
                            <StatTile label="Total CTEs" value={totalCtes} />
                        </div>

                        {/* Add Form */}
                        {showAdd && (
                            <Card>
                                <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
                                    <div className="min-w-0">
                                        <label htmlFor="new-product-name" className="sr-only">Product name</label>
                                        <Input id="new-product-name" size="lg" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Product name" />
                                    </div>
                                    <div className="min-w-0">
                                        <label htmlFor="new-product-category" className="sr-only">Category</label>
                                        <select id="new-product-category" value={newCategory} onChange={e => setNewCategory(e.target.value)} className={`${fieldControlClasses} h-11`}>
                                            {FTL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                        </select>
                                    </div>
                                    <div className="min-w-0">
                                        <label htmlFor="new-product-sku" className="sr-only">SKU (optional)</label>
                                        <Input id="new-product-sku" size="lg" value={newSku} onChange={e => setNewSku(e.target.value)} placeholder="SKU (optional)" />
                                    </div>
                                    <Button
                                        size="lg"
                                        onClick={handleAdd}
                                        disabled={adding}
                                        loading={adding}
                                        leadingIcon={<Plus strokeWidth={1.75} aria-hidden="true" />}
                                    >
                                        Add
                                    </Button>
                                    {addProductMutation.isError && (
                                        <p className="flex items-center gap-1.5 text-small text-re-danger sm:col-span-2 md:col-span-4">
                                            <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            {addProductMutation.error?.message || "Couldn't add the product — retry."}
                                        </p>
                                    )}
                                </CardContent>
                            </Card>
                        )}

                        {/* Category Filter */}
                        <div className="-mx-1 flex gap-2 overflow-x-auto scrollbar-none no-scrollbar px-1 pb-1">
                            <Button
                                variant={filterCategory === 'all' ? 'secondary' : 'ghost'}
                                size="sm"
                                aria-pressed={filterCategory === 'all'}
                                className="shrink-0"
                                onClick={() => setFilterCategory('all')}
                            >
                                All ({products.length})
                            </Button>
                            {uniqueCategories.map(cat => {
                                const count = products.filter(p => p.category === cat).length;
                                return (
                                    <Button
                                        key={cat}
                                        variant={filterCategory === cat ? 'secondary' : 'ghost'}
                                        size="sm"
                                        aria-pressed={filterCategory === cat}
                                        className="shrink-0"
                                        onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
                                    >
                                        {cat} ({count})
                                    </Button>
                                );
                            })}
                        </div>

                        {selectedProduct && (
                            <Card role="region" aria-label="Product detail">
                                <CardContent className="space-y-4">
                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                        <div className="min-w-0">
                                            <div className="flex flex-wrap items-center gap-2">
                                                <h2 className="text-subheading text-re-text-primary">{selectedProduct.name}</h2>
                                                {selectedProduct.ftl_covered && (
                                                    <StatusBadge state="compliant" label="FTL" size="sm" />
                                                )}
                                            </div>
                                            <div className="mt-1 text-small text-re-text-tertiary">
                                                {selectedProduct.category || 'Uncategorized'} · {selectedProduct.sku || 'No SKU'}
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap items-center gap-2">
                                            <Button variant="outline" size="sm" onClick={() => handleEditProduct(selectedProduct)} leadingIcon={<Edit3 strokeWidth={1.75} aria-hidden="true" />}>
                                                Edit Product
                                            </Button>
                                            <Button variant="outline" size="sm" onClick={() => handleDeleteProduct(selectedProduct)} disabled={deletingProduct} leadingIcon={<Trash2 strokeWidth={1.75} aria-hidden="true" />}>
                                                Delete Product
                                            </Button>
                                            <Button variant="outline" size="sm" onClick={() => setSelectedProductId(null)} leadingIcon={<X strokeWidth={1.75} aria-hidden="true" />}>
                                                Close
                                            </Button>
                                        </div>
                                    </div>

                                    {editingProductId === selectedProduct.id ? (
                                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-4">
                                            <Field label="Product Name" htmlFor="edit-product-name">
                                                <Input id="edit-product-name" size="lg" value={editName} onChange={e => setEditName(e.target.value)} />
                                            </Field>
                                            <Field label="Category" htmlFor="edit-product-category">
                                                <select id="edit-product-category" value={editCategory} onChange={e => setEditCategory(e.target.value)} className={`${fieldControlClasses} h-11`}>
                                                    {FTL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                                                </select>
                                            </Field>
                                            <Field label="SKU" htmlFor="edit-product-sku">
                                                <Input id="edit-product-sku" size="lg" value={editSku} onChange={e => setEditSku(e.target.value)} />
                                            </Field>
                                            <div className="flex items-end gap-2">
                                                <Button
                                                    size="lg"
                                                    className="flex-1"
                                                    onClick={() => handleSaveProduct(selectedProduct)}
                                                    disabled={savingProduct || !editName.trim()}
                                                    loading={savingProduct}
                                                    leadingIcon={<Save strokeWidth={1.75} aria-hidden="true" />}
                                                >
                                                    Save
                                                </Button>
                                                <Button variant="outline" size="lg" aria-label="Cancel edit" onClick={() => setEditingProductId(null)}>
                                                    <X className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                </Button>
                                            </div>
                                            {updateProductMutation.isError && (
                                                <p className="flex items-center gap-1.5 text-small text-re-danger sm:col-span-2 md:col-span-4">
                                                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    {updateProductMutation.error?.message || "Couldn't save your changes — retry."}
                                                </p>
                                            )}
                                        </div>
                                    ) : (
                                        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
                                            <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                                <dt className="text-label text-re-text-muted">Suppliers</dt>
                                                <dd className="mt-1 text-ui font-medium tabular-nums text-re-text-primary">{selectedProduct.suppliers.length}</dd>
                                            </div>
                                            <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                                <dt className="text-label text-re-text-muted">Facilities</dt>
                                                <dd className="mt-1 text-ui font-medium tabular-nums text-re-text-primary">{selectedProduct.facilities.length}</dd>
                                            </div>
                                            <div className="rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                                <dt className="text-label text-re-text-muted">CTEs</dt>
                                                <dd className="mt-1 text-ui font-medium tabular-nums text-re-text-primary">{selectedProduct.cte_count}</dd>
                                            </div>
                                            <div className="min-w-0 rounded-md border border-re-border-subtle bg-re-surface-inset p-3">
                                                <dt className="text-label text-re-text-muted">GTIN</dt>
                                                <dd className="mt-1 truncate font-mono text-[0.8125rem] text-re-text-primary">{selectedProduct.gtin || 'Not set'}</dd>
                                            </div>
                                        </dl>
                                    )}
                                </CardContent>
                            </Card>
                        )}

                        {deleteProductMutation.isError && (
                            <p className="flex items-center gap-1.5 text-small text-re-danger">
                                <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                {deleteProductMutation.error?.message || "Couldn't delete the product — retry."}
                            </p>
                        )}

                        {/* Product List — hairline ledger rows. Each row keeps its
                            role="region" + aria-label, which the authenticated e2e
                            journey scopes its Open/Edit/Delete clicks to. */}
                        <Card className="overflow-hidden">
                            <ul className="divide-y divide-re-border-subtle">
                                {filtered.map((product) => (
                                    <li key={product.id}>
                                        <div
                                            role="region"
                                            aria-label={`Product ${product.name}`}
                                            className="flex flex-col gap-3 px-4 py-4 transition-colors duration-120 hover:bg-re-surface-inset/60 motion-reduce:transition-none sm:flex-row sm:items-center sm:justify-between sm:px-5"
                                        >
                                            <div className="min-w-0 flex-1">
                                                <div className="mb-1 flex flex-wrap items-center gap-2">
                                                    <span className="text-ui font-medium text-re-text-primary">{product.name}</span>
                                                    {product.ftl_covered && (
                                                        <StatusBadge state="compliant" label="FTL" size="sm" />
                                                    )}
                                                    <Badge size="sm" className="hidden sm:inline-flex">{product.category}</Badge>
                                                </div>
                                                <div className="flex flex-wrap items-center gap-3 text-small text-re-text-tertiary sm:gap-4">
                                                    {product.sku && (
                                                        <span className="flex items-center gap-1">
                                                            <Barcode className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                            <span className="font-mono">{product.sku}</span>
                                                        </span>
                                                    )}
                                                    <span className="flex items-center gap-1">
                                                        <Users className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        {product.suppliers.length} supplier{product.suppliers.length !== 1 ? 's' : ''}
                                                    </span>
                                                    <span className="flex items-center gap-1">
                                                        <Activity className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        {product.cte_count} CTEs
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="flex flex-col gap-2 sm:items-end">
                                                {product.suppliers.length > 0 && (
                                                    <div className="flex flex-wrap justify-start gap-1 sm:justify-end">
                                                        {product.suppliers.slice(0, 3).map(s => (
                                                            <Badge key={s} size="sm">{s}</Badge>
                                                        ))}
                                                        {product.suppliers.length > 3 && (
                                                            <Badge size="sm">+{product.suppliers.length - 3}</Badge>
                                                        )}
                                                    </div>
                                                )}
                                                <div className="flex flex-wrap gap-1.5">
                                                    <Button variant="outline" size="sm" onClick={() => handleOpenProduct(product)} leadingIcon={<Eye strokeWidth={1.75} aria-hidden="true" />}>
                                                        Open
                                                    </Button>
                                                    <Button variant="outline" size="sm" onClick={() => handleEditProduct(product)} leadingIcon={<Edit3 strokeWidth={1.75} aria-hidden="true" />}>
                                                        Edit
                                                    </Button>
                                                    <Button variant="outline" size="sm" onClick={() => handleDeleteProduct(product)} disabled={deletingProduct} leadingIcon={<Trash2 strokeWidth={1.75} aria-hidden="true" />}>
                                                        Delete
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </li>
                                ))}
                            </ul>
                        </Card>
                    </>
                )}

                {isLoggedIn && !loading && products.length === 0 && !error && (
                    <EmptyState
                        icon={Package}
                        title="No products yet"
                        description="Add your first FTL product to start tracking"
                    />
                )}
            </div>
        </PageContainer>
    );
}
