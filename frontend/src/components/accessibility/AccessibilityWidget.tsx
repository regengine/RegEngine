'use client';

import { useState, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';

interface A11ySettings {
  fontSize: 'default' | 'large' | 'xl';
  dyslexicFont: boolean;
  highContrast: boolean;
  reducedMotion: boolean;
  lineHeight: boolean;
  letterSpacing: boolean;
  focusHighlight: boolean;
  cursorLarge: boolean;
}

const STORAGE_KEY = 're-a11y-settings';

const defaultSettings: A11ySettings = {
  fontSize: 'default',
  dyslexicFont: false,
  highContrast: false,
  reducedMotion: false,
  lineHeight: false,
  letterSpacing: false,
  focusHighlight: false,
  cursorLarge: false,
};

function loadSettings(): A11ySettings {
  if (typeof window === 'undefined') return defaultSettings;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return { ...defaultSettings, ...JSON.parse(stored) };
  } catch {}
  return defaultSettings;
}

let dyslexicFontLoaded = false;

function loadOpenDyslexicFont() {
  if (dyslexicFontLoaded) return;
  const linkId = 're-opendyslexic-font';
  if (document.getElementById(linkId)) {
    dyslexicFontLoaded = true;
    return;
  }
  const link = document.createElement('link');
  link.id = linkId;
  link.rel = 'stylesheet';
  link.href = 'https://fonts.cdnfonts.com/css/opendyslexic';
  link.onload = () => { dyslexicFontLoaded = true; };
  link.onerror = () => { link.remove(); };
  document.head.appendChild(link);
}

function applySettings(s: A11ySettings) {
  const html = document.documentElement;
  html.classList.toggle('a11y-font-large', s.fontSize === 'large');
  html.classList.toggle('a11y-font-xl', s.fontSize === 'xl');
  if (s.dyslexicFont) loadOpenDyslexicFont();
  html.classList.toggle('a11y-dyslexic', s.dyslexicFont);
  html.classList.toggle('a11y-high-contrast', s.highContrast);
  html.classList.toggle('a11y-reduced-motion', s.reducedMotion);
  html.classList.toggle('a11y-line-height', s.lineHeight);
  html.classList.toggle('a11y-letter-spacing', s.letterSpacing);
  html.classList.toggle('a11y-focus-highlight', s.focusHighlight);
  html.classList.toggle('a11y-cursor-large', s.cursorLarge);
}

/* ─── Reusable sub-components ─── */

function Toggle({ label, description, checked, onChange, id }: {
  label: string; description?: string; checked: boolean;
  onChange: (v: boolean) => void; id: string;
}) {
  return (
    <div className="flex items-center justify-between py-3 px-5">
      <label htmlFor={id} className="flex-1 cursor-pointer">
        <span className="block text-ui font-medium text-re-text-primary">{label}</span>
        {description && <span className="mt-0.5 block text-small text-re-text-tertiary">{description}</span>}
      </label>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 motion-reduce:transition-none",
          checked ? "bg-re-brand" : "bg-re-border-strong",
        )}
      >
        <span
          aria-hidden="true"
          className="mt-0.5 inline-block h-5 w-5 transform rounded-full bg-re-surface-card transition-transform duration-120 motion-reduce:transition-none"
          style={{ transform: checked ? 'translateX(20px)' : 'translateX(2px)' }}
        />
      </button>
    </div>
  );
}

function FontSizeSelector({ value, onChange }: {
  value: 'default' | 'large' | 'xl'; onChange: (v: 'default' | 'large' | 'xl') => void;
}) {
  const options: { val: 'default' | 'large' | 'xl'; label: string; size: string }[] = [
    { val: 'default', label: 'A', size: '14px' },
    { val: 'large', label: 'A', size: '18px' },
    { val: 'xl', label: 'A', size: '22px' },
  ];
  return (
    <div className="py-3 px-5">
      <span className="mb-2 block text-ui font-medium text-re-text-primary">Text Size</span>
      <div className="flex gap-2" role="radiogroup" aria-label="Text size">
        {options.map(o => (
          <button
            key={o.val}
            role="radio"
            aria-checked={value === o.val}
            aria-label={`Font size ${o.val}`}
            onClick={() => onChange(o.val)}
            className={cn(
              "flex-1 rounded-md border-2 py-2 text-center font-semibold transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 motion-reduce:transition-none",
              value === o.val
                ? "border-re-brand bg-re-brand text-re-brand-foreground"
                : "border-re-border bg-re-surface-card text-re-text-secondary hover:border-re-border-strong",
            )}
            style={{ fontSize: o.size }} // design-lint-disable — this control previews a text size; the size IS the content
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/* ─── Main Widget ─── */

export function AccessibilityWidget() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<A11ySettings>(defaultSettings);
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Reads persisted a11y preferences from localStorage and applies them to the
  // document. Both are browser-only, so they cannot run during render or SSR —
  // and `mounted` gates the hydration-sensitive markup below.
  useEffect(() => {
    const loaded = loadSettings();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSettings(loaded);
    applySettings(loaded);
    setMounted(true);
  }, []);

  useEffect(() => {
    const handler = (event: Event) => {
      const { open: menuOpen } = (event as CustomEvent<{ open?: boolean }>).detail ?? {};
      setMobileMenuOpen(Boolean(menuOpen));
      if (menuOpen) {
        setOpen(false);
      }
    };

    window.addEventListener('re:mobile-menu-state', handler);
    return () => window.removeEventListener('re:mobile-menu-state', handler);
  }, []);

  /* Close on Escape */
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open]);

  const update = useCallback((patch: Partial<A11ySettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...patch };
      applySettings(next);
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(next)); } catch {}
      return next;
    });
  }, []);

  const resetAll = useCallback(() => {
    update(defaultSettings);
  }, [update]);

  if (!mounted || mobileMenuOpen) return null;

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(defaultSettings);

  return (
    <>
      {/* FAB Button */}
      <button
        onClick={() => setOpen(!open)}
        aria-label={open ? 'Close accessibility settings' : 'Open accessibility settings'}
        aria-expanded={open}
        // Below md the dashboard shell pins a 56px tab bar to the bottom edge,
        // so the launcher has to clear it or it lands on the first tab.
        className="re-a11y-fab fixed bottom-[calc(3.5rem+env(safe-area-inset-bottom,0px)+1rem)] right-4 z-[var(--re-z-toast)] flex h-12 w-12 items-center justify-center rounded-full border border-re-brand-dark bg-re-brand text-re-brand-foreground transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 motion-reduce:transition-none md:bottom-6 md:right-6"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="4.5" r="2.5"/>
          <path d="M12 7v4m0 0l-4 7m4-7l4 7"/>
          <path d="M7 11.5h10"/>
        </svg>
      </button>

      {/* Panel */}
      {open && (
        <div
          role="dialog"
          aria-label="Accessibility Settings"
          aria-modal="false"
          // Sits directly above the launcher, which itself clears the mobile
          // tab bar. Elevation is surface-step + border, not a drop shadow.
          className="re-a11y-panel fixed bottom-[calc(3.5rem+env(safe-area-inset-bottom,0px)+4.5rem)] right-4 z-[var(--re-z-toast)] max-h-[70vh] w-[min(20rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-re-border bg-re-surface-elevated md:bottom-20 md:right-6 md:max-h-[80vh]"
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-re-border-subtle px-5 pb-3 pt-5">
            <div>
              <h2 className="text-subheading text-re-text-primary">Accessibility</h2>
              <p className="mt-0.5 text-small text-re-text-tertiary">Customize your experience</p>
            </div>
            {hasChanges && (
              <button
                onClick={resetAll}
                className="rounded-md px-2 py-1 text-small font-medium text-re-text-secondary transition-colors duration-120 hover:bg-re-surface-inset hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring/25 motion-reduce:transition-none"
              >
                Reset All
              </button>
            )}
          </div>

          {/* Controls */}
          <div className="border-b border-re-border-subtle py-2">
            <div className="px-5 pb-1 pt-3">
              <span className="text-label uppercase text-re-text-muted">Vision</span>
            </div>
            <FontSizeSelector value={settings.fontSize} onChange={v => update({ fontSize: v })} />
            <Toggle id="a11y-dyslexic" label="Dyslexia-Friendly Font" description="Switch to OpenDyslexic typeface"
              checked={settings.dyslexicFont} onChange={v => update({ dyslexicFont: v })} />
            <Toggle id="a11y-contrast" label="High Contrast" description="Increase contrast for better readability"
              checked={settings.highContrast} onChange={v => update({ highContrast: v })} />
            <Toggle id="a11y-line-height" label="Increased Line Spacing" description="More space between lines of text"
              checked={settings.lineHeight} onChange={v => update({ lineHeight: v })} />
            <Toggle id="a11y-letter-spacing" label="Increased Letter Spacing" description="More space between characters"
              checked={settings.letterSpacing} onChange={v => update({ letterSpacing: v })} />
          </div>

          <div className="py-2">
            <div className="px-5 pb-1 pt-3">
              <span className="text-label uppercase text-re-text-muted">Motor &amp; Navigation</span>
            </div>
            <Toggle id="a11y-reduced-motion" label="Reduce Motion" description="Minimize animations and transitions"
              checked={settings.reducedMotion} onChange={v => update({ reducedMotion: v })} />
            <Toggle id="a11y-focus" label="Enhanced Focus Indicators" description="Larger, more visible focus outlines"
              checked={settings.focusHighlight} onChange={v => update({ focusHighlight: v })} />
            <Toggle id="a11y-cursor" label="Large Cursor" description="Increase pointer size for easier tracking"
              checked={settings.cursorLarge} onChange={v => update({ cursorLarge: v })} />
          </div>

          {/* Footer */}
          <div className="border-t border-re-border-subtle px-5 py-3 text-center">
            <p className="text-label text-re-text-muted">
              Settings are saved locally and persist across visits.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
