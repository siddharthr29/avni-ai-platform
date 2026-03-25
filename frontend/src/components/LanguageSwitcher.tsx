import { useState, useRef, useEffect } from 'react';
import { Globe } from 'lucide-react';
import { useTranslation } from '../i18n/I18nProvider';
import type { Locale } from '../i18n';

/**
 * LanguageSwitcher — compact dropdown for selecting the UI language.
 *
 * Features:
 * - Shows current language with a globe icon
 * - Dropdown with all supported locales (native script names)
 * - Persists selection to localStorage via the I18n provider
 * - 44px minimum touch targets for mobile accessibility
 * - Keyboard navigable (Enter/Space to open, Escape to close)
 * - Designed for footer or settings area placement
 */
export function LanguageSwitcher() {
  const { locale, setLocale, supportedLocales } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  const handleSelect = (newLocale: Locale) => {
    setLocale(newLocale);
    setIsOpen(false);
  };

  const currentLocale = supportedLocales[locale];
  const localeEntries = Object.entries(supportedLocales) as [Locale, typeof currentLocale][];

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        onClick={() => setIsOpen(prev => !prev)}
        className="
          inline-flex items-center gap-1.5
          min-w-[44px] min-h-[44px]
          px-3 py-2
          text-xs font-medium text-gray-600
          hover:text-gray-900 hover:bg-gray-100
          rounded-lg transition-colors duration-150
          focus:outline-none focus:ring-2 focus:ring-teal-500
        "
        aria-label={`Select language. Current: ${currentLocale.name}`}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <Globe className="w-4 h-4" />
        <span className="hidden sm:inline">{currentLocale.nativeName}</span>
      </button>

      {isOpen && (
        <div
          role="listbox"
          aria-label="Select language"
          className="
            absolute bottom-full mb-1 left-0
            bg-white border border-gray-200
            rounded-lg shadow-lg
            py-1 min-w-[180px]
            z-50
          "
        >
          {localeEntries.map(([code, info]) => (
            <button
              key={code}
              role="option"
              aria-selected={code === locale}
              onClick={() => handleSelect(code)}
              className={`
                w-full flex items-center justify-between
                min-h-[44px] px-4 py-2.5
                text-sm text-left
                transition-colors duration-150
                focus:outline-none focus:bg-teal-50
                ${code === locale
                  ? 'bg-teal-50 text-teal-800 font-medium'
                  : 'text-gray-700 hover:bg-gray-50'
                }
              `}
            >
              <span>{info.nativeName}</span>
              <span className="text-xs text-gray-400 ml-3">{info.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
