/**
 * AesthetiCite Frontend i18n Configuration
 * 
 * Supports 22+ languages covering ~90% of world population
 */

export const locales = [
  'en', 'zh', 'hi', 'es', 'fr', 'ar', 'bn', 'pt', 'ru', 'ur',
  'id', 'de', 'ja', 'sw', 'tr', 'vi', 'it', 'ko', 'th', 'fa',
  'ha', 'pa', 'te', 'mr', 'ta'
] as const;

export type Locale = typeof locales[number];

export const defaultLocale: Locale = 'en';

export const localeNames: Record<Locale, string> = {
  en: 'English',
  zh: '中文',
  hi: 'हिन्दी',
  es: 'Español',
  fr: 'Français',
  ar: 'العربية',
  bn: 'বাংলা',
  pt: 'Português',
  ru: 'Русский',
  ur: 'اردو',
  id: 'Bahasa Indonesia',
  de: 'Deutsch',
  ja: '日本語',
  sw: 'Kiswahili',
  tr: 'Türkçe',
  vi: 'Tiếng Việt',
  it: 'Italiano',
  ko: '한국어',
  th: 'ไทย',
  fa: 'فارسی',
  ha: 'Hausa',
  pa: 'ਪੰਜਾਬੀ',
  te: 'తెలుగు',
  mr: 'मराठी',
  ta: 'தமிழ்',
};

export const rtlLocales: Locale[] = ['ar', 'ur', 'fa', 'ha'];

export function isRTL(locale: Locale): boolean {
  return rtlLocales.includes(locale);
}

export function getDirection(locale: Locale): 'ltr' | 'rtl' {
  return isRTL(locale) ? 'rtl' : 'ltr';
}

export function isValidLocale(locale: string): locale is Locale {
  return locales.includes(locale as Locale);
}

export function normalizeLocale(locale: string | undefined | null): Locale {
  if (!locale) return defaultLocale;
  const base = locale.toLowerCase().split('-')[0];
  return isValidLocale(base) ? base : defaultLocale;
}

export function getBrowserLocale(): Locale {
  if (typeof navigator === 'undefined') return defaultLocale;
  
  const languages = navigator.languages || [navigator.language];
  for (const lang of languages) {
    const normalized = normalizeLocale(lang);
    if (normalized !== defaultLocale || lang.startsWith('en')) {
      return normalized;
    }
  }
  return defaultLocale;
}

export function getStoredLocale(): Locale | null {
  if (typeof localStorage === 'undefined') return null;
  const stored = localStorage.getItem('aestheticite-locale');
  return stored && isValidLocale(stored) ? stored : null;
}

export function setStoredLocale(locale: Locale): void {
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('aestheticite-locale', locale);
  }
}

export function getInitialLocale(): Locale {
  return getStoredLocale() || getBrowserLocale();
}
