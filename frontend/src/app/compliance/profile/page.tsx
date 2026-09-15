"use client";

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useEffect, useCallback } from "react";

import { PageContainer } from "@/components/layout/page-container";
import { PageHeader } from "@/components/layout/page-header";
import { getServiceURL } from "@/lib/api-config";
import { useTenant } from "@/lib/tenant-context";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Save, Settings, Leaf, MapPin, Building2, Package, ShoppingCart, AlertCircle, CheckCircle } from "lucide-react";
import Link from "next/link";
import { US_STATES } from "@/lib/constants";

interface ProductProfile {
    tenant_id: string;
    product_categories: string[];
    supply_regions: string[];
    supplier_identifiers: string[];
    fda_product_codes: string[];
    retailer_relationships: string[];
}

// FSMA 204 Food Traceability List categories (Verified against FDA official sources)
const FTL_CATEGORIES = [
    { id: "leafy_greens", label: "Leafy Greens (incl. fresh-cut)", icon: Leaf },
    { id: "tomatoes", label: "Tomatoes", icon: Package },
    { id: "peppers", label: "Peppers", icon: Package },
    { id: "cucumbers", label: "Cucumbers", icon: Package },
    { id: "sprouts", label: "Sprouts", icon: Leaf },
    { id: "melons", label: "Melons", icon: Package },
    { id: "tropical_fruits", label: "Tropical Tree Fruits", icon: Package },
    { id: "fresh_herbs", label: "Fresh Herbs", icon: Leaf },
    { id: "fresh_cut_fruits", label: "Fresh-Cut Fruits", icon: Package },
    { id: "fresh_cut_vegetables", label: "Fresh-Cut Vegetables (non-leafy)", icon: Package },
    { id: "deli_salads", label: "Ready-to-Eat Deli Salads", icon: Package },
    { id: "shell_eggs", label: "Shell Eggs", icon: Package },
    { id: "nut_butters", label: "Nut Butters", icon: Package },
    { id: "finfish", label: "Finfish (including smoked)", icon: Package },
    { id: "crustaceans", label: "Crustaceans", icon: Package },
    { id: "mollusks", label: "Molluscan Shellfish (bivalves)", icon: Package },
    { id: "cheese", label: "Cheeses (other than hard cheeses)", icon: Package },
];

const MAJOR_RETAILERS = [
    "National Retailer A", "Wholesale Club", "Regional Grocery Chain", "Multi-Banner Group", "Southeast Grocer",
    "Organic Market", "Mass Merchant", "Specialty Grocer", "West Coast Chain", "Discount Grocer",
];

const slug = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, "-");

export default function ProductProfilePage() {
    const { tenantId } = useTenant();
    const { isAuthenticated } = useAuth();
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saveMessage, setSaveMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);
    const [profile, setProfile] = useState<ProductProfile>({
        tenant_id: tenantId,
        product_categories: [],
        supply_regions: [],
        supplier_identifiers: [],
        fda_product_codes: [],
        retailer_relationships: [],
    });
    const [supplierInput, setSupplierInput] = useState("");
    const profileEndpoint = `${getServiceURL('admin')}/v1/compliance/profile/${tenantId}`;

    const fetchProfile = useCallback(async () => {
        if (!tenantId) return;
        try {
            const response = await fetchWithCsrf(profileEndpoint, {
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                },
            });
            if (response.ok) {
                const data = await response.json();
                setProfile(data);
                setLoadError(false);
            } else {
                throw new Error('API unavailable');
            }
        } catch (error) {
            // Show error state - no mock fallback for production FSMA
            console.error('Profile API unavailable:', error);
            setLoadError(true);
        } finally {
            setLoading(false);
        }
    }, [profileEndpoint, tenantId]);

    useEffect(() => {
        if (!tenantId || !isAuthenticated) {
            setLoading(false);
            return;
        }
        fetchProfile();
    }, [fetchProfile, isAuthenticated, tenantId]);

    const saveProfile = async () => {
        if (!tenantId) return;
        setSaving(true);
        try {
            const response = await fetchWithCsrf(profileEndpoint, {
                method: "PUT",
                credentials: 'include',
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(profile),
            });

            if (response.ok) {
                setSaveMessage({ type: 'success', text: 'Profile saved! Alerts will now match these criteria.' });
                setTimeout(() => setSaveMessage(null), 4000);
            } else {
                throw new Error("API unavailable");
            }
        } catch (error) {
            // Show error - no mock fallback for production FSMA
            console.error('Profile save failed:', error);
            setSaveMessage({ type: 'error', text: 'Failed to save profile. Backend unavailable.' });
            setTimeout(() => setSaveMessage(null), 4000);
        } finally {
            setSaving(false);
        }
    };

    const toggleCategory = (categoryId: string) => {
        setProfile(prev => ({
            ...prev,
            product_categories: prev.product_categories.includes(categoryId)
                ? prev.product_categories.filter(c => c !== categoryId)
                : [...prev.product_categories, categoryId],
        }));
    };

    const toggleRegion = (state: string) => {
        setProfile(prev => ({
            ...prev,
            supply_regions: prev.supply_regions.includes(state)
                ? prev.supply_regions.filter(s => s !== state)
                : [...prev.supply_regions, state],
        }));
    };

    const toggleRetailer = (retailer: string) => {
        setProfile(prev => ({
            ...prev,
            retailer_relationships: prev.retailer_relationships.includes(retailer)
                ? prev.retailer_relationships.filter(r => r !== retailer)
                : [...prev.retailer_relationships, retailer],
        }));
    };

    const addSupplier = () => {
        if (supplierInput.trim() && !profile.supplier_identifiers.includes(supplierInput.trim())) {
            setProfile(prev => ({
                ...prev,
                supplier_identifiers: [...prev.supplier_identifiers, supplierInput.trim()],
            }));
            setSupplierInput("");
        }
    };

    const removeSupplier = (supplier: string) => {
        setProfile(prev => ({
            ...prev,
            supplier_identifiers: prev.supplier_identifiers.filter(s => s !== supplier),
        }));
    };

    if (loading) {
        return (
            <PageContainer>
                <div className="space-y-4" aria-busy="true">
                    <Skeleton className="h-8 w-64" />
                    <Skeleton className="h-64 w-full" />
                </div>
            </PageContainer>
        );
    }

    return (
        <PageContainer>
            <PageHeader
                title="Product Profile"
                description="Configure what products and regions you handle for alert matching"
                secondaryActions={
                    <Button variant="secondary" asChild>
                        <Link href="/compliance/status">View Status</Link>
                    </Button>
                }
                primaryAction={
                    <Button onClick={saveProfile} disabled={saving}>
                        <Save className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        {saving ? "Saving..." : "Save Profile"}
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Save Message */}
                {saveMessage && (
                    <div
                        role={saveMessage.type === 'success' ? 'status' : 'alert'}
                        className={`flex gap-3 rounded-md border border-l-[3px] border-re-border px-4 py-3 text-ui text-re-text-secondary ${saveMessage.type === 'success'
                            ? 'border-l-re-success bg-re-surface-card'
                            : 'border-l-re-danger bg-re-danger-bg'
                            }`}
                    >
                        {saveMessage.type === 'success' ? (
                            <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                        ) : (
                            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                        )}
                        <span className="min-w-0 flex-1">{saveMessage.text}</span>
                    </div>
                )}

                {/* Load failure */}
                {loadError && (
                    <div
                        role="alert"
                        className="flex gap-3 rounded-md border border-l-[3px] border-re-border border-l-re-danger bg-re-danger-bg px-4 py-3 text-ui text-re-text-secondary"
                    >
                        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                            <p className="font-medium text-re-text-primary">Couldn&apos;t load your product profile</p>
                            <p className="mt-1">The selections below are empty until the profile service responds.</p>
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                                <Button variant="secondary" size="sm" onClick={() => fetchProfile()}>
                                    Retry
                                </Button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Info Banner */}
                <div className="flex gap-3 rounded-md border border-l-[3px] border-re-border border-l-re-info bg-re-surface-card px-4 py-3 text-ui text-re-text-secondary">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-re-info" strokeWidth={1.75} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                        <p className="font-medium text-re-text-primary">
                            Why configure your product profile?
                        </p>
                        <p className="mt-1">
                            RegEngine monitors FDA recalls and alerts. By setting your product categories and supply regions,
                            we can automatically alert you when a recall might affect your business — before it becomes a crisis.
                        </p>
                    </div>
                </div>

                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    {/* Product Categories */}
                    <Card>
                        <CardHeader className="flex-col items-stretch gap-1">
                            <CardTitle className="flex items-center gap-2">
                                <Package className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                Food Traceability List Products
                            </CardTitle>
                            <CardDescription>
                                Select the FSMA 204 FTL categories you handle
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 gap-1">
                                {FTL_CATEGORIES.map(category => {
                                    const checked = profile.product_categories.includes(category.id);
                                    const controlId = `ftl-${category.id}`;
                                    return (
                                        <label
                                            key={category.id}
                                            htmlFor={controlId}
                                            className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-ui transition-colors duration-120 motion-reduce:transition-none ${checked
                                                ? "border-re-border-strong bg-re-surface-inset text-re-text-primary"
                                                : "border-transparent text-re-text-secondary hover:bg-re-surface-inset"
                                                }`}
                                        >
                                            <Checkbox
                                                id={controlId}
                                                checked={checked}
                                                onCheckedChange={() => toggleCategory(category.id)}
                                            />
                                            <category.icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                            <span>{category.label}</span>
                                        </label>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Supply Regions */}
                    <Card>
                        <CardHeader className="flex-col items-stretch gap-1">
                            <CardTitle className="flex items-center gap-2">
                                <MapPin className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                Supply Regions
                            </CardTitle>
                            <CardDescription>
                                Where do your products come from or go to?
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="flex flex-wrap gap-1.5">
                                {US_STATES.map(state => {
                                    const selected = profile.supply_regions.includes(state);
                                    return (
                                        <Button
                                            key={state}
                                            variant="secondary"
                                            size="sm"
                                            aria-pressed={selected}
                                            onClick={() => toggleRegion(state)}
                                            className={selected ? "bg-re-brand-muted text-re-brand" : undefined}
                                        >
                                            {state}
                                        </Button>
                                    );
                                })}
                            </div>
                            <p className="mt-4 text-small text-re-text-tertiary">
                                Selected: {profile.supply_regions.length} states
                            </p>
                        </CardContent>
                    </Card>

                    {/* Suppliers */}
                    <Card>
                        <CardHeader className="flex-col items-stretch gap-1">
                            <CardTitle className="flex items-center gap-2">
                                <Building2 className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                Supplier Names
                            </CardTitle>
                            <CardDescription>
                                Add supplier names to match against recalls
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="mb-4 flex gap-2">
                                <label htmlFor="supplier-name" className="sr-only">
                                    Supplier name
                                </label>
                                <Input
                                    id="supplier-name"
                                    placeholder="Enter supplier name..."
                                    value={supplierInput}
                                    onChange={(e) => setSupplierInput(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && addSupplier()}
                                />
                                <Button variant="secondary" onClick={addSupplier}>Add</Button>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                                {profile.supplier_identifiers.map(supplier => (
                                    <Button
                                        key={supplier}
                                        variant="secondary"
                                        size="sm"
                                        title={`Remove ${supplier}`}
                                        onClick={() => removeSupplier(supplier)}
                                    >
                                        {supplier} ×
                                    </Button>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                    {/* Retailer Relationships */}
                    <Card>
                        <CardHeader className="flex-col items-stretch gap-1">
                            <CardTitle className="flex items-center gap-2">
                                <ShoppingCart className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                Retailer Relationships
                            </CardTitle>
                            <CardDescription>
                                Which retailers do you supply?
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                                {MAJOR_RETAILERS.map(retailer => {
                                    const checked = profile.retailer_relationships.includes(retailer);
                                    const controlId = `retailer-${slug(retailer)}`;
                                    return (
                                        <label
                                            key={retailer}
                                            htmlFor={controlId}
                                            className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-ui transition-colors duration-120 motion-reduce:transition-none ${checked
                                                ? "border-re-border-strong bg-re-surface-inset text-re-text-primary"
                                                : "border-transparent text-re-text-secondary hover:bg-re-surface-inset"
                                                }`}
                                        >
                                            <Checkbox
                                                id={controlId}
                                                checked={checked}
                                                onCheckedChange={() => toggleRetailer(retailer)}
                                            />
                                            <span>{retailer}</span>
                                        </label>
                                    );
                                })}
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Summary */}
                <Card>
                    <CardHeader className="flex-col items-stretch gap-1">
                        <CardTitle>Profile Summary</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                            <div>
                                <p className="text-label text-re-text-muted">Product Categories</p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {profile.product_categories.length}
                                </p>
                            </div>
                            <div>
                                <p className="text-label text-re-text-muted">Supply Regions</p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {profile.supply_regions.length}
                                </p>
                            </div>
                            <div>
                                <p className="text-label text-re-text-muted">Suppliers</p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {profile.supplier_identifiers.length}
                                </p>
                            </div>
                            <div>
                                <p className="text-label text-re-text-muted">Retailers</p>
                                <p className="mt-1 text-title tabular-nums text-re-text-primary">
                                    {profile.retailer_relationships.length}
                                </p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    );
}
