export interface ReviewItem {
    id: string;
    source_text: string;
    extracted_data: Record<string, unknown>; // Arbitrary parsed JSON
    confidence_score: number;
    status: 'PENDING' | 'APPROVED' | 'REJECTED';
    created_at: string;
    updated_at: string;
    tenant_id: string;
}

export interface ReviewStats {
    pending: number;
    approved: number;
    rejected: number;
}
