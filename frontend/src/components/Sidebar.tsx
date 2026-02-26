import { Plus, MessageSquare, Package, Mic, ImageIcon, HelpCircle, X } from 'lucide-react';
import clsx from 'clsx';
import type { Session } from '../types';

interface SidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  isOpen: boolean;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onClose: () => void;
  onQuickAction: (action: string) => void;
}

function formatDate(date: Date): string {
  const now = new Date();
  const d = new Date(date);
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
}

export function Sidebar({
  sessions,
  currentSessionId,
  isOpen,
  onNewChat,
  onSelectSession,
  onClose,
  onQuickAction,
}: SidebarProps) {
  return (
    <>
      {/* Backdrop for mobile */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 md:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={clsx(
          'fixed md:relative z-50 md:z-auto h-full w-[280px] bg-gray-50 border-r border-gray-200 flex flex-col transition-transform duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0 md:hidden'
        )}
      >
        {/* Mobile close button */}
        <div className="flex items-center justify-between p-3 md:hidden">
          <span className="font-semibold text-gray-900">Avni AI</span>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-200 transition-colors"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5 text-gray-600" />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="p-3">
          <button
            onClick={onNewChat}
            className="w-full flex items-center gap-2 px-4 py-2.5 bg-primary-600 hover:bg-primary-700 text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 font-medium text-sm"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Quick Actions */}
        <div className="px-3 pb-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider px-1 mb-2">Quick Actions</p>
          <div className="grid grid-cols-2 gap-1.5">
            <button
              onClick={() => onQuickAction('Generate Bundle')}
              className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-700 hover:bg-gray-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <Package className="w-3.5 h-3.5 text-primary-600" />
              Bundle
            </button>
            <button
              onClick={() => onQuickAction('Voice Capture')}
              className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-700 hover:bg-gray-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <Mic className="w-3.5 h-3.5 text-primary-600" />
              Voice
            </button>
            <button
              onClick={() => onQuickAction('Upload Image')}
              className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-700 hover:bg-gray-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <ImageIcon className="w-3.5 h-3.5 text-primary-600" />
              Image
            </button>
            <button
              onClick={() => onQuickAction('Get Help')}
              className="flex items-center gap-1.5 px-3 py-2 text-xs text-gray-700 hover:bg-gray-200 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <HelpCircle className="w-3.5 h-3.5 text-primary-600" />
              Help
            </button>
          </div>
        </div>

        <div className="h-px bg-gray-200 mx-3" />

        {/* Session List */}
        <div className="flex-1 overflow-y-auto p-3">
          <p className="text-xs font-medium text-gray-400 uppercase tracking-wider px-1 mb-2">Recent Chats</p>

          {sessions.length === 0 ? (
            <p className="text-sm text-gray-400 px-1 py-4 text-center">
              No conversations yet
            </p>
          ) : (
            <div className="space-y-1">
              {sessions.map(session => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={clsx(
                    'w-full text-left px-3 py-2.5 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 group',
                    session.id === currentSessionId
                      ? 'bg-primary-50 text-primary-900'
                      : 'hover:bg-gray-200 text-gray-700'
                  )}
                >
                  <div className="flex items-start gap-2">
                    <MessageSquare className={clsx(
                      'w-4 h-4 mt-0.5 shrink-0',
                      session.id === currentSessionId ? 'text-primary-600' : 'text-gray-400'
                    )} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">{session.title}</p>
                      <p className={clsx(
                        'text-xs mt-0.5',
                        session.id === currentSessionId ? 'text-primary-600' : 'text-gray-400'
                      )}>
                        {formatDate(session.createdAt)}
                        {session.messages.length > 0 && ` · ${session.messages.length} messages`}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
