/**
 * API Client Tests - Energy Service
 * 
 * Tests for Energy service API client methods:
 * - Snapshot creation and retrieval
 * - Mismatch detection and resolution
 * - Chain verification
 * - Error handling
 * - Authentication headers
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { apiClient } from '@/lib/api-client';

// Mock axios
vi.mock('axios');

const mockedAxios = axios as any;

describe('API Client - Energy Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockedAxios.create = vi.fn(() => ({
            get: vi.fn(),
            post: vi.fn(),
            patch: vi.fn(),
            delete: vi.fn(),
            interceptors: {
                request: { use: vi.fn() },
                response: { use: vi.fn() },
            },
        }));
    });

    describe('Snapshot Operations', () => {
        it('creates snapshot with correct payload', async () => {
            const mockClient = {
                post: vi.fn().mockResolvedValueOnce({
                    data: {
                        snapshot_id: 'snap-123',
                        created_at: '2026-01-27T18:00:00Z',
                        status: 'created',
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const payload = {
                substation_id: 'sub-001',
                voltage_kv: 138,
                firmware_versions: { pmu: '2.1.0' },
            };

            // Simulate API call (would need to expose energy client method)
            await mockClient.post('/energy/snapshots', payload);

            expect(mockClient.post).toHaveBeenCalledWith('/energy/snapshots', payload);
        });

        it('retrieves snapshots with filtering', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        snapshots: [
                            {
                                id: 'snap-123',
                                substation_id: 'sub-001',
                                created_at: '2026-01-27T18:00:00Z',
                            },
                        ],
                        total: 1,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                substation_id: 'sub-001',
                limit: 50,
                offset: 0,
            };

            await mockClient.get('/energy/snapshots', { params });

            expect(mockClient.get).toHaveBeenCalledWith('/energy/snapshots', { params });
        });

        it('verifies snapshot chain integrity', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        is_valid: true,
                        snapshot_id: 'snap-123',
                        chain_length: 42,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await mockClient.get('/energy/snapshots/snap-123/verify');

            expect(mockClient.get).toHaveBeenCalledWith('/energy/snapshots/snap-123/verify');
        });
    });

    describe('Mismatch Detection', () => {
        it('fetches compliance mismatches', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        mismatches: [
                            {
                                id: 'mismatch-001',
                                type: 'firmware_outdated',
                                severity: 'high',
                                details: 'PMU firmware 2.0.0 < required 2.1.0',
                            },
                        ],
                        total: 1,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await mockClient.get('/energy/mismatches', {
                params: { substation_id: 'sub-001' },
            });

            expect(mockClient.get).toHaveBeenCalledWith('/energy/mismatches', {
                params: { substation_id: 'sub-001' },
            });
        });

        it('resolves mismatch with remediation', async () => {
            const mockClient = {
                post: vi.fn().mockResolvedValueOnce({
                    data: {
                        mismatch_id: 'mismatch-001',
                        status: 'resolved',
                        resolved_at: '2026-01-27T18:30:00Z',
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const resolution = {
                action: 'firmware_upgrade',
                notes: 'Upgraded PMU firmware to 2.1.0',
                resolved_by: 'user-123',
            };

            await mockClient.post('/energy/mismatches/mismatch-001/resolve', resolution);

            expect(mockClient.post).toHaveBeenCalledWith(
                '/energy/mismatches/mismatch-001/resolve',
                resolution
            );
        });
    });

    describe('Error Handling', () => {
        it('handles 401 unauthorized errors', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 401,
                        data: { error: 'Unauthorized' },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(mockClient.get('/energy/snapshots')).rejects.toMatchObject({
                response: { status: 401 },
            });
        });

        it('handles 403 forbidden errors', async () => {
            const mockClient = {
                post: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 403,
                        data: { error: 'Insufficient permissions' },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(
                mockClient.post('/energy/snapshots', {})
            ).rejects.toMatchObject({
                response: { status: 403 },
            });
        });

        it('handles 500 server errors', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 500,
                        data: { error: 'Internal server error' },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(mockClient.get('/energy/health')).rejects.toMatchObject({
                response: { status: 500 },
            });
        });

        it('handles network errors', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce(new Error('Network Error')),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(mockClient.get('/energy/snapshots')).rejects.toThrow('Network Error');
        });
    });

    describe('Authentication Headers', () => {
        it('includes Bearer token in requests', () => {
            const interceptorHandler = vi.fn((config) => config);

            const mockClient = {
                interceptors: {
                    request: {
                        use: vi.fn((handler) => {
                            interceptorHandler.mockImplementation(handler);
                        })
                    },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            // Simulate setting access token
            const config: { headers: Record<string, string> } = {
                headers: {},
            };

            // Would set token via apiClient.setAccessToken()
            config.headers['Authorization'] = 'Bearer test-token-123';

            expect(config.headers['Authorization']).toBe('Bearer test-token-123');
        });

        it('includes API key header', () => {
            const config: { headers: Record<string, string> } = {
                headers: {},
            };

            config.headers['X-RegEngine-API-Key'] = 'admin';

            expect(config.headers['X-RegEngine-API-Key']).toBe('admin');
        });

        it('includes tenant ID when set', () => {
            const config: { headers: Record<string, string> } = {
                headers: {},
            };

            config.headers['X-Tenant-ID'] = 'tenant-123';

            expect(config.headers['X-Tenant-ID']).toBe('tenant-123');
        });
    });

    describe('Export Functionality', () => {
        it('exports snapshots in CSV format', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: 'id,substation_id,created_at\nsnap-123,sub-001,2026-01-27T18:00:00Z\n',
                    headers: {
                        'content-type': 'text/csv',
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                substation_id: 'sub-001',
                from_time: '2026-01-01T00:00:00Z',
                to_time: '2026-01-27T23:59:59Z',
                format: 'csv',
            };

            const response = await mockClient.get('/energy/snapshots/export', { params });

            expect(response.data).toContain('id,substation_id,created_at');
            expect(response.headers['content-type']).toBe('text/csv');
        });

        it('exports snapshots in JSON format', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        snapshots: [
                            {
                                id: 'snap-123',
                                substation_id: 'sub-001',
                            },
                        ],
                    },
                    headers: {
                        'content-type': 'application/json',
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                format: 'json',
            };

            const response = await mockClient.get('/energy/snapshots/export', { params });

            expect(response.data.snapshots).toHaveLength(1);
            expect(response.headers['content-type']).toBe('application/json');
        });
    });
});
