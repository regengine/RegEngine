'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FreeToolPageShell } from '@/components/layout/FreeToolPageShell';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    FileText,
    Download,
    CheckCircle2,
    Plus,
    X,
    Building2,
    Package,
    Printer,
} from 'lucide-react';

type Phase = 'form' | 'generating' | 'preview';

export function SOPGeneratorClient() {
    const [phase, setPhase] = useState<Phase>('form');
    const [formData, setFormData] = useState({
        company_name: '',
        company_type: 'manufacturer',
        primary_contact: '',
        contact_title: '',
        has_iot: false,
        has_erp: false,
    });
    const [products, setProducts] = useState<string[]>(['']);
    const [facilities, setFacilities] = useState<string[]>(['']);
    const [retailers, setRetailers] = useState<string[]>([]);
    const [generatedDoc, setGeneratedDoc] = useState('');

    const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
        const target = e.target;
        const value = target.type === 'checkbox' ? (target as HTMLInputElement).checked : target.value;
        setFormData({ ...formData, [target.name]: value });
    };

    const handleGenerate = () => {
        setPhase('generating');
        // Simulate generation delay
        setTimeout(() => {
            const doc = generatePreview();
            setGeneratedDoc(doc);
            setPhase('preview');
        }, 2000);
    };

    const generatePreview = () => {
        const prodList = products.filter(Boolean).join(', ');
        const facList = facilities.filter(Boolean).map(f => `   - ${f}`).join('\n');
        const now = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

        return `# FSMA 204 Traceability Plan

**Company**: ${formData.company_name}
**Type**: ${formData.company_type.charAt(0).toUpperCase() + formData.company_type.slice(1)}
**Generated**: ${now}
**Contact**: ${formData.primary_contact}${formData.contact_title ? ` — ${formData.contact_title}` : ''}

## Products Covered
${prodList}

## Facilities
${facList}

## CTE Procedures
${formData.company_type === 'grower' || formData.company_type === 'manufacturer' ? '✅ Harvesting (§1.1325a)\n✅ Cooling (§1.1325b)\n' : ''}✅ Shipping (§1.1340)
✅ Receiving (§1.1345)
${formData.company_type === 'manufacturer' ? '✅ Transformation (§1.1350)\n' : ''}
## Operations
${formData.has_iot ? '✅ IoT Temperature Monitoring (Sensitech)' : '⬜ No IoT monitoring'}
${formData.has_erp ? '✅ ERP/WMS Integration via Webhook API' : '⬜ Manual data entry / CSV upload'}

${retailers.length > 0 ? `## Retailer Requirements\n${retailers.map(r => `- ${r}`).join('\n')}` : ''}

---
*Full document available via POST /api/v1/sop/generate*`;
    };

    const validProducts = products.filter(Boolean);
    const validFacilities = facilities.filter(Boolean);
    const isValid = formData.company_name && formData.primary_contact && validProducts.length > 0 && validFacilities.length > 0;

    return (
        <FreeToolPageShell
            title="SOP Generator"
            subtitle="Auto-generate a complete FSMA 204 Traceability Plan and Standard Operating Procedures for your organization."
            relatedToolIds={['ftl-checker', 'cte-mapper', 'drill-simulator']}
        >
            <AnimatePresence mode="wait">
                {phase === 'form' && (
                    <motion.div key="form" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-6">
                        {/* Company Info */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Building2 className="h-4 w-4 text-[var(--re-brand)]" />
                                    Company Information
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Company Name *</label>
                                        <Input name="company_name" value={formData.company_name} onChange={handleChange} placeholder="Valley Fresh Farms" className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Company Type *</label>
                                        <select name="company_type" value={formData.company_type} onChange={handleChange} className="flex h-10 w-full rounded-xl border border-input bg-background px-3 text-sm">
                                            <option value="grower">Grower / Farm</option>
                                            <option value="manufacturer">Manufacturer / Processor</option>
                                            <option value="distributor">Distributor</option>
                                            <option value="retailer">Retailer</option>
                                            <option value="importer">Importer</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Compliance Contact *</label>
                                        <Input name="primary_contact" value={formData.primary_contact} onChange={handleChange} placeholder="Jane Smith" className="rounded-xl" />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-muted-foreground mb-1 block">Title</label>
                                        <Input name="contact_title" value={formData.contact_title} onChange={handleChange} placeholder="VP Food Safety" className="rounded-xl" />
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        {/* Products */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Package className="h-4 w-4 text-[var(--re-brand)]" />
                                    FTL Products *
                                </CardTitle>
                                <CardDescription>Products on the FDA Food Traceability List</CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {products.map((p, i) => (
                                    <div key={i} className="flex gap-2">
                                        <Input
                                            value={p}
                                            onChange={(e) => {
                                                const updated = [...products];
                                                updated[i] = e.target.value;
                                                setProducts(updated);
                                            }}
                                            placeholder="e.g. Roma Tomatoes, Romaine Lettuce"
                                            className="rounded-xl"
                                        />
                                        {products.length > 1 && (
                                            <Button variant="ghost" size="sm" onClick={() => setProducts(products.filter((_, idx) => idx !== i))}>
                                                <X className="h-4 w-4" />
                                            </Button>
                                        )}
                                    </div>
                                ))}
                                <Button variant="outline" size="sm" onClick={() => setProducts([...products, ''])} className="rounded-xl">
                                    <Plus className="h-3 w-3 mr-1" /> Add Product
                                </Button>
                            </CardContent>
                        </Card>

                        {/* Facilities */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Facilities *</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-2">
                                {facilities.map((f, i) => (
                                    <div key={i} className="flex gap-2">
                                        <Input
                                            value={f}
                                            onChange={(e) => {
                                                const updated = [...facilities];
                                                updated[i] = e.target.value;
                                                setFacilities(updated);
                                            }}
                                            placeholder="e.g. Valley Fresh Farms, Salinas CA"
                                            className="rounded-xl"
                                        />
                                        {facilities.length > 1 && (
                                            <Button variant="ghost" size="sm" onClick={() => setFacilities(facilities.filter((_, idx) => idx !== i))}>
                                                <X className="h-4 w-4" />
                                            </Button>
                                        )}
                                    </div>
                                ))}
                                <Button variant="outline" size="sm" onClick={() => setFacilities([...facilities, ''])} className="rounded-xl">
                                    <Plus className="h-3 w-3 mr-1" /> Add Facility
                                </Button>
                            </CardContent>
                        </Card>

                        {/* Options */}
                        <Card className="border-[var(--re-border-default)]">
                            <CardHeader>
                                <CardTitle className="text-base">Options</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3">
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input type="checkbox" name="has_iot" checked={formData.has_iot} onChange={handleChange} className="rounded" />
                                    <span className="text-sm">IoT temperature monitoring (Sensitech, Tive, etc.)</span>
                                </label>
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input type="checkbox" name="has_erp" checked={formData.has_erp} onChange={handleChange} className="rounded" />
                                    <span className="text-sm">ERP/WMS integration (SAP, NetSuite, etc.)</span>
                                </label>
                                <div>
                                    <label className="text-xs font-medium text-muted-foreground mb-2 block">Target Retailers</label>
                                    <div className="flex flex-wrap gap-2">
                                        {['Walmart', 'Kroger', 'Costco', 'Target', 'Albertsons'].map((r) => (
                                            <button
                                                key={r}
                                                onClick={() => setRetailers(retailers.includes(r) ? retailers.filter(x => x !== r) : [...retailers, r])}
                                                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${retailers.includes(r)
                                                        ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                                        : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                                    }`}
                                            >
                                                {r}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </CardContent>
                        </Card>

                        <Button
                            onClick={handleGenerate}
                            disabled={!isValid}
                            className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white h-12 rounded-xl font-bold text-base"
                        >
                            <FileText className="mr-2 h-5 w-5" />
                            Generate Traceability Plan
                        </Button>
                    </motion.div>
                )}

                {phase === 'generating' && (
                    <motion.div key="generating" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center justify-center py-20 gap-6">
                        <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 2, ease: 'linear' }}>
                            <FileText className="h-12 w-12 text-[var(--re-brand)]" />
                        </motion.div>
                        <div className="text-lg font-bold">Generating your Traceability Plan...</div>
                        <div className="text-sm text-muted-foreground">Customizing CTE procedures for {formData.company_type}</div>
                    </motion.div>
                )}

                {phase === 'preview' && (
                    <motion.div key="preview" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
                        <div className="flex items-center gap-3">
                            <CheckCircle2 className="h-6 w-6 text-emerald-500" />
                            <h2 className="text-lg font-bold">Plan Generated</h2>
                        </div>

                        <LeadGate
                            source="sop-generator"
                            headline="Download Your Traceability Plan"
                            subheadline="Get the full FSMA 204 SOP document customized for your operation — ready to print, share with auditors, or submit to retailers."
                            ctaText="Unlock Full Plan"
                            toolContext={{ toolInputs: formData }}
                            teaser={
                                <div className="space-y-2 pb-4">
                                    <p className="text-sm text-[var(--re-text-muted)]">Your plan has been generated with custom CTE procedures.</p>
                                    <pre className="whitespace-pre-wrap text-xs font-mono text-[var(--re-text-muted)] max-h-[120px] overflow-hidden">{generatedDoc?.slice(0, 400)}...</pre>
                                </div>
                            }
                        >
                            <div className="space-y-4">
                                <div className="flex gap-2">
                                    <Button variant="outline" size="sm" className="rounded-xl">
                                        <Download className="h-3 w-3 mr-1" /> Download Full PDF
                                    </Button>
                                    <Button variant="outline" size="sm" className="rounded-xl">
                                        <Printer className="h-3 w-3 mr-1" /> Print
                                    </Button>
                                </div>
                                <Card className="border-[var(--re-border-default)]">
                                    <CardContent className="py-6">
                                        <pre className="whitespace-pre-wrap text-sm font-mono leading-relaxed text-foreground">
                                            {generatedDoc}
                                        </pre>
                                    </CardContent>
                                </Card>
                                <Button onClick={() => setPhase('form')} variant="outline" className="rounded-xl">
                                    ← Edit & Regenerate
                                </Button>
                            </div>
                        </LeadGate>
                    </motion.div>
                )}
            </AnimatePresence>
        </FreeToolPageShell>
    );
}
