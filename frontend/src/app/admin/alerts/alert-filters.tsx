'use client';

import { Button } from '@/components/ui/button';
import { Filter } from 'lucide-react';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuLabel,
    DropdownMenuRadioGroup,
    DropdownMenuRadioItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface AlertFiltersProps {
    severity: string;
    setSeverity: (val: string) => void;
    type: string;
    setType: (val: string) => void;
}

export function AlertFilters({ severity, setSeverity, type, setType }: AlertFiltersProps) {
    return (
        <div className="flex gap-2">
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" className="gap-2">
                        <Filter className="w-4 h-4" />
                        Severity: {severity === 'ALL' ? 'All' : severity}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                    <DropdownMenuLabel>Alert Severity</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuRadioGroup value={severity} onValueChange={setSeverity}>
                        <DropdownMenuRadioItem value="ALL">All Severities</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="CRITICAL">Critical</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="WARNING">Warning</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="INFO">Info</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                </DropdownMenuContent>
            </DropdownMenu>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" className="gap-2">
                        <Filter className="w-4 h-4" />
                        Type: {type === 'ALL' ? 'All' : type}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                    <DropdownMenuLabel>Alert Type</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    <DropdownMenuRadioGroup value={type} onValueChange={setType}>
                        <DropdownMenuRadioItem value="ALL">All Types</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="trace_completeness">Trace Links</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="latency">Latency</DropdownMenuRadioItem>
                        <DropdownMenuRadioItem value="error_rate">Errors</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
