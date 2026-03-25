import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { t as translate, getPersistedLocale, persistLocale, SUPPORTED_LOCALES, type Locale } from './index';

interface I18nContextType {
  /** Current active locale */
  locale: Locale;
  /** Translate a key path, with optional interpolation params */
  t: (key: string, params?: Record<string, string>) => string;
  /** Switch the active locale */
  setLocale: (locale: Locale) => void;
  /** All supported locales with display names */
  supportedLocales: typeof SUPPORTED_LOCALES;
}

const I18nContext = createContext<I18nContextType | null>(null);

/**
 * Hook to access translation functions and locale management.
 *
 * @example
 * const { t, locale, setLocale } = useTranslation();
 * <button>{t('common.signIn')}</button>
 */
export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Fallback for components outside the provider — use English
    return {
      locale: 'en' as Locale,
      t: (key: string, params?: Record<string, string>) => translate(key, 'en', params),
      setLocale: () => {},
      supportedLocales: SUPPORTED_LOCALES,
    };
  }
  return ctx;
}

interface I18nProviderProps {
  children: ReactNode;
  /** Override the initial locale (otherwise reads from localStorage) */
  defaultLocale?: Locale;
}

/**
 * I18nProvider — wraps the app to provide translation context.
 *
 * - Reads persisted locale from localStorage on mount
 * - Updates html lang attribute when locale changes
 * - Provides `useTranslation()` hook to all descendants
 */
export function I18nProvider({ children, defaultLocale }: I18nProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(() => defaultLocale ?? getPersistedLocale());

  // Sync html lang attribute on mount and locale change
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    persistLocale(newLocale);
  }, []);

  const t = useCallback(
    (key: string, params?: Record<string, string>) => translate(key, locale, params),
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, t, setLocale, supportedLocales: SUPPORTED_LOCALES }}>
      {children}
    </I18nContext.Provider>
  );
}
