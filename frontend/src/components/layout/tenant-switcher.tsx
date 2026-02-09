'use client';

import * as React from 'react';
import { Check, ChevronsUpDown, Building, Store, Factory, Crown } from 'lucide-react';

import { useTenant } from '@/lib/tenant-context';
import { MOCK_TENANTS, type IndustrySegment } from '@/lib/mock-tenants';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
    CommandSeparator,
} from '@/components/ui/command';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';

// Industry icons and colors
const INDUSTRY_CONFIG: Record<IndustrySegment, { icon: string; color: string }> = {
    administration: { icon: '⚙️', color: 'text-gray-500' },
    grocery: { icon: '🛒', color: 'text-blue-500' },
    produce: { icon: '🥬', color: 'text-green-500' },
    seafood: { icon: '🐟', color: 'text-cyan-500' },
    meat: { icon: '🥩', color: 'text-red-500' },
    dairy: { icon: '🧀', color: 'text-yellow-500' },
    organic: { icon: '🌿', color: 'text-emerald-500' },
    specialty: { icon: '✨', color: 'text-purple-500' },
};

const TIER_BADGES: Record<string, { label: string; className: string } | undefined> = {
    enterprise: { label: 'Enterprise', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
    scale: { label: 'Scale', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
    growth: undefined,
    starter: undefined,
};

export function TenantSwitcher() {
    const { tenantId, setTenantId } = useTenant();
    const [open, setOpen] = React.useState(false);

    const selectedTenant = MOCK_TENANTS.find((t) => t.id === tenantId) || MOCK_TENANTS[0];
    const selectedConfig = INDUSTRY_CONFIG[selectedTenant.industry ?? 'administration'];
    const selectedTierBadge = selectedTenant.subscriptionTier ? TIER_BADGES[selectedTenant.subscriptionTier] : undefined;

    // Categorize Tenants using type field
    const retailers = MOCK_TENANTS.filter(t => t.type === 'retailer');
    const suppliers = MOCK_TENANTS.filter(t => t.type === 'supplier');
    const admins = MOCK_TENANTS.filter(t => t.type === 'system');

    // Group suppliers by industry for sub-sections
    const suppliersByIndustry = React.useMemo(() => {
        const groups: Record<string, typeof suppliers> = {};
        suppliers.forEach(s => {
            const industry = s.industry ?? 'administration';
            if (!groups[industry]) groups[industry] = [];
            groups[industry].push(s);
        });
        return groups;
    }, [suppliers]);

    return (
        <Popover open={open} onOpenChange={setOpen} modal={true}>
            <PopoverTrigger asChild>
                <Button
                    id="onboarding-tenant-switcher"
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    aria-label="Select tenant organization"
                    className="w-full md:w-[320px] justify-between text-left font-normal"
                >
                    <div className="flex items-center truncate gap-2">
                        <span className="text-base" role="img" aria-label={selectedTenant.industry}>
                            {selectedConfig.icon}
                        </span>
                        <span className="truncate flex-1 text-left">{selectedTenant.name}</span>
                        {selectedTierBadge && (
                            <Badge variant="secondary" className={cn("text-[10px] px-1.5 py-0 h-4 shrink-0", selectedTierBadge.className)}>
                                {selectedTierBadge.label}
                            </Badge>
                        )}
                    </div>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-full md:w-[320px] p-0 bg-white dark:bg-zinc-950 border border-border shadow-2xl z-50">
                <Command>
                    <CommandInput placeholder="Search tenants..." />
                    <CommandList className="max-h-[400px]">
                        <CommandEmpty>No tenant found.</CommandEmpty>

                        <CommandGroup heading="System">
                            {admins.map((tenant) => {
                                const config = INDUSTRY_CONFIG[tenant.industry ?? 'administration'];
                                return (
                                    <CommandItem
                                        key={tenant.id}
                                        value={tenant.name}
                                        onSelect={() => {
                                            setTenantId(tenant.id);
                                            setOpen(false);
                                        }}
                                    >
                                        <Check
                                            className={cn(
                                                "mr-2 h-4 w-4",
                                                tenantId === tenant.id ? "opacity-100" : "opacity-0"
                                            )}
                                        />
                                        <span className="mr-2">{config.icon}</span>
                                        {tenant.name}
                                    </CommandItem>
                                );
                            })}
                        </CommandGroup>

                        <CommandSeparator />

                        <CommandGroup heading="Retailers">
                            {retailers.map((tenant) => {
                                const config = INDUSTRY_CONFIG[tenant.industry ?? 'grocery'];
                                const tierBadge = tenant.subscriptionTier ? TIER_BADGES[tenant.subscriptionTier] : undefined;
                                return (
                                    <CommandItem
                                        key={tenant.id}
                                        value={tenant.name}
                                        onSelect={() => {
                                            setTenantId(tenant.id);
                                            setOpen(false);
                                        }}
                                    >
                                        <Check
                                            className={cn(
                                                "mr-2 h-4 w-4",
                                                tenantId === tenant.id ? "opacity-100" : "opacity-0"
                                            )}
                                        />
                                        <span className="mr-2">{config.icon}</span>
                                        <span className="flex-1">{tenant.name}</span>
                                        {tierBadge && (
                                            <Badge variant="secondary" className={cn("text-[9px] px-1 py-0 h-3.5 ml-1", tierBadge.className)}>
                                                {tierBadge.label}
                                            </Badge>
                                        )}
                                    </CommandItem>
                                );
                            })}
                        </CommandGroup>

                        <CommandSeparator />

                        {/* Suppliers grouped by industry */}
                        {Object.entries(suppliersByIndustry).map(([industry, tenants]) => {
                            const industryConfig = INDUSTRY_CONFIG[industry as IndustrySegment];
                            const industryLabel = industry.charAt(0).toUpperCase() + industry.slice(1);
                            return (
                                <React.Fragment key={industry}>
                                    <CommandGroup heading={`${industryConfig.icon} ${industryLabel}`}>
                                        {tenants.map((tenant) => {
                                            const tierBadge = tenant.subscriptionTier ? TIER_BADGES[tenant.subscriptionTier] : undefined;
                                            return (
                                                <CommandItem
                                                    key={tenant.id}
                                                    value={tenant.name}
                                                    onSelect={() => {
                                                        setTenantId(tenant.id);
                                                        setOpen(false);
                                                    }}
                                                >
                                                    <Check
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            tenantId === tenant.id ? "opacity-100" : "opacity-0"
                                                        )}
                                                    />
                                                    <span className="flex-1">{tenant.name}</span>
                                                    {tierBadge && (
                                                        <Badge variant="secondary" className={cn("text-[9px] px-1 py-0 h-3.5 ml-1", tierBadge.className)}>
                                                            {tierBadge.label}
                                                        </Badge>
                                                    )}
                                                </CommandItem>
                                            );
                                        })}
                                    </CommandGroup>
                                </React.Fragment>
                            );
                        })}

                        <CommandSeparator />
                        <CommandGroup heading="Context">
                            <div className="px-2 py-2 text-xs text-muted-foreground">
                                <p className="mb-1 font-medium text-foreground">Multi-Tenant Simulation</p>
                                <p>
                                    Each tenant sees isolated data &amp; metrics. Quick actions and dashboard stats adjust based on tenant type.
                                </p>
                            </div>
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}
