import { render, RenderOptions } from '@testing-library/react';
import { ReactElement } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Create a fresh QueryClient for each test
const createTestQueryClient = () =>
    new QueryClient({
        defaultOptions: {
            queries: {
                retry: false,
                gcTime: 0,
            },
        },
    });

interface WrapperProps {
    children: React.ReactNode;
}

const AllTheProviders = ({ children }: WrapperProps) => {
    const queryClient = createTestQueryClient();

    return (
        <QueryClientProvider client={queryClient}>
            {children}
        </QueryClientProvider>
    );
};

const customRender = (
    ui: ReactElement,
    options?: Omit<RenderOptions, 'wrapper'>
) => render(ui, { wrapper: AllTheProviders, ...options });

// Re-export everything
export * from '@testing-library/react';
export { customRender as render };

// Test utilities
export const mockApiResponse = (data: unknown, status = 200) => {
    return Promise.resolve({
        ok: status >= 200 && status < 300,
        status,
        json: () => Promise.resolve(data),
        text: () => Promise.resolve(JSON.stringify(data)),
    });
};

export const mockApiError = (message: string, status = 500) => {
    return Promise.resolve({
        ok: false,
        status,
        json: () => Promise.resolve({ error: message }),
        text: () => Promise.resolve(JSON.stringify({ error: message })),
    });
};

// Synthetic test data generators
export const generateTestUser = (overrides = {}) => ({
    id: `user-${Date.now()}`,
    email: 'test@example.com',
    name: 'Test User',
    role: 'viewer',
    tenant_id: 'tenant-001',
    created_at: new Date().toISOString(),
    ...overrides,
});

export const generateTestTenant = (overrides = {}) => ({
    id: `tenant-${Date.now()}`,
    name: 'Test Tenant',
    status: 'ACTIVE',
    created_at: new Date().toISOString(),
    ...overrides,
});

export const generateTestAuditLog = (overrides = {}) => ({
    id: `audit-${Date.now()}`,
    user_id: 'user-001',
    action: 'VIEW',
    resource: 'document',
    resource_id: 'doc-001',
    timestamp: new Date().toISOString(),
    ip_address: '127.0.0.1',
    user_agent: 'Test Agent',
    ...overrides,
});
