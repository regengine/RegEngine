import { expect, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
}

vi.stubGlobal('ResizeObserver', ResizeObserverMock)

// Cleanup after each test case
afterEach(() => {
    cleanup()
})

// 'server-only' throws outside the react-server condition; vitest runs every
// module as a client import, so neutralize it for tests.
vi.mock('server-only', () => ({}))

// Mock Next.js router
vi.mock('next/navigation', () => ({
    useRouter: () => ({
        push: vi.fn(),
        replace: vi.fn(),
        prefetch: vi.fn(),
        back: vi.fn(),
    }),
    usePathname: () => '/',
    useSearchParams: () => new URLSearchParams(),
}))

// Mock environment variables
process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8002'
// Existing page tests exercise experimental surfaces (audit, curation,
// inflow-lab, /fsma nav) as if enabled; gate-off behaviour is covered by
// __tests__/pages/experimental-gating.test.tsx via vi.stubEnv.
process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES = 'true'
