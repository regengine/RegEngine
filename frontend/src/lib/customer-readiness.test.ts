import { describe, expect, it } from 'vitest';
import {
    CAPABILITY_REGISTRY,
    DELIVERY_MODE_LABELS,
    STATUS_LABELS,
    TRUST_ARTIFACTS,
} from '@/lib/customer-readiness';

describe('customer readiness registry', () => {
    it('uses unique capability ids', () => {
        const ids = CAPABILITY_REGISTRY.map((item) => item.id);
        expect(new Set(ids).size).toBe(ids.length);
    });

    it('only uses statuses and delivery modes with labels', () => {
        for (const item of CAPABILITY_REGISTRY) {
            expect(STATUS_LABELS[item.status]).toBeTruthy();
            expect(DELIVERY_MODE_LABELS[item.delivery_mode]).toBeTruthy();
        }
    });

    it('exposes at least one public diligence artifact', () => {
        expect(TRUST_ARTIFACTS.some((artifact) => artifact.access === 'public')).toBe(true);
    });

    it('never renders SFTP in display text for the csv-sftp key or csv_sftp_import label', () => {
        expect(DELIVERY_MODE_LABELS.csv_sftp_import).not.toMatch(/sftp/i);
        const entry = CAPABILITY_REGISTRY.find((item) => item.id === 'csv-sftp');
        expect(entry).toBeDefined();
        expect(entry?.name).not.toMatch(/sftp/i);
        expect(entry?.customer_copy).not.toMatch(/sftp/i);
    });
});
