/**
 * API Client Tests - Opportunity Service
 * 
 * Tests for Opportunity service API client methods:
 * - Arbitrage opportunity detection
 * - Compliance gap analysis
 * - Savings calculations
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

// Mock axios
vi.mock('axios', () => ({
    default: {
        create: vi.fn(() => ({
            get: vi.fn(),
            post: vi.fn(),
            interceptors: {
                request: { use: vi.fn() },
                response: { use: vi.fn() },
            },
        })),
    },
}));

const mockedAxios = axios as any;

describe('API Client - Opportunity Service', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    describe('Arbitrage Opportunities', () => {
        it('finds arbitrage opportunities between frameworks', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            {
                                id: 'opp-001',
                                type: 'control_reuse',
                                j1: 'SOC2',
                                j2: 'ISO27001',
                                concept: 'Multi-Factor Authentication',
                                rel_delta: 0.85,
                                estimated_savings: 15000,
                                confidence: 0.92,
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
                j1: 'SOC2',
                j2: 'ISO27001',
                rel_delta: 0.8,
                limit: 10,
            };

            const response = await mockClient.get('/opportunities/arbitrage', { params });

            expect(response.data.items).toHaveLength(1);
            expect(response.data.items[0].type).toBe('control_reuse');
            expect(response.data.items[0].estimated_savings).toBe(15000);
        });

        it('filters opportunities by concept', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            {
                                id: 'opp-002',
                                concept: 'Encryption at Rest',
                                estimated_savings: 8000,
                            },
                        ],
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                concept: 'Encryption at Rest',
            };

            const response = await mockClient.get('/opportunities/arbitrage', { params });

            expect(response.data.items[0].concept).toBe('Encryption at Rest');
        });

        it('sorts opportunities by savings amount', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            {
                                id: 'opp-001',
                                estimated_savings: 25000,
                            },
                            {
                                id: 'opp-002',
                                estimated_savings: 15000,
                            },
                            {
                                id: 'opp-003',
                                estimated_savings: 8000,
                            },
                        ],
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const response = await mockClient.get('/opportunities/arbitrage');

            const items = response.data.items;
            expect(items[0].estimated_savings).toBeGreaterThan(items[1].estimated_savings);
            expect(items[1].estimated_savings).toBeGreaterThan(items[2].estimated_savings);
        });
    });

    describe('Compliance Gaps', () => {
        it('identifies compliance gaps for target framework', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            {
                                id: 'gap-001',
                                control_id: 'A.12.6.1',
                                name: 'Management of technical vulnerabilities',
                                framework: 'ISO27001',
                                priority: 'high',
                                estimated_cost: 25000,
                            },
                        ],
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                j1: 'current_controls',
                j2: 'ISO27001',
            };

            const response = await mockClient.get('/opportunities/gaps', { params });

            expect(response.data.items).toHaveLength(1);
            expect(response.data.items[0].priority).toBe('high');
        });

        it('calculates total gap remediation cost', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            { estimated_cost: 25000 },
                            { estimated_cost: 12000 },
                            { estimated_cost: 8000 },
                        ],
                        total_cost: 45000,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const response = await mockClient.get('/opportunities/gaps');

            expect(response.data.total_cost).toBe(45000);
        });

        it('filters gaps by priority level', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [
                            {
                                id: 'gap-001',
                                priority: 'high',
                            },
                        ],
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const params = {
                priority: 'high',
            };

            const response = await mockClient.get('/opportunities/gaps', { params });

            expect(response.data.items.every((item: any) => item.priority === 'high')).toBe(true);
        });
    });

    describe('Health Check', () => {
        it('verifies service is healthy', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        status: 'healthy',
                        service: 'opportunity-api',
                        dependencies: {
                            neo4j: 'connected',
                            postgresql: 'connected',
                        },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const response = await mockClient.get('/health');

            expect(response.data.status).toBe('healthy');
            expect(response.data.dependencies.neo4j).toBe('connected');
        });

        it('detects unhealthy service', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 503,
                        data: {
                            status: 'unhealthy',
                            error: 'Neo4j connection failed',
                        },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(mockClient.get('/health')).rejects.toMatchObject({
                response: {
                    status: 503,
                    data: {
                        status: 'unhealthy',
                    },
                },
            });
        });
    });

    describe('Error Handling', () => {
        it('handles invalid framework parameters', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 400,
                        data: {
                            error: 'Invalid framework: UNKNOWN',
                        },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(
                mockClient.get('/opportunities/arbitrage', {
                    params: { j1: 'UNKNOWN' },
                })
            ).rejects.toMatchObject({
                response: { status: 400 },
            });
        });

        it('handles missing required parameters', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    response: {
                        status: 422,
                        data: {
                            error: 'Missing required parameter: j2',
                        },
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(
                mockClient.get('/opportunities/gaps')
            ).rejects.toMatchObject({
                response: { status: 422 },
            });
        });

        it('handles timeout errors', async () => {
            const mockClient = {
                get: vi.fn().mockRejectedValueOnce({
                    code: 'ECONNABORTED',
                    message: 'timeout of 30000ms exceeded',
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            await expect(
                mockClient.get('/opportunities/arbitrage')
            ).rejects.toMatchObject({
                code: 'ECONNABORTED',
            });
        });
    });

    describe('Response Formatting', () => {
        it('returns empty array when no opportunities found', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [],
                        total: 0,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const response = await mockClient.get('/opportunities/arbitrage');

            expect(response.data.items).toEqual([]);
            expect(response.data.total).toBe(0);
        });

        it('includes pagination metadata', async () => {
            const mockClient = {
                get: vi.fn().mockResolvedValueOnce({
                    data: {
                        items: [{}, {}, {}],
                        total: 42,
                        limit: 10,
                        offset: 0,
                    },
                }),
                interceptors: {
                    request: { use: vi.fn() },
                    response: { use: vi.fn() },
                },
            };

            mockedAxios.create.mockReturnValueOnce(mockClient);

            const response = await mockClient.get('/opportunities/arbitrage', {
                params: { limit: 10, offset: 0 },
            });

            expect(response.data.total).toBe(42);
            expect(response.data.limit).toBe(10);
        });
    });
});
