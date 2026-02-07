'use client';

import { Button } from '@/components/ui/button';
import { Download } from 'lucide-react';

export function ExportButton() {
    return (
        <Button
            className="bg-emerald-600 hover:bg-emerald-700"
            onClick={() => window.print()}
        >
            <Download className="h-4 w-4 mr-2" />
            Export to PDF
        </Button>
    );
}
