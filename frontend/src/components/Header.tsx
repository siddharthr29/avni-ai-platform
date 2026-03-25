import { useState, useRef, useEffect } from 'react';
import { Menu, LogOut, Building2, BookOpen, Key, Shield, Info, Settings, ChevronDown, MessageSquare, FileText } from 'lucide-react';
import { AvniLogo } from './AvniLogo';
import { BYOKSettings } from './BYOKSettings';
import type { UserProfile } from '../types';

interface HeaderProps {
  onToggleSidebar: () => void;
  onGoHome?: () => void;
  onOpenDocs?: () => void;
  onOpenAdmin?: () => void;
  onOpenAbout?: () => void;
  profile?: UserProfile | null;
  onLogout?: () => void;
  onUpdateProfile?: (updates: Partial<UserProfile>) => void;
  onToast?: (type: 'success' | 'error' | 'info', message: string) => void;
}

function getInitials(name: string): string {
  return name
    .split(' ')
    .map(w => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();
}

function getSectorIcon(sector?: string): string {
  if (!sector) return '';
  const s = sector.toLowerCase();
  if (s.includes('health')) return '\u2764\uFE0F';
  if (s.includes('education') || s.includes('school')) return '\uD83C\uDF93';
  if (s.includes('water') || s.includes('wash')) return '\uD83D\uDCA7';
  if (s.includes('agriculture') || s.includes('farm')) return '\uD83C\uDF3E';
  if (s.includes('livelihood') || s.includes('finance')) return '\uD83D\uDCB0';
  return '\uD83C\uDFE2';
}

type NavTab = 'chat' | 'srs' | 'docs';

export function Header({ onToggleSidebar, onGoHome, onOpenDocs, onOpenAdmin, onOpenAbout, profile, onLogout, onUpdateProfile, onToast }: HeaderProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [showBYOK, setShowBYOK] = useState(false);
  const [activeTab, setActiveTab] = useState<NavTab>('chat');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setShowBYOK(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleTabClick = (tab: NavTab) => {
    setActiveTab(tab);
    if (tab === 'chat') {
      onGoHome?.();
    } else if (tab === 'srs') {
      // SRS Builder is handled via view state in App
      // Trigger via quick action mechanism
      const event = new CustomEvent('avni-action', { detail: { action: 'open_srs_builder' } });
      window.dispatchEvent(event);
    } else if (tab === 'docs') {
      onOpenDocs?.();
    }
  };

  const navTabs: { key: NavTab; label: string; icon: typeof MessageSquare }[] = [
    { key: 'chat', label: 'Chat', icon: MessageSquare },
    { key: 'srs', label: 'SRS Builder', icon: FileText },
    { key: 'docs', label: 'Docs', icon: BookOpen },
  ];

  const isAdmin = profile && (profile.role === 'platform_admin' || profile.role === 'org_admin');

  return (
    <>
      <header
        className="h-14 border-b border-gray-200 bg-white shadow-sm shrink-0 flex items-center px-3 sm:px-4"
        style={{ '--header-height': '56px' } as React.CSSProperties}
      >
        {/* Left: Hamburger + Logo */}
        <div className="flex items-center gap-1 sm:gap-2">
          <button
            onClick={onToggleSidebar}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
            aria-label="Toggle sidebar"
          >
            <Menu className="w-5 h-5 text-gray-600" />
          </button>

          <button
            onClick={onGoHome}
            className="flex items-center gap-2 rounded-lg hover:bg-gray-50 transition-colors px-1.5 py-1 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
            aria-label="Go to home page"
          >
            <AvniLogo size={26} variant="icon" />
            <span className="text-base font-semibold text-teal-700 hidden sm:inline">Avni AI</span>
          </button>
        </div>

        {/* Center: Navigation Tabs (desktop only) */}
        <nav className="hidden md:flex items-center gap-1 mx-auto" role="tablist">
          {navTabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              role="tab"
              aria-selected={activeTab === key}
              onClick={() => handleTabClick(key)}
              className={`
                flex items-center gap-1.5 px-3.5 py-1.5 text-sm font-medium rounded-lg transition-all duration-200 relative
                focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1
                ${activeTab === key
                  ? 'text-teal-700'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                }
              `}
            >
              <Icon className="w-4 h-4" />
              {label}
              {/* Active tab indicator */}
              {activeTab === key && (
                <span className="absolute bottom-[-9px] left-2 right-2 h-0.5 bg-teal-600 rounded-full" />
              )}
            </button>
          ))}
        </nav>

        {/* Right: Org Badge + Profile */}
        <div className="ml-auto flex items-center gap-2">
          {/* Org context badge — always visible */}
          {profile && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 bg-teal-50 text-teal-700 rounded-full text-xs font-medium max-w-[160px] sm:max-w-[200px]">
              <Building2 className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">{profile.orgName}</span>
              {profile.sector && (
                <span className="shrink-0" title={profile.sector}>{getSectorIcon(profile.sector)}</span>
              )}
            </div>
          )}

          {/* Profile menu */}
          {profile && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => { setMenuOpen(!menuOpen); setShowBYOK(false); }}
                aria-expanded={menuOpen}
                className="flex items-center gap-1.5 px-1.5 py-1 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-1"
              >
                {/* Avatar with initials */}
                <div className="w-8 h-8 bg-teal-100 rounded-full flex items-center justify-center text-xs font-semibold text-teal-700 select-none">
                  {getInitials(profile.name)}
                </div>
                <ChevronDown className={`w-3.5 h-3.5 text-gray-400 hidden sm:block transition-transform duration-200 ${menuOpen ? 'rotate-180' : ''}`} />
              </button>

              {menuOpen && (
                <div className="absolute right-0 top-full mt-1.5 w-72 bg-white rounded-xl shadow-lg border border-gray-200 py-1 z-50 animate-in fade-in slide-in-from-top-1 duration-150">
                  {/* Profile header */}
                  <div className="px-4 py-3 border-b border-gray-100">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 bg-teal-100 rounded-full flex items-center justify-center text-sm font-semibold text-teal-700 shrink-0">
                        {getInitials(profile.name)}
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-gray-900 truncate">{profile.name}</p>
                        <p className="text-xs text-gray-500 truncate">{profile.email || profile.orgName}</p>
                      </div>
                    </div>
                    {profile.orgContext && (
                      <p className="text-xs text-gray-400 mt-2 line-clamp-2">{profile.orgContext}</p>
                    )}
                  </div>

                  {/* Menu items */}
                  <div className="py-1">
                    <button
                      onClick={() => {
                        setMenuOpen(false);
                        onOpenAbout?.();
                      }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      <Settings className="w-4 h-4 text-gray-400" />
                      <span>Settings</span>
                    </button>

                    <button
                      onClick={() => setShowBYOK(!showBYOK)}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      <Key className="w-4 h-4 text-gray-400" />
                      <span>API Keys (BYOK)</span>
                      {profile.byokProvider && (
                        <span className="ml-auto text-xs text-teal-600 font-medium bg-teal-50 px-1.5 py-0.5 rounded">Active</span>
                      )}
                    </button>

                    {showBYOK && onUpdateProfile && (
                      <div className="border-t border-b border-gray-100 bg-gray-50">
                        <BYOKSettings
                          profile={profile}
                          onUpdateProfile={onUpdateProfile}
                          onToast={onToast}
                        />
                      </div>
                    )}

                    {isAdmin && (
                      <button
                        onClick={() => {
                          setMenuOpen(false);
                          onOpenAdmin?.();
                        }}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                      >
                        <Shield className="w-4 h-4 text-gray-400" />
                        <span>Admin Panel</span>
                      </button>
                    )}

                    <button
                      onClick={() => {
                        setMenuOpen(false);
                        onOpenAbout?.();
                      }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      <Info className="w-4 h-4 text-gray-400" />
                      <span>About</span>
                    </button>
                  </div>

                  {/* Logout */}
                  <div className="border-t border-gray-100 py-1">
                    <button
                      onClick={() => {
                        setMenuOpen(false);
                        onLogout?.();
                      }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-600 hover:bg-red-50 transition-colors"
                    >
                      <LogOut className="w-4 h-4" />
                      <span>Sign Out</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Mobile org badge bar — shown below header on small screens */}
      {profile && (
        <div className="flex md:hidden items-center justify-center gap-2 px-3 py-1.5 bg-teal-50 border-b border-teal-100 text-xs text-teal-700 font-medium sm:hidden">
          <Building2 className="w-3 h-3" />
          <span className="truncate max-w-[200px]">{profile.orgName}</span>
          {profile.sector && (
            <>
              <span className="text-teal-300">|</span>
              <span>{profile.sector}</span>
            </>
          )}
        </div>
      )}
    </>
  );
}
