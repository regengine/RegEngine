'use client';

import * as React from 'react';
import { Check, ChevronsUpDown, Building2, Loader2 } from 'lucide-react';

import { useTenant } from '@/lib/tenant-context';
import { useOrganizations } from '@/hooks/use-organizations';
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
} from '@/components/ui/command';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/components/ui/popover';

const PLAN_BADGES: Record<string, { label: string; className: string } | undefined> = {
    enterprise: { label: 'Enterprise', className: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
    professional: { label: 'Pro', className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
    starter: undefined,
    free: undefined,
};

export function TenantSwitcher() {
    const { tenantId, setTenantId } = useTenant();
    const { organizations, isLoading } = useOrganizations();
    const [open, setOpen] = React.useState(false);

    const selectedOrg = organizations.find((o) => o.id === tenantId);
    const displayName = selectedOrg?.name ?? 'Select Organization';

    // If orgs loaded and current tenant isn't in the list, auto-select first
    React.useEffect(() => {
        if (!isLoading && organizations.length > 0 && !selectedOrg) {
            setTenantId(organizations[0].id);
        }
    }, [isLoading, organizations, selectedOrg, setTenantId]);

    if (isLoading) {
        return (
            <Button variant="outline" className="w-full md:w-[320px] justify-between text-left font-normal" disabled>
                <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Loading organizations...</span>
                </div>
            </Button>
        );
    }

    if (organizations.length === 0) {
        return (
            <Button variant="outline" className="w-full md:w-[320px] justify-between text-left font-normal" disabled>
                <div className="flex items-center gap-2 text-muted-foreground">
                    <Building2 className="h-4 w-4" />
                    <span>No organizations yet</span>
                </div>
            </Button>
        );
    }

    // Single org — no switcher needed, just display
    if (organizations.length === 1) {
        return (
            <div className="flex items-center gap-2 px-3 py-2 text-sm">
                <Building2 className="h-4 w-4 text-muted-foreground" />
                <span className="font-medium">{organizations[0].name}</span>
                {PLAN_BADGES[organizations[0].plan] && (
                    <Badge variant="secondary" className={cn("text-[10px] px-1.5 py-0 h-4", PLAN_BADGES[organizations[0].plan]!.className)}>
                        {PLAN_BADGES[organizations[0].plan]!.label}
                    </Badge>
                )}
            </div>
        );
    }

    return (
        <Popover open={open} onOpenChange={setOpen} modal={true}>
            <PopoverTrigger asChild>
                <Button
                    id="onboarding-tenant-switcher"
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    aria-label="Select organization"
                    className="w-full md:w-[320px] justify-between text-left font-normal"
                >
                    <div className="flex items-center truncate gap-2">
                        <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate flex-1 text-left">{displayName}</span>
                        {selectedOrg && PLAN_BADGES[selectedOrg.plan] && (
                            <Badge variant="secondary" className={cn("text-[10px] px-1.5 py-0 h-4 shrink-0", PLAN_BADGES[selectedOrg.plan]!.className)}>
                                {PLAN_BADGES[selectedOrg.plan]!.label}
                            </Badge>
                        )}
                    </div>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-full md:w-[320px] p-0 bg-white dark:bg-zinc-950 border border-border shadow-2xl z-50">
                <Command>
                    <CommandInput placeholder="Search organizations..." />
                    <CommandList className="max-h-[400px]">
                        <CommandEmpty>No organization found.</CommandEmpty>
                        <CommandGroup heading="Organizations">
                            {organizations.map((org) => {
                                const planBadge = PLAN_BADGES[org.plan];
                                return (
                                    <CommandItem
                                        key={org.id}
                                        value={org.name}
                                        onSelect={() => {
                                            setTenantId(org.id);
                                            setOpen(false);
                                        }}
                                    >
                                        <Check
                                            className={cn(
                                                "mr-2 h-4 w-4",
                                                tenantId === org.id ? "opacity-100" : "opacity-0"
                                            )}
                                        />
                                        <Building2 className="mr-2 h-4 w-4 text-muted-foreground" />
                                        <span className="flex-1">{org.name}</span>
                                        {planBadge && (
                                            <Badge variant="secondary" className={cn("text-[9px] px-1 py-0 h-3.5 ml-1", planBadge.className)}>
                                                {planBadge.label}
                                            </Badge>
                                        )}
                                    </CommandItem>
                                );
                            })}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
}
