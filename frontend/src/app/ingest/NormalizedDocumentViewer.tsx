'use client';

import { Card, CardContent } from '@/components/ui/card';

interface ViewerProps {
    documentId: string;
}

/** Ingestion receipt only; no extraction endpoint backs this view yet. */
export function NormalizedDocumentViewer({ documentId }: ViewerProps) {
    return (
        <Card>
            <CardContent className="p-6 space-y-3">
                <h3 className="font-semibold">Document received</h3>
                <p className="text-sm text-muted-foreground">Document ID: {documentId}</p>
                <p role="status" className="text-sm text-muted-foreground">
                    Extracted content is not available in this view. Receipt does not confirm
                    normalization, validation, or traceability evidence persistence.
                </p>
            </CardContent>
        </Card>
    );
}
