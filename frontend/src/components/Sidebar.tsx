import { useState, useMemo, memo, useCallback } from 'react';
import { PenSquare, MessageSquare, Package, MessageCircle, Mic, ImageIcon, HelpCircle, X, Trash2, Search, Calendar, ChevronDown, ChevronUp } from 'lucide-react';
import clsx from 'clsx';
import { useDebounce } from '../hooks/useDebounce';
import type { Session } from '../types';

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  isOpen: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onClose: () => void;
  onQuickAction: (action: string) => void;
}

type DateGroup = 'Today' | 'Yesterday' | 'Previous 7 Days' | 'Older';

function getDateGroup(date: Date): DateGroup {
  const now = new Date();
  const d = new Date(date);
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday.getTime() - 86400000);
  const startOf7DaysAgo = new Date(startOfToday.getTime() - 7 * 86400000);

  if (d >= startOfToday) return 'Today';
  if (d >= startOfYesterday) return 'Yesterday';
  if (d >= startOf7DaysAgo) return 'Previous 7 Days';
  return 'Older';
}

function formatTimestamp(date: Date): string {
  const d = new Date(date);
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
}

function groupSessions(sessions: Session[]): { group: DateGroup; sessions: Session[] }[] {
  const groups: Record<DateGroup, Session[]> = {
    'Today': [],
    'Yesterday': [],
    'Previous 7 Days': [],
    'Older': [],
  };

  for (const session of sessions) {
    const group = getDateGroup(session.createdAt);
    groups[group].push(session);
  }

  const order: DateGroup[] = ['Today', 'Yesterday', 'Previous 7 Days', 'Older'];
  return order
    .filter(g => groups[g].length > 0)
    .map(g => ({ group: g, sessions: groups[g] }));
}

function getStatusColor(session: Session): string {
  if (session.messages.length === 0) return 'bg-gray-300';
  const lastMsg = session.messages[session.messages.length - 1];
  if (lastMsg.metadata?.type === 'error') return 'bg-red-400';
  if (lastMsg.role === 'assistant') return 'bg-teal-500';
  return 'bg-amber-400';
}

// Memoized session list item to avoid re-renders when other sessions change
const SessionItem = memo(function SessionItem({
  session,
  isActive,
  onSelect,
  onDelete,
}: {
  session: Session;
  isActive: boolean;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div
      className={clsx(
        'group relative rounded-lg transition-all duration-150',
        isActive
          ? 'bg-teal-50 border-l-[3px] border-l-teal-600'
          : 'hover:bg-gray-50 border-l-[3px] border-l-transparent'
      )}
    >
      <button
        onClick={() => onSelect(session.id)}
        className="w-full text-left px-3 py-2.5 focus:outline-none"
      >
        <div className="flex items-start gap-2.5 pr-7">
          <div className="flex items-center gap-2 min-w-0 flex-1">
            <div
              className={clsx(
                'w-1.5 h-1.5 rounded-full shrink-0 mt-1.5',
                getStatusColor(session)
              )}
              title="Session status"
            />
            <div className="min-w-0 flex-1">
              <p className={clsx(
                'text-sm truncate',
                isActive ? 'font-semibold text-teal-900' : 'font-medium text-gray-700'
              )}>
                {session.title}
              </p>
              <p className={clsx(
                'text-xs mt-0.5',
                isActive ? 'text-teal-600' : 'text-gray-400'
              )}>
                {formatTimestamp(session.createdAt)}
                {session.messages.length > 0 && ` \u00b7 ${session.messages.length} msgs`}
              </p>
            </div>
          </div>
        </div>
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
        className={clsx(
          'absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md transition-all duration-150',
          'hover:bg-red-100 text-gray-400 hover:text-red-500',
          '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100',
          'opacity-60'
        )}
        aria-label="Delete session"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
});

export function Sidebar({
  sessions,
  currentSessionId,
  isOpen,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onClose,
  onQuickAction,
}: SidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [showDateFilter, setShowDateFilter] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const debouncedQuery = useDebounce(searchQuery, 200);

  const filteredSessions = useMemo(() => {
    let result = sessions;

    // Text search — matches title AND message content
    if (debouncedQuery.trim()) {
      const q = debouncedQuery.toLowerCase();
      result = result.filter(s => {
        if (s.title.toLowerCase().includes(q)) return true;
        // Search in message content
        return s.messages.some(m => m.content.toLowerCase().includes(q));
      });
    }

    // Date range filter
    if (dateFrom) {
      const from = new Date(dateFrom);
      from.setHours(0, 0, 0, 0);
      result = result.filter(s => new Date(s.createdAt) >= from);
    }
    if (dateTo) {
      const to = new Date(dateTo);
      to.setHours(23, 59, 59, 999);
      result = result.filter(s => new Date(s.createdAt) <= to);
    }

    return result;
  }, [sessions, debouncedQuery, dateFrom, dateTo]);

  const hasActiveFilters = debouncedQuery.trim() || dateFrom || dateTo;

  const clearAllFilters = useCallback(() => {
    setSearchQuery('');
    setDateFrom('');
    setDateTo('');
    setShowDateFilter(false);
  }, []);

  const groupedSessions = useMemo(() => groupSessions(filteredSessions), [filteredSessions]);

  const handleSelectSession = (sessionId: string) => {
    onSelectSession(sessionId);
    // Close sidebar on mobile
    if (window.innerWidth < 768) {
      onClose();
    }
  };

  const quickActions = [
    { label: 'Generate Bundle', icon: Package, action: 'Generate Bundle' },
    { label: 'Chat Builder', icon: MessageCircle, action: 'Chat Builder' },
    { label: 'Voice Capture', icon: Mic, action: 'Voice Capture' },
    { label: 'Upload Image', icon: ImageIcon, action: 'Upload Image' },
    { label: 'Get Help', icon: HelpCircle, action: 'Get Help' },
  ] as const;

  return (
    <>
      {/* Backdrop for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 md:hidden backdrop-blur-sm transition-opacity duration-300"
          onClick={onClose}
        />
      )}

      <aside
        className={clsx(
          'fixed md:relative z-50 md:z-auto h-full w-[280px] bg-white border-r border-gray-200 flex flex-col transition-transform duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0 md:hidden'
        )}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between p-4 md:hidden">
          <span className="text-base font-semibold text-teal-700">Avni AI</span>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-3 pt-3 md:pt-4">
          <button
            onClick={onNewChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-teal-700 hover:bg-teal-800 text-white rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:ring-offset-2 font-medium text-sm active:scale-[0.98] shadow-sm"
          >
            <PenSquare className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Search + Date Filter */}
        <div className="px-3 pb-2 space-y-1.5">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search titles & messages..."
              className="w-full pl-9 pr-16 py-2 text-sm bg-gray-100 rounded-lg text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:bg-white transition-all duration-200 border border-transparent focus:border-teal-500"
            />
            <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="p-1 rounded hover:bg-gray-200 transition-colors"
                  aria-label="Clear search"
                >
                  <X className="w-3.5 h-3.5 text-gray-400" />
                </button>
              )}
              <button
                onClick={() => setShowDateFilter(prev => !prev)}
                className={clsx(
                  'p-1 rounded transition-colors',
                  showDateFilter || dateFrom || dateTo
                    ? 'bg-teal-100 text-teal-600'
                    : 'hover:bg-gray-200 text-gray-400'
                )}
                aria-label="Toggle date filter"
                title="Filter by date"
              >
                <Calendar className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Date range filter */}
          {showDateFilter && (
            <div className="flex items-center gap-1.5 px-0.5">
              <input
                type="date"
                value={dateFrom}
                onChange={e => setDateFrom(e.target.value)}
                className="flex-1 px-2 py-1.5 text-xs bg-gray-100 rounded-md text-gray-700 focus:outline-none focus:ring-1 focus:ring-teal-500 border border-transparent focus:border-teal-500"
                title="From date"
              />
              <span className="text-xs text-gray-400">to</span>
              <input
                type="date"
                value={dateTo}
                onChange={e => setDateTo(e.target.value)}
                className="flex-1 px-2 py-1.5 text-xs bg-gray-100 rounded-md text-gray-700 focus:outline-none focus:ring-1 focus:ring-teal-500 border border-transparent focus:border-teal-500"
                title="To date"
              />
            </div>
          )}

          {/* Active filters indicator */}
          {hasActiveFilters && (
            <div className="flex items-center justify-between px-1">
              <span className="text-xs text-teal-600 font-medium">
                {filteredSessions.length} result{filteredSessions.length !== 1 ? 's' : ''}
              </span>
              <button
                onClick={clearAllFilters}
                className="text-xs text-gray-400 hover:text-red-500 transition-colors"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>

        {/* Session List */}
        {/* TODO: Virtualize with react-window when session count exceeds 100+ for scroll performance */}
        <div className="flex-1 overflow-y-auto px-3 pb-2">
          {sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <MessageSquare className="w-8 h-8 text-gray-300 mb-3" />
              <p className="text-sm text-gray-400">No conversations yet</p>
              <p className="text-xs text-gray-300 mt-1">Start a new chat to begin</p>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Search className="w-8 h-8 text-gray-300 mb-3" />
              <p className="text-sm text-gray-400">No matching chats</p>
            </div>
          ) : (
            <div className="space-y-4">
              {groupedSessions.map(({ group, sessions: groupSessions }) => (
                <div key={group}>
                  <p className="text-xs font-medium text-gray-400 uppercase tracking-wider px-2 mb-1.5">
                    {group}
                  </p>
                  <div className="space-y-0.5">
                    {groupSessions.map(session => (
                      <SessionItem
                        key={session.id}
                        session={session}
                        isActive={session.id === currentSessionId}
                        onSelect={handleSelectSession}
                        onDelete={onDeleteSession}
                      />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="h-px bg-gray-200 mx-3" />

        {/* Quick Actions */}
        <div className="p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider px-1 mb-2">Quick Actions</p>
          <div className="grid grid-cols-2 gap-1.5">
            {quickActions.map(({ label, icon: Icon, action }) => (
              <button
                key={action}
                onClick={() => onQuickAction(action)}
                className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-teal-500 active:scale-[0.97]"
              >
                <Icon className="w-3.5 h-3.5 text-teal-600 shrink-0" />
                <span className="truncate">{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Session count footer */}
        {sessions.length > 0 && (
          <div className="px-4 py-2 border-t border-gray-200">
            <p className="text-xs text-gray-400 text-center">
              {sessions.length} conversation{sessions.length !== 1 ? 's' : ''}
            </p>
          </div>
        )}
      </aside>
    </>
  );
}
