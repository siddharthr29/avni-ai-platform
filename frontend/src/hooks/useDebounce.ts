import { useState, useEffect, useRef, useCallback } from 'react';

/**
 * Debounce a value — delays updating until `delay` ms of inactivity.
 * Use for search inputs to avoid firing on every keystroke.
 */
export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

/**
 * Returns a debounced callback that delays invocation.
 * The callback is stable across renders.
 */
export function useDebouncedCallback<T extends (...args: unknown[]) => unknown>(
  callback: T,
  delay: number,
): (...args: Parameters<T>) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return useCallback((...args: Parameters<T>) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => callbackRef.current(...args), delay);
  }, [delay]);
}

/**
 * Throttle a callback — fires at most once per `interval` ms.
 * Use for scroll, resize, and drag handlers.
 */
export function useThrottledCallback<T extends (...args: unknown[]) => unknown>(
  callback: T,
  interval: number,
): (...args: Parameters<T>) => void {
  const lastCallRef = useRef(0);
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  return useCallback((...args: Parameters<T>) => {
    const now = Date.now();
    if (now - lastCallRef.current >= interval) {
      lastCallRef.current = now;
      callbackRef.current(...args);
    }
  }, [interval]);
}

/**
 * Keyboard shortcut hook — registers a global keyboard shortcut.
 * Automatically cleans up on unmount.
 */
export function useKeyboardShortcut(
  key: string,
  callback: () => void,
  options: { ctrl?: boolean; meta?: boolean; shift?: boolean; disabled?: boolean } = {},
): void {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    if (options.disabled) return;

    const handler = (e: KeyboardEvent) => {
      const modMatch =
        (options.ctrl === undefined && options.meta === undefined) ||
        (options.ctrl && e.ctrlKey) ||
        (options.meta && e.metaKey) ||
        (e.ctrlKey || e.metaKey);

      if (e.key === key && modMatch && (!options.shift || e.shiftKey)) {
        e.preventDefault();
        callbackRef.current();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [key, options.ctrl, options.meta, options.shift, options.disabled]);
}
