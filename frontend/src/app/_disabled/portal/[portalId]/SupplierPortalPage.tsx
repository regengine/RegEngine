'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    CheckCircle2,
    Send,
    Package,
    Truck,
    MapPin,
    Calendar,
    Hash,
    Shield,
    ArrowRight,
} from 'lucide-react';

type FormState = 'form' | 'submitting' | 'success';

// Simulated portal context (in production, fetched from GET /api/v1/portal/{portal_id})
const PORTAL_CONTEXT = {
    customer_name: 'Metro Distribution Center',
    supplier_name: 'Valley Fresh Farms',
};

export default function SupplierPortalPage() {
    const [formState, setFormState] = useState<FormState>('form');
    const [formData, setFormData] = useState({
        traceability_lot_code: '',
        product_description: '',
        quantity: '',
        unit_of_measure: 'cases',
        ship_date: '',
        ship_from_location: '',
        ship_to_location: PORTAL_CONTEXT.customer_name,
        carrier_name: '',
        po_number: '',
        temperature_celsius: '',
    });

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        setFormData({ ...formData, [e.target.name]: e.target.value });
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        setFormState('submitting');
        setTimeout(() => setFormState('success'), 1500);
    };

    const isFormValid =
        formData.traceability_lot_code &&
        formData.product_description &&
        formData.quantity &&
        formData.ship_date &&
        formData.ship_from_location;

    return (
        <div className="min-h-screen bg-background">
            {/* Header */}
            <div className="border-b border-[var(--re-border-default)] bg-[var(--re-surface-card)]">
                <div className="max-w-2xl mx-auto px-4 py-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="h-10 w-10 rounded-xl bg-[var(--re-brand)] flex items-center justify-center">
                                <Shield className="h-5 w-5 text-white" />
                            </div>
                            <div>
                                <div className="text-lg font-bold">RegEngine</div>
                                <div className="text-xs text-muted-foreground">Supplier Portal</div>
                            </div>
                        </div>
                        <Badge variant="outline" className="rounded-full text-[9px] uppercase tracking-widest">
                            No Account Required
                        </Badge>
                    </div>
                </div>
            </div>

            <div className="max-w-2xl mx-auto px-4 py-8">
                <AnimatePresence mode="wait">
                    {formState === 'success' ? (
                        <motion.div
                            key="success"
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="text-center py-16 space-y-6"
                        >
                            <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                transition={{ type: 'spring', stiffness: 200 }}
                                className="inline-flex h-20 w-20 items-center justify-center rounded-full bg-emerald-500/10 mx-auto"
                            >
                                <CheckCircle2 className="h-10 w-10 text-emerald-500" />
                            </motion.div>
                            <h2 className="text-2xl font-bold">Shipment Data Received</h2>
                            <p className="text-muted-foreground max-w-md mx-auto">
                                Your shipment data has been verified and added to{' '}
                                <strong>{PORTAL_CONTEXT.customer_name}</strong>&apos;s
                                traceability chain. A SHA-256 hash has been generated
                                for this record.
                            </p>
                            <div className="p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] max-w-sm mx-auto">
                                <div className="text-xs text-muted-foreground mb-1">Event Hash</div>
                                <code className="text-xs font-mono text-[var(--re-brand)] break-all">
                                    a3f8c1d2e4b5...7f9a0c3d6e8b
                                </code>
                            </div>
                            <Button
                                onClick={() => {
                                    setFormState('form');
                                    setFormData({
                                        ...formData,
                                        traceability_lot_code: '',
                                        product_description: '',
                                        quantity: '',
                                        ship_date: '',
                                        carrier_name: '',
                                        po_number: '',
                                        temperature_celsius: '',
                                    });
                                }}
                                variant="outline"
                                className="rounded-xl"
                            >
                                Submit Another Shipment
                            </Button>
                        </motion.div>
                    ) : (
                        <motion.div
                            key="form"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                        >
                            {/* Context Banner */}
                            <div className="mb-6 p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                                <div className="flex items-center gap-3">
                                    <Truck className="h-5 w-5 text-[var(--re-brand)]" />
                                    <div>
                                        <div className="text-sm font-medium">
                                            Submitting to: <strong>{PORTAL_CONTEXT.customer_name}</strong>
                                        </div>
                                        <div className="text-xs text-muted-foreground">
                                            As: {PORTAL_CONTEXT.supplier_name}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <Card className="border-[var(--re-border-default)]">
                                <CardHeader>
                                    <CardTitle className="text-xl">Submit Shipment Data</CardTitle>
                                    <CardDescription>
                                        Enter the details of your shipment. This data will be
                                        SHA-256 hashed and added to the FSMA 204 traceability chain.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    <form onSubmit={handleSubmit} className="space-y-5">
                                        {/* Product Info */}
                                        <div className="space-y-3">
                                            <h3 className="text-sm font-bold flex items-center gap-2">
                                                <Package className="h-4 w-4 text-[var(--re-brand)]" />
                                                Product Information
                                            </h3>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Lot Code (TLC) *
                                                    </label>
                                                    <Input
                                                        name="traceability_lot_code"
                                                        value={formData.traceability_lot_code}
                                                        onChange={handleChange}
                                                        placeholder="TOM-0226-F3-001"
                                                        required
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Product Description *
                                                    </label>
                                                    <Input
                                                        name="product_description"
                                                        value={formData.product_description}
                                                        onChange={handleChange}
                                                        placeholder="Roma Tomatoes 12ct"
                                                        required
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Quantity *
                                                    </label>
                                                    <Input
                                                        name="quantity"
                                                        type="number"
                                                        value={formData.quantity}
                                                        onChange={handleChange}
                                                        placeholder="200"
                                                        required
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Unit *
                                                    </label>
                                                    <select
                                                        name="unit_of_measure"
                                                        value={formData.unit_of_measure}
                                                        onChange={handleChange}
                                                        className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                                                    >
                                                        <option value="cases">Cases</option>
                                                        <option value="pallets">Pallets</option>
                                                        <option value="lbs">Pounds (lbs)</option>
                                                        <option value="kg">Kilograms (kg)</option>
                                                        <option value="units">Units</option>
                                                        <option value="bags">Bags</option>
                                                        <option value="boxes">Boxes</option>
                                                    </select>
                                                </div>
                                            </div>
                                        </div>

                                        {/* Shipment Info */}
                                        <div className="space-y-3">
                                            <h3 className="text-sm font-bold flex items-center gap-2">
                                                <MapPin className="h-4 w-4 text-[var(--re-brand)]" />
                                                Shipment Details
                                            </h3>
                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Ship From *
                                                    </label>
                                                    <Input
                                                        name="ship_from_location"
                                                        value={formData.ship_from_location}
                                                        onChange={handleChange}
                                                        placeholder="Your facility name & city"
                                                        required
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Ship To
                                                    </label>
                                                    <Input
                                                        name="ship_to_location"
                                                        value={formData.ship_to_location}
                                                        onChange={handleChange}
                                                        disabled
                                                        className="rounded-xl bg-[var(--re-surface-elevated)]"
                                                    />
                                                </div>
                                            </div>
                                            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Ship Date *
                                                    </label>
                                                    <Input
                                                        name="ship_date"
                                                        type="date"
                                                        value={formData.ship_date}
                                                        onChange={handleChange}
                                                        required
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Carrier
                                                    </label>
                                                    <Input
                                                        name="carrier_name"
                                                        value={formData.carrier_name}
                                                        onChange={handleChange}
                                                        placeholder="Cold Express"
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        PO Number
                                                    </label>
                                                    <Input
                                                        name="po_number"
                                                        value={formData.po_number}
                                                        onChange={handleChange}
                                                        placeholder="PO-2026-4521"
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                            </div>
                                        </div>

                                        {/* Optional: Temperature */}
                                        <div className="space-y-3">
                                            <h3 className="text-sm font-bold flex items-center gap-2">
                                                <Calendar className="h-4 w-4 text-[var(--re-brand)]" />
                                                Optional
                                            </h3>
                                            <div className="grid grid-cols-2 gap-3">
                                                <div>
                                                    <label className="text-xs font-medium text-muted-foreground mb-1 block">
                                                        Temperature at Shipping (°C)
                                                    </label>
                                                    <Input
                                                        name="temperature_celsius"
                                                        type="number"
                                                        step="0.1"
                                                        value={formData.temperature_celsius}
                                                        onChange={handleChange}
                                                        placeholder="3.2"
                                                        className="rounded-xl"
                                                    />
                                                </div>
                                            </div>
                                        </div>

                                        {/* Submit */}
                                        <div className="pt-4 border-t border-[var(--re-border-default)]">
                                            <Button
                                                type="submit"
                                                disabled={!isFormValid || formState === 'submitting'}
                                                className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white h-12 text-base font-bold rounded-xl"
                                            >
                                                {formState === 'submitting' ? (
                                                    <span className="flex items-center gap-2">
                                                        <motion.div
                                                            animate={{ rotate: 360 }}
                                                            transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
                                                        >
                                                            <Hash className="h-4 w-4" />
                                                        </motion.div>
                                                        Hashing & Verifying...
                                                    </span>
                                                ) : (
                                                    <span className="flex items-center gap-2">
                                                        <Send className="h-4 w-4" />
                                                        Submit Shipment
                                                    </span>
                                                )}
                                            </Button>
                                            <div className="mt-3 flex items-center justify-center gap-2 text-xs text-muted-foreground">
                                                <Shield className="h-3 w-3" />
                                                Data is SHA-256 hashed and added to an immutable audit trail
                                            </div>
                                        </div>
                                    </form>
                                </CardContent>
                            </Card>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
