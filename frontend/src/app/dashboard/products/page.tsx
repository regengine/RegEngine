'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    Package,
    Plus,
    ShieldCheck,
    Tag,
    Barcode,
    Building2,
    Users,
    Activity,
    Leaf,
} from 'lucide-react';

const FTL_CATEGORIES = [
    'Leafy Greens', 'Herbs', 'Fresh-Cut Fruits', 'Fresh-Cut Vegetables',
    'Finfish', 'Crustaceans', 'Molluscan Shellfish', 'Smoked Finfish',
    'Soft Cheeses', 'Shell Eggs', 'Nut Butters', 'Ready-to-Eat Deli Salads',
    'Fresh Tomatoes', 'Fresh Peppers', 'Fresh Cucumbers', 'Fresh Sprouts',
    'Tropical Tree Fruits', 'Fresh Melons',
];

interface Product {
    id: string;
    name: string;
    category: string;
    sku: string;
    gtin: string;
    suppliers: string[];
    cte_count: number;
    ftl_covered: boolean;
}

const SAMPLE_PRODUCTS: Product[] = [
    { id: 'prod-001', name: 'Romaine Lettuce', category: 'Leafy Greens', sku: 'ROM-001', gtin: '00612345678901', suppliers: ['Valley Fresh Farms'], cte_count: 47, ftl_covered: true },
    { id: 'prod-002', name: 'Roma Tomatoes', category: 'Fresh Tomatoes', sku: 'TOM-002', gtin: '00612345678902', suppliers: ['Valley Fresh Farms', 'Sunrise Produce'], cte_count: 32, ftl_covered: true },
    { id: 'prod-003', name: 'Atlantic Salmon Fillets', category: 'Finfish', sku: 'SAL-003', gtin: '00612345678903', suppliers: ['Pacific Seafood Inc.'], cte_count: 28, ftl_covered: true },
    { id: 'prod-004', name: 'English Cucumbers', category: 'Fresh Cucumbers', sku: 'CUC-004', gtin: '00612345678904', suppliers: ['Sunrise Produce Co.'], cte_count: 11, ftl_covered: true },
    { id: 'prod-005', name: 'Mixed Salad Greens', category: 'Leafy Greens', sku: 'SAL-005', gtin: '00612345678905', suppliers: ['Green Valley Organics'], cte_count: 5, ftl_covered: true },
];

export default function ProductCatalogPage() {
    const [products, setProducts] = useState(SAMPLE_PRODUCTS);
    const [showAdd, setShowAdd] = useState(false);
    const [newName, setNewName] = useState('');
    const [newCategory, setNewCategory] = useState(FTL_CATEGORIES[0]);
    const [newSku, setNewSku] = useState('');
    const [filterCategory, setFilterCategory] = useState<string>('all');

    const categories = [...new Set(products.map(p => p.category))].sort();
    const filtered = filterCategory === 'all' ? products : products.filter(p => p.category === filterCategory);
    const totalCtes = products.reduce((s, p) => s + p.cte_count, 0);

    const handleAdd = () => {
        if (!newName) return;
        setProducts([...products, {
            id: `prod-new-${Date.now()}`,
            name: newName,
            category: newCategory,
            sku: newSku || `SKU-${Date.now().toString(36).toUpperCase()}`,
            gtin: '',
            suppliers: [],
            cte_count: 0,
            ftl_covered: FTL_CATEGORIES.includes(newCategory),
        }]);
        setNewName('');
        setNewSku('');
        setShowAdd(false);
    };

    return (
        <div className="min-h-screen bg-background py-10 px-4">
            <div className="max-w-5xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-3">
                            <Package className="h-6 w-6 text-[var(--re-brand)]" />
                            Product Catalog
                        </h1>
                        <p className="text-sm text-muted-foreground mt-1">
                            FTL-covered products in your traceability program
                        </p>
                    </div>
                    <Button onClick={() => setShowAdd(!showAdd)} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                        <Plus className="h-4 w-4 mr-1" /> Add Product
                    </Button>
                </div>

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[
                        { label: 'Total Products', value: products.length, icon: Package },
                        { label: 'FTL Covered', value: products.filter(p => p.ftl_covered).length, icon: ShieldCheck },
                        { label: 'Categories', value: categories.length, icon: Tag },
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
                                    <Button onClick={handleAdd} className="bg-[var(--re-brand)] hover:brightness-110 text-white rounded-xl">
                                        <Plus className="h-4 w-4 mr-1" /> Add
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}

                {/* Category Filter */}
                <div className="flex gap-2 flex-wrap">
                    <button
                        onClick={() => setFilterCategory('all')}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${filterCategory === 'all'
                                ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                            }`}
                    >
                        All ({products.length})
                    </button>
                    {categories.map(cat => {
                        const count = products.filter(p => p.category === cat).length;
                        return (
                            <button
                                key={cat}
                                onClick={() => setFilterCategory(filterCategory === cat ? 'all' : cat)}
                                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${filterCategory === cat
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
                                                <span className="flex items-center gap-1"><Barcode className="h-3 w-3" /> {product.sku}</span>
                                                <span className="flex items-center gap-1"><Users className="h-3 w-3" /> {product.suppliers.length} supplier{product.suppliers.length !== 1 ? 's' : ''}</span>
                                                <span className="flex items-center gap-1"><Activity className="h-3 w-3" /> {product.cte_count} CTEs</span>
                                            </div>
                                        </div>
                                        {product.suppliers.length > 0 && (
                                            <div className="flex gap-1">
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
            </div>
        </div>
    );
}
