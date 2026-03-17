import { defineRouting } from 'next-intl/routing';

export const locales = ['en', 'es', 'zh', 'vi', 'ar', 'fr', 'ru'] as const;
export type Locale = (typeof locales)[number];

export const localeNames: Record<Locale, string> = {
  en: 'English',
  es: 'Español',
  zh: '中文',
  vi: 'Tiếng Việt',
  ar: 'العربية',
  fr: 'Français',
  ru: 'Русский',
};

export const routing = defineRouting({
  locales,
  defaultLocale: 'en',
  localePrefix: 'as-needed',
});
