import { memo } from 'react';
import type { ReactNode } from 'react';
import clsx from 'clsx';

interface MessageBubbleProps {
  role: 'user' | 'assistant' | 'system';
  children: ReactNode;
  isStreaming?: boolean;
}

export const MessageBubble = memo(function MessageBubble({ role, children, isStreaming }: MessageBubbleProps) {
  if (role === 'system') {
    return (
      <div className="flex justify-center mb-4 px-4">
        <div className="bg-amber-50 border-l-3 border-amber-400 text-gray-900 text-sm px-4 py-2.5 rounded-lg max-w-[90%] md:max-w-[80%]" style={{ lineHeight: '1.6' }}>
          {children}
        </div>
      </div>
    );
  }

  const isUser = role === 'user';

  return (
    <div className={clsx('flex mb-4 px-4 fade-in', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={clsx(
          'px-4 py-3 transition-all',
          'max-w-full md:max-w-[80%]',
          isUser
            ? 'bg-teal-700 text-white rounded-lg rounded-tr-sm'
            : 'bg-slate-50 text-gray-900 rounded-lg border-l-3 border-teal-600 shadow-sm group',
          isStreaming && 'animate-pulse-subtle'
        )}
        style={{ lineHeight: '1.6', fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        {children}
      </div>
    </div>
  );
});

/** Loading placeholder bubble with animated dots */
export function LoadingBubble() {
  return (
    <div className="flex justify-start mb-4 px-4">
      <div
        className="bg-slate-50 text-gray-900 rounded-lg border-l-3 border-teal-600 shadow-sm px-4 py-3"
        style={{ lineHeight: '1.6' }}
      >
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-teal-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}
