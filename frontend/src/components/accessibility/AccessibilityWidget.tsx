'use client';

import { useState, useEffect, useCallback } from 'react';

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

function applySettings(s: A11ySettings) {
  const html = document.documentElement;
  html.classList.toggle('a11y-font-large', s.fontSize === 'large');
  html.classList.toggle('a11y-font-xl', s.fontSize === 'xl');
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
        <span className="text-sm font-medium block" style={{ color: 'var(--re-text-primary)' }}>{label}</span>
        {description && <span className="text-xs block mt-0.5" style={{ color: 'var(--re-text-muted)' }}>{description}</span>}
      </label>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className="relative inline-flex h-6 w-11 shrink-0 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2"
        style={{
          background: checked ? 'var(--re-brand)' : 'var(--re-surface-border)',
          focusRingColor: 'var(--re-brand)',
        }}
      >
        <span
          aria-hidden="true"
          className="inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform"
          style={{ transform: checked ? 'translateX(20px)' : 'translateX(2px)', marginTop: '2px' }}
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
      <span className="text-sm font-medium block mb-2" style={{ color: 'var(--re-text-primary)' }}>Text Size</span>
      <div className="flex gap-2" role="radiogroup" aria-label="Text size">
        {options.map(o => (
          <button
            key={o.val}
            role="radio"
            aria-checked={value === o.val}
            aria-label={`Font size ${o.val}`}
            onClick={() => onChange(o.val)}
            className="flex-1 py-2 rounded-lg text-center font-semibold transition-all focus:outline-none focus:ring-2"
            style={{
              fontSize: o.size,
              background: value === o.val ? 'var(--re-brand)' : 'var(--re-surface-elevated)',
              color: value === o.val ? '#fff' : 'var(--re-text-secondary)',
              border: value === o.val ? '2px solid var(--re-brand)' : '2px solid var(--re-surface-border)',
            }}
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

  useEffect(() => {
    const loaded = loadSettings();
    setSettings(loaded);
    applySettings(loaded);
    setMounted(true);
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

  if (!mounted) return null;

  const hasChanges = JSON.stringify(settings) !== JSON.stringify(defaultSettings);

  return (
    <>
      {/* FAB Button */}
      <button
        onClick={() => setOpen(!open)}
        aria-label={open ? 'Close accessibility settings' : 'Open accessibility settings'}
        aria-expanded={open}
        className="fixed bottom-6 right-6 z-[9999] w-12 h-12 rounded-full flex items-center justify-center transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2"
        style={{
          background: 'var(--re-brand)',
          color: '#fff',
          boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
        }}
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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
          className="fixed bottom-20 right-6 z-[9999] w-80 max-h-[80vh] overflow-y-auto rounded-2xl"
          style={{
            background: 'var(--re-surface-base)',
            border: '1px solid var(--re-surface-border)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.25)',
          }}
        >
          {/* Header */}
          <div className="px-5 pt-5 pb-3 flex items-center justify-between" style={{ borderBottom: '1px solid var(--re-surface-border)' }}>
            <div>
              <h2 className="text-base font-semibold" style={{ color: 'var(--re-text-primary)' }}>Accessibility</h2>
              <p className="text-xs mt-0.5" style={{ color: 'var(--re-text-muted)' }}>Customize your experience</p>
            </div>
            {hasChanges && (
              <button onClick={resetAll} className="text-xs font-medium px-2 py-1 rounded" style={{ color: 'var(--re-brand)', background: 'var(--re-brand-muted)' }}>
                Reset All
              </button>
            )}
          </div>

          {/* Controls */}
          <div className="py-2" style={{ borderBottom: '1px solid var(--re-surface-border)' }}>
            <div className="px-5 pt-3 pb-1">
              <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--re-text-muted)' }}>Vision</span>
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
            <div className="px-5 pt-3 pb-1">
              <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: 'var(--re-text-muted)' }}>Motor &amp; Navigation</span>
            </div>
            <Toggle id="a11y-reduced-motion" label="Reduce Motion" description="Minimize animations and transitions"
              checked={settings.reducedMotion} onChange={v => update({ reducedMotion: v })} />
            <Toggle id="a11y-focus" label="Enhanced Focus Indicators" description="Larger, more visible focus outlines"
              checked={settings.focusHighlight} onChange={v => update({ focusHighlight: v })} />
            <Toggle id="a11y-cursor" label="Large Cursor" description="Increase pointer size for easier tracking"
              checked={settings.cursorLarge} onChange={v => update({ cursorLarge: v })} />
          </div>

          {/* Footer */}
          <div className="px-5 py-3 text-center" style={{ borderTop: '1px solid var(--re-surface-border)' }}>
            <p className="text-[10px]" style={{ color: 'var(--re-text-muted)' }}>
              Settings are saved locally and persist across visits.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
