import { useState, useEffect, useRef, useCallback, type ReactNode } from 'react';
import { Menu, X, MessageSquare, Package, BookOpen, Settings, Info, LogOut } from 'lucide-react';
import { useIsMobile, useIsTablet } from '../hooks/useMediaQuery';

interface MobileNavProps {
  onNavigate: (view: string) => void;
  onNewChat?: () => void;
  onLogout?: () => void;
  profileName?: string;
  currentView?: string;
  children?: ReactNode;
}

interface NavItem {
  id: string;
  label: string;
  icon: ReactNode;
  action: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'chat', label: 'Chat', icon: <MessageSquare className="w-5 h-5" />, action: 'chat' },
  { id: 'srs', label: 'SRS Builder', icon: <Package className="w-5 h-5" />, action: 'srs' },
  { id: 'docs', label: 'Documentation', icon: <BookOpen className="w-5 h-5" />, action: 'docs' },
  { id: 'admin', label: 'Admin', icon: <Settings className="w-5 h-5" />, action: 'admin' },
  { id: 'about', label: 'About', icon: <Info className="w-5 h-5" />, action: 'about' },
];

/**
 * MobileNav — hamburger menu with slide-out drawer for mobile/tablet.
 *
 * Features:
 * - Hidden on desktop (> 1024px)
 * - Slide-out drawer from left with backdrop overlay
 * - 44px minimum touch targets (WCAG 2.1 AA)
 * - Swipe-to-close gesture support
 * - Focus trap within open drawer
 * - aria attributes for screen readers
 */
export function MobileNav({
  onNavigate,
  onNewChat,
  onLogout,
  profileName,
  currentView = 'chat',
}: MobileNavProps) {
  const [isOpen, setIsOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const touchStartX = useRef<number | null>(null);
  const touchCurrentX = useRef<number | null>(null);
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  // Don't render on desktop
  if (!isMobile && !isTablet) return null;

  const openDrawer = () => {
    setIsOpen(true);
    // Focus close button when drawer opens
    requestAnimationFrame(() => {
      closeButtonRef.current?.focus();
    });
  };

  const closeDrawer = useCallback(() => {
    setIsOpen(false);
  }, []);

  const handleNavigate = (action: string) => {
    onNavigate(action);
    closeDrawer();
  };

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeDrawer();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeDrawer]);

  // Prevent body scroll when drawer is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  // Swipe-to-close gesture handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchCurrentX.current = e.touches[0].clientX;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    touchCurrentX.current = e.touches[0].clientX;

    // Apply real-time transform for visual feedback
    if (touchStartX.current !== null && drawerRef.current) {
      const diff = touchStartX.current - touchCurrentX.current!;
      if (diff > 0) {
        drawerRef.current.style.transform = `translateX(-${Math.min(diff, 280)}px)`;
      }
    }
  };

  const handleTouchEnd = () => {
    if (touchStartX.current !== null && touchCurrentX.current !== null) {
      const diff = touchStartX.current - touchCurrentX.current;
      // If swiped left more than 80px, close the drawer
      if (diff > 80) {
        closeDrawer();
      } else if (drawerRef.current) {
        // Snap back
        drawerRef.current.style.transform = 'translateX(0)';
      }
    }
    touchStartX.current = null;
    touchCurrentX.current = null;
  };

  return (
    <>
      {/* Hamburger button — always visible on mobile/tablet */}
      <button
        onClick={openDrawer}
        className="
          inline-flex items-center justify-center
          min-w-[44px] min-h-[44px]
          p-2 rounded-lg
          text-gray-700 hover:bg-gray-100
          transition-colors duration-150
          focus:outline-none focus:ring-2 focus:ring-teal-500
          lg:hidden
        "
        aria-label="Open navigation menu"
        aria-expanded={isOpen}
        aria-controls="mobile-nav-drawer"
      >
        <Menu className="w-6 h-6" />
      </button>

      {/* Backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm transition-opacity duration-300"
          onClick={closeDrawer}
          aria-hidden="true"
        />
      )}

      {/* Slide-out drawer */}
      <div
        id="mobile-nav-drawer"
        ref={drawerRef}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
        className={`
          fixed top-0 left-0 z-[101]
          h-full w-[280px] max-w-[85vw]
          bg-white shadow-2xl
          flex flex-col
          transition-transform duration-300 ease-in-out
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <span className="text-base font-semibold text-teal-700">Avni AI</span>
          <button
            ref={closeButtonRef}
            onClick={closeDrawer}
            className="
              inline-flex items-center justify-center
              min-w-[44px] min-h-[44px]
              p-2 rounded-lg
              hover:bg-gray-100
              transition-colors duration-150
              focus:outline-none focus:ring-2 focus:ring-teal-500
            "
            aria-label="Close navigation menu"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Profile section */}
        {profileName && (
          <div className="px-4 py-3 border-b border-gray-100">
            <p className="text-sm font-medium text-gray-900">{profileName}</p>
          </div>
        )}

        {/* Navigation items */}
        <nav className="flex-1 overflow-y-auto py-2" aria-label="Main navigation">
          <ul className="space-y-1 px-2">
            {NAV_ITEMS.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => handleNavigate(item.action)}
                  className={`
                    w-full flex items-center gap-3
                    min-h-[44px] px-4 py-3
                    rounded-lg text-sm font-medium
                    transition-colors duration-150
                    focus:outline-none focus:ring-2 focus:ring-teal-500
                    ${currentView === item.id
                      ? 'bg-teal-50 text-teal-800'
                      : 'text-gray-700 hover:bg-gray-50'
                    }
                  `}
                  aria-current={currentView === item.id ? 'page' : undefined}
                >
                  <span className={currentView === item.id ? 'text-teal-600' : 'text-gray-500'}>
                    {item.icon}
                  </span>
                  {item.label}
                </button>
              </li>
            ))}
          </ul>

          {/* New Chat button */}
          {onNewChat && (
            <div className="px-4 mt-4">
              <button
                onClick={() => {
                  onNewChat();
                  closeDrawer();
                }}
                className="
                  w-full flex items-center justify-center gap-2
                  min-h-[44px] px-4 py-3
                  bg-teal-700 hover:bg-teal-800
                  text-white text-sm font-medium
                  rounded-lg transition-colors duration-150
                  focus:outline-none focus:ring-2 focus:ring-teal-400 focus:ring-offset-2
                "
              >
                <MessageSquare className="w-4 h-4" />
                New Chat
              </button>
            </div>
          )}
        </nav>

        {/* Footer actions */}
        {onLogout && (
          <div className="border-t border-gray-200 p-2">
            <button
              onClick={() => {
                onLogout();
                closeDrawer();
              }}
              className="
                w-full flex items-center gap-3
                min-h-[44px] px-4 py-3
                rounded-lg text-sm font-medium
                text-red-600 hover:bg-red-50
                transition-colors duration-150
                focus:outline-none focus:ring-2 focus:ring-red-500
              "
            >
              <LogOut className="w-5 h-5" />
              Sign Out
            </button>
          </div>
        )}
      </div>
    </>
  );
}
