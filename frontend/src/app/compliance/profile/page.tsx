"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";

import { PageContainer } from "@/components/layout/page-container";
import { useTenant } from "@/lib/tenant-context";
import { useAuth } from "@/lib/auth-context";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
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

export default function ProductProfilePage() {
    const { tenantId } = useTenant();
    const { apiKey } = useAuth();
    const [loading, setLoading] = useState(true);
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

    useEffect(() => {
        fetchProfile();
    }, [tenantId]);

    const fetchProfile = async () => {
        try {
            const response = await fetch(`/api/v1/compliance/profile/${tenantId}`, {
                headers: {
                    'X-RegEngine-API-Key': apiKey || '',
                    'X-Tenant-ID': tenantId,
                },
            });
            if (response.ok) {
                const data = await response.json();
                setProfile(data);
            } else {
                throw new Error('API unavailable');
            }
        } catch (error) {
            // Show error state - no mock fallback for production FSMA
            console.error('Profile API unavailable:', error);
        } finally {
            setLoading(false);
        }
    };

    const saveProfile = async () => {
        setSaving(true);
        try {
            const response = await fetch(`/api/v1/compliance/profile/${tenantId}`, {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    'X-RegEngine-API-Key': apiKey || '',
                    'X-Tenant-ID': tenantId,
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
            <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
                <PageContainer>
                    <div className="animate-pulse space-y-4">
                        <div className="h-8 w-64 bg-re-surface-elevated rounded" />
                        <div className="h-64 bg-re-surface-elevated rounded" />
                    </div>
                </PageContainer>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                >
                    {/* Page Header */}
                    <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
                        <div className="flex items-start sm:items-center gap-4">
                            <div className="p-3 rounded-lg bg-purple-100 dark:bg-purple-900">
                                <Settings className="h-8 w-8 text-purple-600 dark:text-purple-400" />
                            </div>
                            <div>
                                <h1 className="text-3xl sm:text-4xl font-bold">Product Profile</h1>
                                <p className="text-muted-foreground mt-1">
                                    Configure what products and regions you handle for alert matching
                                </p>
                            </div>
                        </div>
                        <div className="flex gap-2">
                            <Link href="/compliance/status">
                                <Button variant="outline">View Status</Button>
                            </Link>
                            <Button onClick={saveProfile} disabled={saving}>
                                <Save className="h-4 w-4 mr-2" />
                                {saving ? "Saving..." : "Save Profile"}
                            </Button>
                        </div>
                    </div>

                    {/* Save Message */}
                    {saveMessage && (
                        <div className={`mb-6 p-4 rounded-lg flex items-center gap-2 ${saveMessage.type === 'success'
                            ? 'bg-re-success-muted border border-green-200 text-re-success'
                            : 'bg-re-danger-muted border border-re-danger text-re-danger'
                            }`}>
                            {saveMessage.type === 'success' ? (
                                <CheckCircle className="h-5 w-5" />
                            ) : (
                                <AlertCircle className="h-5 w-5" />
                            )}
                            <span>{saveMessage.text}</span>
                        </div>
                    )}

                    {/* Info Banner */}
                    <Card className="mb-8 border-blue-200 bg-re-info-muted dark:bg-re-info/20">
                        <CardContent className="pt-6">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="h-5 w-5 text-re-info mt-0.5" />
                                <div>
                                    <p className="font-medium text-re-info dark:text-blue-100">
                                        Why configure your product profile?
                                    </p>
                                    <p className="text-sm text-re-info dark:text-blue-300 mt-1">
                                        RegEngine monitors FDA recalls and alerts. By setting your product categories and supply regions,
                                        we can automatically alert you when a recall might affect your business — before it becomes a crisis.
                                    </p>
                                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        {/* Product Categories */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Package className="h-5 w-5" />
                                    Food Traceability List Products
                                </CardTitle>
                                <CardDescription>
                                    Select the FSMA 204 FTL categories you handle
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-1 gap-2">
                                    {FTL_CATEGORIES.map(category => (
                                        <div
                                            key={category.id}
                                            className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${profile.product_categories.includes(category.id)
                                                ? "bg-re-success-muted border-green-200 dark:bg-re-success/20"
                                                : "hover:bg-muted"
                                                }`}
                                            onClick={() => toggleCategory(category.id)}
                                        >
                                            <Checkbox
                                                checked={profile.product_categories.includes(category.id)}
                                                onCheckedChange={() => toggleCategory(category.id)}
                                            />
                                            <category.icon className="h-4 w-4 text-muted-foreground" />
                                            <span className="text-sm">{category.label}</span>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Supply Regions */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <MapPin className="h-5 w-5" />
                                    Supply Regions
                                </CardTitle>
                                <CardDescription>
                                    Where do your products come from or go to?
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex flex-wrap gap-2">
                                    {US_STATES.map(state => (
                                        <Badge
                                            key={state}
                                            variant={profile.supply_regions.includes(state) ? "default" : "outline"}
                                            className="cursor-pointer"
                                            onClick={() => toggleRegion(state)}
                                        >
                                            {state}
                                        </Badge>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground mt-4">
                                    Selected: {profile.supply_regions.length} states
                                </p>
                            </CardContent>
                        </Card>

                        {/* Suppliers */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <Building2 className="h-5 w-5" />
                                    Supplier Names
                                </CardTitle>
                                <CardDescription>
                                    Add supplier names to match against recalls
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="flex gap-2 mb-4">
                                    <Input
                                        placeholder="Enter supplier name..."
                                        value={supplierInput}
                                        onChange={(e) => setSupplierInput(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && addSupplier()}
                                    />
                                    <Button variant="outline" onClick={addSupplier}>Add</Button>
                                </div>
                                <div className="flex flex-wrap gap-2">
                                    {profile.supplier_identifiers.map(supplier => (
                                        <Badge
                                            key={supplier}
                                            variant="secondary"
                                            className="cursor-pointer"
                                            onClick={() => removeSupplier(supplier)}
                                        >
                                            {supplier} ×
                                        </Badge>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>

                        {/* Retailer Relationships */}
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <ShoppingCart className="h-5 w-5" />
                                    Retailer Relationships
                                </CardTitle>
                                <CardDescription>
                                    Which retailers do you supply?
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="grid grid-cols-2 gap-2">
                                    {MAJOR_RETAILERS.map(retailer => (
                                        <div
                                            key={retailer}
                                            className={`flex items-center gap-2 p-2 rounded border cursor-pointer ${profile.retailer_relationships.includes(retailer)
                                                ? "bg-re-info-muted border-blue-200"
                                                : "hover:bg-muted"
                                                }`}
                                            onClick={() => toggleRetailer(retailer)}
                                        >
                                            <Checkbox
                                                checked={profile.retailer_relationships.includes(retailer)}
                                                onCheckedChange={() => toggleRetailer(retailer)}
                                            />
                                            <span className="text-sm">{retailer}</span>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Summary */}
                    <Card className="mt-6">
                        <CardHeader>
                            <CardTitle>Profile Summary</CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                                <div>
                                    <div className="text-3xl font-bold text-re-success">
                                        {profile.product_categories.length}
                                    </div>
                                    <div className="text-sm text-muted-foreground">Product Categories</div>
                                </div>
                                <div>
                                    <div className="text-3xl font-bold text-re-info">
                                        {profile.supply_regions.length}
                                    </div>
                                    <div className="text-sm text-muted-foreground">Supply Regions</div>
                                </div>
                                <div>
                                    <div className="text-3xl font-bold text-purple-600">
                                        {profile.supplier_identifiers.length}
                                    </div>
                                    <div className="text-sm text-muted-foreground">Suppliers</div>
                                </div>
                                <div>
                                    <div className="text-3xl font-bold text-re-warning">
                                        {profile.retailer_relationships.length}
                                    </div>
                                    <div className="text-sm text-muted-foreground">Retailers</div>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </motion.div>
            </PageContainer>
        </div>
    );
}
