import { useState, useRef, useEffect, useCallback } from 'react';
import { authFetch } from '../../services/api';
import { Send, Sparkles } from 'lucide-react';
import clsx from 'clsx';
import type { SRSTabName, SRSData } from '../../types/index.ts';

interface SRSChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface SRSChatProps {
  currentTab: SRSTabName;
  srsData: SRSData;
  onAutoFill: () => void;
  isAutoFilling: boolean;
  orgName?: string;
  sector?: string;
}

const TAB_LABELS: Record<SRSTabName, string> = {
  summary: 'Program Summary',
  programs: 'Programs',
  users: 'User Personas',
  w3h: 'W3H',
  forms: 'Forms',
  visitScheduling: 'Visit Scheduling',
  dashboardCards: 'Dashboard Cards',
  permissions: 'Permissions',
};

export function SRSChat({ currentTab, srsData, onAutoFill, isAutoFilling, orgName, sector }: SRSChatProps) {
  const [messages, setMessages] = useState<SRSChatMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: `I can help you fill out the SRS document. Try asking me things like:\n\n- "Fill this for an MCH program"\n- "What forms do I need for a nutrition program?"\n- "Suggest user personas for a WASH project"\n\nYou can also use the "AI Auto-Fill" button to have me suggest values for empty fields in the current tab.`,
      timestamp: new Date(),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const assistantContentRef = useRef('');
  const assistantIdRef = useRef('');
  const sessionIdRef = useRef(crypto.randomUUID());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim() || isLoading) return;

      const userMessage: SRSChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: content.trim(),
        timestamp: new Date(),
      };

      const assistantId = crypto.randomUUID();
      assistantIdRef.current = assistantId;
      assistantContentRef.current = '';

      const assistantMessage: SRSChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, userMessage, assistantMessage]);
      setInputText('');
      setIsLoading(true);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await authFetch('/api/srs/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: content.trim(),
            session_id: sessionIdRef.current,
            current_tab: currentTab,
            srs_context: {
              summary: srsData.summary,
              programs: srsData.programs.map(p => ({ name: p.name })),
              users: srsData.users.map(u => ({ type: u.type })),
              forms: srsData.forms.map(f => ({ name: f.name })),
            },
            org_name: orgName,
            sector: sector,
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`Request failed: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('event:')) continue;

            if (trimmed.startsWith('data:')) {
              const jsonStr = trimmed.slice(5).trim();
              if (jsonStr === '[DONE]') break;

              try {
                const parsed = JSON.parse(jsonStr) as { type?: string; content?: string };
                if (parsed.type === 'done') break;
                if (parsed.type === 'error') {
                  assistantContentRef.current = parsed.content ?? 'An error occurred.';
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantIdRef.current
                        ? { ...m, content: assistantContentRef.current }
                        : m
                    )
                  );
                  break;
                }
                if (parsed.type === 'text' && parsed.content) {
                  assistantContentRef.current += parsed.content;
                  setMessages(prev =>
                    prev.map(m =>
                      m.id === assistantIdRef.current
                        ? { ...m, content: assistantContentRef.current }
                        : m
                    )
                  );
                }
              } catch {
                // Not valid JSON, skip
              }
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          const errorMsg = (err as Error).message || 'Connection failed';
          assistantContentRef.current = `Sorry, I couldn't connect to the AI service. ${errorMsg}`;
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantIdRef.current
                ? { ...m, content: assistantContentRef.current }
                : m
            )
          );
        }
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, currentTab, srsData, orgName, sector]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(inputText);
      }
    },
    [inputText, sendMessage]
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-white shrink-0">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-sm font-semibold text-gray-900">AI Assistant</h4>
            <p className="text-xs text-gray-500">
              Helping with: {TAB_LABELS[currentTab]}
            </p>
          </div>
          <button
            onClick={onAutoFill}
            disabled={isAutoFilling}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500',
              isAutoFilling
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-teal-50 text-teal-700 hover:bg-teal-100'
            )}
          >
            <Sparkles className="w-3.5 h-3.5" />
            {isAutoFilling ? 'Filling...' : 'AI Auto-Fill'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3 bg-gray-50">
        {messages.map(msg => (
          <div
            key={msg.id}
            className={clsx(
              'flex',
              msg.role === 'user' ? 'justify-end' : 'justify-start'
            )}
          >
            <div
              className={clsx(
                'max-w-[90%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap shadow-sm',
                msg.role === 'user'
                  ? 'bg-teal-700 text-white'
                  : 'bg-white text-gray-900 border border-gray-200'
              )}
            >
              {msg.content || (
                <span className="text-gray-400 italic">Thinking...</span>
              )}
            </div>
          </div>
        ))}

        {isLoading && !assistantContentRef.current && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-500 shadow-sm">
              <div className="flex gap-1">
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400" />
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400" />
                <span className="typing-dot w-1.5 h-1.5 rounded-full bg-gray-400" />
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-200 bg-white shrink-0">
        <div className="flex items-end gap-2">
          <textarea
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about this tab..."
            rows={1}
            className="flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
          />
          <button
            onClick={() => sendMessage(inputText)}
            disabled={!inputText.trim() || isLoading}
            className={clsx(
              'p-2 rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-teal-500 shrink-0',
              inputText.trim() && !isLoading
                ? 'bg-teal-700 hover:bg-teal-800 text-white'
                : 'bg-gray-100 text-gray-300 cursor-not-allowed'
            )}
            aria-label="Send"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
