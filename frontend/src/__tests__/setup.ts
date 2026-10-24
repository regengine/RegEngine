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

// Node >= 25 ships a built-in Web Storage global that is `undefined` unless
// --localstorage-file is passed, and it shadows jsdom's window.localStorage.
// CI runs Node 20 (.nvmrc) and is unaffected; local runs on newer Node broke
// any test touching storage. Restore jsdom's implementations when shadowed.
{
    const dom = (globalThis as { jsdom?: { window: Window } }).jsdom;
    for (const key of ['localStorage', 'sessionStorage'] as const) {
        if (dom && !globalThis[key]) {
            Object.defineProperty(globalThis, key, {
                value: dom.window[key],
                configurable: true,
                writable: true,
            });
        }
    }
}
