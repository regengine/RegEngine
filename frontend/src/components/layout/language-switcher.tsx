'use client';

import { useState, useRef, useEffect } from 'react';
import { useLocale } from 'next-intl';
import { Globe } from 'lucide-react';

const LOCALES = [
  { code: 'en', label: 'English', flag: '🇺🇸' },
  { code: 'es', label: 'Español', flag: '🇲🇽' },
  { code: 'zh', label: '中文', flag: '🇨🇳' },
  { code: 'vi', label: 'Tiếng Việt', flag: '🇻🇳' },
  { code: 'ar', label: 'العربية', flag: '🇸🇦' },
  { code: 'fr', label: 'Français', flag: '🇫🇷' },
  { code: 'ru', label: 'Русский', flag: '🇷🇺' },
] as const;

export function LanguageSwitcher() {
  const locale = useLocale();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const current = LOCALES.find(l => l.code === locale) || LOCALES[0];

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  function switchLocale(code: string) {
    document.cookie = `NEXT_LOCALE=${code};path=/;max-age=31536000;SameSite=Lax`;
    setOpen(false);
    window.location.reload();
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm
          text-[var(--re-text-secondary)] hover:text-[var(--re-text-primary)]
          hover:bg-[var(--re-surface-elevated)] transition-colors min-h-[36px]"
        aria-label="Change language"
      >
        <Globe className="h-4 w-4" />
        <span className="hidden sm:inline">{current.flag} {current.label}</span>
        <span className="sm:hidden">{current.flag}</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-50 min-w-[160px] rounded-xl
          border border-[var(--re-border-default)] bg-[var(--re-surface-card)]
          shadow-lg overflow-hidden animate-in fade-in slide-in-from-top-1 duration-150">
          {LOCALES.map((l) => (
            <button
              key={l.code}
              onClick={() => switchLocale(l.code)}
              className={`w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm transition-colors
                ${l.code === locale
                  ? 'bg-[var(--re-brand)]/10 text-[var(--re-brand)] font-medium'
                  : 'text-[var(--re-text-secondary)] hover:bg-[var(--re-surface-elevated)] hover:text-[var(--re-text-primary)]'
                }`}
            >
              <span>{l.flag}</span>
              <span>{l.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
