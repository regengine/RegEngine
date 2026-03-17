import { getRequestConfig } from 'next-intl/server';
import { cookies, headers } from 'next/headers';

const SUPPORTED_LOCALES = ['en', 'es', 'zh', 'vi', 'ar', 'fr', 'ru'];
const DEFAULT_LOCALE = 'en';

export default getRequestConfig(async () => {
  // 1. Check cookie (set by language switcher)
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get('NEXT_LOCALE')?.value;
  if (cookieLocale && SUPPORTED_LOCALES.includes(cookieLocale)) {
    return {
      locale: cookieLocale,
      messages: (await import(`../../messages/${cookieLocale}.json`)).default,
    };
  }

  // 2. Fall back to Accept-Language header
  const headerStore = await headers();
  const acceptLang = headerStore.get('accept-language') || '';
  const browserLocale = acceptLang
    .split(',')
    .map(l => l.split(';')[0].trim().substring(0, 2))
    .find(l => SUPPORTED_LOCALES.includes(l));

  const locale = browserLocale || DEFAULT_LOCALE;
  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
