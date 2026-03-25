import en from './locales/en.json';
import hi from './locales/hi.json';
import ta from './locales/ta.json';
import te from './locales/te.json';
import kn from './locales/kn.json';
import bn from './locales/bn.json';

/**
 * Supported locales and their display names.
 */
export const SUPPORTED_LOCALES = {
  en: { name: 'English', nativeName: 'English' },
  hi: { name: 'Hindi', nativeName: 'हिन्दी' },
  ta: { name: 'Tamil', nativeName: 'தமிழ்' },
  te: { name: 'Telugu', nativeName: 'తెలుగు' },
  kn: { name: 'Kannada', nativeName: 'ಕನ್ನಡ' },
  bn: { name: 'Bengali', nativeName: 'বাংলা' },
} as const;

export type Locale = keyof typeof SUPPORTED_LOCALES;

/** All loaded translation bundles. */
const translations: Record<string, Record<string, unknown>> = {
  en,
  hi,
  ta,
  te,
  kn,
  bn,
};

/**
 * Resolve a dot-separated key path (e.g. "common.signIn") from a translation bundle.
 * Returns `undefined` if the path doesn't exist.
 */
function resolvePath(obj: Record<string, unknown>, path: string): string | undefined {
  const parts = path.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === 'string' ? current : undefined;
}

/**
 * Get a translated string by key path. Falls back to English if the key
 * is not found in the requested locale.
 *
 * Supports simple interpolation: `{name}` placeholders are replaced with
 * values from the `params` object.
 *
 * @example
 * t('common.signIn', 'en')        // "Sign In"
 * t('emptyState.hello', 'hi', { name: 'Amit' })  // "नमस्ते, Amit!"
 */
export function t(key: string, locale: Locale = 'en', params?: Record<string, string>): string {
  const bundle = translations[locale] ?? translations.en;
  let value = resolvePath(bundle, key);

  // Fallback to English
  if (value === undefined && locale !== 'en') {
    value = resolvePath(translations.en, key);
  }

  // Final fallback: return the key itself
  if (value === undefined) {
    return key;
  }

  // Interpolate {placeholder} patterns
  if (params) {
    for (const [paramKey, paramValue] of Object.entries(params)) {
      value = value.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), paramValue);
    }
  }

  return value;
}

const LOCALE_STORAGE_KEY = 'avni-ai-locale';

/** Read the persisted locale from localStorage, defaulting to 'en'. */
export function getPersistedLocale(): Locale {
  if (typeof window === 'undefined') return 'en';
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (stored && stored in SUPPORTED_LOCALES) {
    return stored as Locale;
  }
  return 'en';
}

/** Persist the selected locale to localStorage. */
export function persistLocale(locale: Locale): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  // Update the html lang attribute
  document.documentElement.lang = locale;
}
