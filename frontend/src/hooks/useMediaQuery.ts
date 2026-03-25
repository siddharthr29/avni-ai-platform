import { useState, useEffect } from 'react';

/**
 * Custom hook that listens to a CSS media query and returns whether it matches.
 * Updates reactively when the viewport changes.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQuery = window.matchMedia(query);
    setMatches(mediaQuery.matches);

    const handler = (event: MediaQueryListEvent) => {
      setMatches(event.matches);
    };

    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

/** True when viewport width <= 640px (mobile phones) */
export const useIsMobile = () => useMediaQuery('(max-width: 640px)');

/** True when viewport width <= 1024px (tablets and smaller) */
export const useIsTablet = () => useMediaQuery('(max-width: 1024px)');

/** True when viewport width > 1024px (desktops) */
export const useIsDesktop = () => useMediaQuery('(min-width: 1025px)');

/** True when user prefers reduced motion */
export const usePrefersReducedMotion = () => useMediaQuery('(prefers-reduced-motion: reduce)');
