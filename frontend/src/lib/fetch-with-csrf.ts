import { CSRF_PROTECTED_METHODS, getCsrfHeaders } from './csrf';

export function withCsrfHeaders(options: RequestInit = {}): RequestInit {
    const method = (options.method || 'GET').toUpperCase();
    if (!CSRF_PROTECTED_METHODS.has(method)) {
        return options;
    }

    const headers = new Headers(options.headers);
    for (const [name, value] of Object.entries(getCsrfHeaders())) {
        headers.set(name, value);
    }

    return {
        ...options,
        headers,
    };
}

export function fetchWithCsrf(input: RequestInfo | URL, options: RequestInit = {}) {
    return fetch(input, withCsrfHeaders(options));
}
