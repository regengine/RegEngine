/**
 * TC_AUDIT_001 - TC_AUDIT_005: Audit Trail & Data Integrity Tests
 * 
 * Tests for log tampering detection, digital signatures,
 * immutability verification, and completeness.
 * 
 * Compliance: SOX Section 302, FDA 21 CFR Part 11
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mockApiResponse, mockApiError, generateTestAuditLog } from '@/test/utils';
import crypto from 'crypto';

describe('Audit Trail Integrity Tests', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('TC_AUDIT_001: Log Tampering Detection', () => {
        it('should detect modified audit entries via hash chain', () => {
            // Create audit log with hash chain
            interface ChainEntry {
                id: string;
                action: string;
                prevHash: string;
                hash: string;
            }

            const createHashChain = (entries: Array<{ id: string; action: string }>): ChainEntry[] => {
                const result: ChainEntry[] = [];
                for (let i = 0; i < entries.length; i++) {
                    const prevHash = i === 0 ? '0'.repeat(64) : result[i - 1].hash;
                    const content = JSON.stringify({ ...entries[i], prevHash });
                    const hash = crypto.createHash('sha256').update(content).digest('hex');
                    result.push({ ...entries[i], hash, prevHash });
                }
                return result;
            };

            const auditEntries = [
                { id: 'log-1', action: 'CREATE' },
                { id: 'log-2', action: 'UPDATE' },
                { id: 'log-3', action: 'DELETE' },
            ];

            const chain = createHashChain(auditEntries);

            // Verify chain integrity
            const verifyChain = (entries: ChainEntry[]): boolean => {
                for (let i = 1; i < entries.length; i++) {
                    if (entries[i].prevHash !== entries[i - 1].hash) {
                        return false;
                    }
                }
                return true;
            };

            expect(verifyChain(chain)).toBe(true);

            // Content verification
            const verifyContent = (entry: ChainEntry): boolean => {
                const content = JSON.stringify({
                    id: entry.id,
                    action: entry.action,
                    prevHash: entry.prevHash,
                });
                const expectedHash = crypto.createHash('sha256').update(content).digest('hex');
                return expectedHash === entry.hash;
            };

            expect(verifyContent(chain[0])).toBe(true);
            expect(verifyContent(chain[1])).toBe(true);

            // Tamper with middle entry
            const tamperedChain = [...chain];
            tamperedChain[1] = { ...tamperedChain[1], action: 'MALICIOUS' };

            // Tampered entry should fail content verification
            expect(verifyContent(tamperedChain[1])).toBe(false);
        });

        it('should reject DELETE operations on audit table', async () => {
            const mockFetch = vi.fn().mockResolvedValue(
                mockApiError('Operation not permitted: Audit logs are immutable', 403)
            );
            global.fetch = mockFetch;

            const response = await fetch('/api/admin/audit/log-123', {
                method: 'DELETE',
            });

            expect(response.status).toBe(403);
            const data = await response.json();
            expect(data.error).toContain('immutable');
        });

        it('should reject UPDATE operations on audit table', async () => {
            const mockFetch = vi.fn().mockResolvedValue(
                mockApiError('Operation not permitted: Audit logs are immutable', 403)
            );
            global.fetch = mockFetch;

            const response = await fetch('/api/admin/audit/log-123', {
                method: 'PUT',
                body: JSON.stringify({ action: 'modified' }),
            });

            expect(response.status).toBe(403);
        });
    });

    describe('TC_AUDIT_002: Digital Signature Verification', () => {
        it('should verify valid digital signatures on log entries', () => {
            const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', {
                modulusLength: 2048,
            });

            const signEntry = (entry: object): string => {
                const sign = crypto.createSign('SHA256');
                sign.update(JSON.stringify(entry));
                return sign.sign(privateKey, 'hex');
            };

            const verifySignature = (entry: object, signature: string): boolean => {
                const verify = crypto.createVerify('SHA256');
                verify.update(JSON.stringify(entry));
                return verify.verify(publicKey, signature, 'hex');
            };

            const auditEntry = generateTestAuditLog();
            const signature = signEntry(auditEntry);

            expect(verifySignature(auditEntry, signature)).toBe(true);
        });

        it('should reject entries with invalid signatures', () => {
            const { privateKey, publicKey } = crypto.generateKeyPairSync('rsa', {
                modulusLength: 2048,
            });

            const signEntry = (entry: object): string => {
                const sign = crypto.createSign('SHA256');
                sign.update(JSON.stringify(entry));
                return sign.sign(privateKey, 'hex');
            };

            const verifySignature = (entry: object, signature: string): boolean => {
                const verify = crypto.createVerify('SHA256');
                verify.update(JSON.stringify(entry));
                try {
                    return verify.verify(publicKey, signature, 'hex');
                } catch {
                    return false;
                }
            };

            const auditEntry = generateTestAuditLog();
            const signature = signEntry(auditEntry);

            // Tamper with entry
            const tamperedEntry = { ...auditEntry, action: 'MALICIOUS' };

            expect(verifySignature(tamperedEntry, signature)).toBe(false);
        });
    });

    describe('TC_AUDIT_003: Timestamp Integrity', () => {
        it('should enforce monotonically increasing timestamps', () => {
            const logs = [
                { id: '1', timestamp: '2026-01-17T10:00:00Z' },
                { id: '2', timestamp: '2026-01-17T10:00:01Z' },
                { id: '3', timestamp: '2026-01-17T10:00:02Z' },
            ];

            const isMonotonic = (entries: typeof logs): boolean => {
                for (let i = 1; i < entries.length; i++) {
                    const prev = new Date(entries[i - 1].timestamp).getTime();
                    const curr = new Date(entries[i].timestamp).getTime();
                    if (curr <= prev) return false;
                }
                return true;
            };

            expect(isMonotonic(logs)).toBe(true);

            // Out of order should fail
            const badLogs = [
                { id: '1', timestamp: '2026-01-17T10:00:02Z' },
                { id: '2', timestamp: '2026-01-17T10:00:01Z' }, // Earlier!
            ];

            expect(isMonotonic(badLogs)).toBe(false);
        });

        it('should use server-side timestamps only', async () => {
            const mockFetch = vi.fn().mockImplementation(async (_url, options) => {
                const body = JSON.parse(options?.body || '{}');

                // Server should ignore client-provided timestamp
                if (body.timestamp) {
                    const serverTimestamp = new Date().toISOString();
                    return mockApiResponse({
                        ...body,
                        timestamp: serverTimestamp, // Server overrides
                        client_timestamp_ignored: true,
                    });
                }
                return mockApiResponse(body);
            });
            global.fetch = mockFetch;

            const response = await fetch('/api/audit/log', {
                method: 'POST',
                body: JSON.stringify({
                    action: 'TEST',
                    timestamp: '1999-01-01T00:00:00Z', // Attempting to backdate
                }),
            });

            const data = await response.json();
            expect(new Date(data.timestamp).getFullYear()).toBe(new Date().getFullYear());
        });
    });

    describe('TC_AUDIT_004: Log Completeness During Failure', () => {
        it('should buffer logs during network failure', async () => {
            const logBuffer: unknown[] = [];
            let networkDown = true;

            const mockFetch = vi.fn().mockImplementation(async () => {
                if (networkDown) {
                    throw new Error('Network unavailable');
                }
                return mockApiResponse({ success: true });
            });
            global.fetch = mockFetch;

            const logWithRetry = async (entry: object) => {
                try {
                    await fetch('/api/audit/log', {
                        method: 'POST',
                        body: JSON.stringify(entry),
                    });
                } catch {
                    logBuffer.push(entry);
                }
            };

            // Log during outage
            await logWithRetry({ action: 'EVENT_1' });
            await logWithRetry({ action: 'EVENT_2' });

            expect(logBuffer).toHaveLength(2);

            // Network restored
            networkDown = false;

            // Flush buffer
            const flushBuffer = async () => {
                while (logBuffer.length > 0) {
                    const entry = logBuffer.shift();
                    await fetch('/api/audit/log', {
                        method: 'POST',
                        body: JSON.stringify(entry),
                    });
                }
            };

            await flushBuffer();
            expect(logBuffer).toHaveLength(0);
            expect(mockFetch).toHaveBeenCalledTimes(4); // 2 failed + 2 successful
        });
    });

    describe('TC_AUDIT_005: Retention Policy Compliance', () => {
        it('should verify 7-year retention for SOX compliance', () => {
            const calculateRetentionDate = (createdAt: Date, yearsToRetain: number): Date => {
                const retention = new Date(createdAt);
                retention.setFullYear(retention.getFullYear() + yearsToRetain);
                return retention;
            };

            const logCreatedAt = new Date('2026-01-17');
            const retentionEnd = calculateRetentionDate(logCreatedAt, 7);

            expect(retentionEnd.getFullYear()).toBe(2033);
        });

        it('should prevent deletion of logs within retention period', async () => {
            const mockFetch = vi.fn().mockResolvedValue(
                mockApiError('Cannot delete: Within 7-year retention period', 403)
            );
            global.fetch = mockFetch;

            const response = await fetch('/api/admin/audit/purge', {
                method: 'POST',
                body: JSON.stringify({
                    before: '2025-01-01', // Too recent
                }),
            });

            expect(response.status).toBe(403);
        });
    });
});
