'use client';

import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function ThemeToggle() {
    const { theme, setTheme, forcedTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    // next-themes cannot know the resolved theme during SSR, so the documented
    // pattern is to render a placeholder until mount. The flag flip must happen
    // after hydration by definition — that is the point of the guard.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    useEffect(() => setMounted(true), []);

    // A route that forces its theme has nothing to toggle; the control would
    // be a dead button, so it is not rendered there.
    if (forcedTheme) return null;

    if (!mounted) {
        // Render placeholder to avoid layout shift
        return (
            <Button type="button" variant="ghost" size="icon" aria-label="Toggle theme">
                <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Button>
        );
    }

    const isDark = theme === 'dark';

    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setTheme(isDark ? 'light' : 'dark')}
            aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
            title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
        >
            {isDark ? (
                // Sun icon — click to go light
                <Sun className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            ) : (
                // Moon icon — click to go dark
                <Moon className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            )}
        </Button>
    );
}
