import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import {
  Locale,
  defaultLocale,
  getInitialLocale,
  setStoredLocale,
  getDirection,
  localeNames,
  isRTL,
} from '@/lib/i18n';
import { getTranslation, type TranslationKey } from '@/lib/translations';

interface LocaleContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  direction: 'ltr' | 'rtl';
  isRTL: boolean;
  localeName: string;
  t: (key: TranslationKey) => string;
}

const LocaleContext = createContext<LocaleContextType | undefined>(undefined);

interface LocaleProviderProps {
  children: ReactNode;
}

export function LocaleProvider({ children }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(defaultLocale);

  useEffect(() => {
    setLocaleState(getInitialLocale());
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = getDirection(locale);
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    setStoredLocale(newLocale);
  }, []);

  const t = useCallback((key: TranslationKey): string => {
    return getTranslation(locale, key);
  }, [locale]);

  const value: LocaleContextType = {
    locale,
    setLocale,
    direction: getDirection(locale),
    isRTL: isRTL(locale),
    localeName: localeNames[locale],
    t,
  };

  return (
    <LocaleContext.Provider value={value}>
      {children}
    </LocaleContext.Provider>
  );
}

export function useLocale(): LocaleContextType {
  const context = useContext(LocaleContext);
  if (context === undefined) {
    throw new Error('useLocale must be used within a LocaleProvider');
  }
  return context;
}
