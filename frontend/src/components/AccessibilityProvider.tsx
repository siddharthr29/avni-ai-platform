import { createContext, useContext, useState, useEffect, useCallback, useRef, type ReactNode } from 'react';

interface AccessibilityContextType {
  /** Announce a message to screen readers via an aria-live region */
  announce: (message: string, priority?: 'polite' | 'assertive') => void;
  /** Whether the keyboard shortcuts help dialog is open */
  showShortcuts: boolean;
  /** Toggle the keyboard shortcuts help dialog */
  toggleShortcuts: () => void;
}

const AccessibilityContext = createContext<AccessibilityContextType | null>(null);

export function useAccessibility() {
  const ctx = useContext(AccessibilityContext);
  if (!ctx) {
    throw new Error('useAccessibility must be used within <AccessibilityProvider>');
  }
  return ctx;
}

interface AccessibilityProviderProps {
  children: ReactNode;
}

export function AccessibilityProvider({ children }: AccessibilityProviderProps) {
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [politeMessage, setPoliteMessage] = useState('');
  const [assertiveMessage, setAssertiveMessage] = useState('');
  const politeTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const assertiveTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const announce = useCallback((message: string, priority: 'polite' | 'assertive' = 'polite') => {
    if (priority === 'assertive') {
      setAssertiveMessage('');
      clearTimeout(assertiveTimerRef.current);
      // Force re-render so screen readers pick up the change
      requestAnimationFrame(() => {
        setAssertiveMessage(message);
        assertiveTimerRef.current = setTimeout(() => setAssertiveMessage(''), 5000);
      });
    } else {
      setPoliteMessage('');
      clearTimeout(politeTimerRef.current);
      requestAnimationFrame(() => {
        setPoliteMessage(message);
        politeTimerRef.current = setTimeout(() => setPoliteMessage(''), 5000);
      });
    }
  }, []);

  const toggleShortcuts = useCallback(() => {
    setShowShortcuts(prev => !prev);
  }, []);

  // Global keyboard shortcut: ? to open shortcuts help
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }

      if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        toggleShortcuts();
      }

      if (e.key === 'Escape' && showShortcuts) {
        e.preventDefault();
        setShowShortcuts(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showShortcuts, toggleShortcuts]);

  return (
    <AccessibilityContext.Provider value={{ announce, showShortcuts, toggleShortcuts }}>
      {children}

      {/* Screen reader live regions */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {politeMessage}
      </div>
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      >
        {assertiveMessage}
      </div>

      {/* Keyboard Shortcuts Help Dialog */}
      {showShortcuts && (
        <div
          className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/40 backdrop-blur-sm"
          onClick={() => setShowShortcuts(false)}
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-md w-full mx-4 p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Keyboard Shortcuts</h2>
              <button
                onClick={() => setShowShortcuts(false)}
                className="p-2 rounded-lg hover:bg-gray-100 transition-colors text-gray-500 min-w-[44px] min-h-[44px] flex items-center justify-center"
                aria-label="Close shortcuts dialog"
                autoFocus
              >
                <span aria-hidden="true">&times;</span>
              </button>
            </div>

            <div className="space-y-3">
              {[
                { keys: ['?'], description: 'Show this help dialog' },
                { keys: ['Ctrl/Cmd', 'K'], description: 'Focus chat input' },
                { keys: ['Ctrl/Cmd', 'N'], description: 'Start new chat' },
                { keys: ['Esc'], description: 'Close sidebar / dialog' },
                { keys: ['Tab'], description: 'Navigate to next element' },
                { keys: ['Shift', 'Tab'], description: 'Navigate to previous element' },
                { keys: ['Enter'], description: 'Activate focused button' },
              ].map(({ keys, description }) => (
                <div key={description} className="flex items-center justify-between py-1.5">
                  <span className="text-sm text-gray-600">{description}</span>
                  <div className="flex items-center gap-1">
                    {keys.map((key) => (
                      <kbd
                        key={key}
                        className="px-2 py-1 text-xs font-mono bg-gray-100 border border-gray-300 rounded text-gray-700"
                      >
                        {key}
                      </kbd>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <p className="mt-4 text-xs text-gray-400">
              Press <kbd className="px-1 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs">Esc</kbd> to close
            </p>
          </div>
        </div>
      )}
    </AccessibilityContext.Provider>
  );
}
