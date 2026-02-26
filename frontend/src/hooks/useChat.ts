import { useState, useCallback, useRef } from 'react';
import type { Message, Session, Attachment, SSEEvent, BundleFile } from '../types';
import { streamChat } from '../services/api';

function generateId(): string {
  return crypto.randomUUID();
}

function generateSessionTitle(firstMessage: string): string {
  const trimmed = firstMessage.trim();
  if (trimmed.length <= 40) return trimmed;
  return trimmed.slice(0, 37) + '...';
}

interface UseChatReturn {
  messages: Message[];
  sessions: Session[];
  currentSessionId: string | null;
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string, attachments?: Attachment[]) => void;
  startNewSession: () => void;
  switchSession: (sessionId: string) => void;
  clearError: () => void;
}

export function useChat(): UseChatReturn {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assistantMessageRef = useRef<string>('');
  const assistantMessageIdRef = useRef<string>('');

  const currentSession = sessions.find(s => s.id === currentSessionId);
  const messages = currentSession?.messages ?? [];

  const updateSessionMessages = useCallback((sessionId: string, updater: (msgs: Message[]) => Message[]) => {
    setSessions(prev => prev.map(s =>
      s.id === sessionId
        ? { ...s, messages: updater(s.messages) }
        : s
    ));
  }, []);

  const startNewSession = useCallback(() => {
    const newSession: Session = {
      id: generateId(),
      title: 'New Chat',
      createdAt: new Date(),
      messages: [],
    };
    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    setError(null);
  }, []);

  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
    setError(null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const sendMessage = useCallback((content: string, attachments?: Attachment[]) => {
    let sessionId = currentSessionId;

    if (!sessionId) {
      const newSession: Session = {
        id: generateId(),
        title: 'New Chat',
        createdAt: new Date(),
        messages: [],
      };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      sessionId = newSession.id;
    }

    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: new Date(),
      attachments,
    };

    const assistantMessageId = generateId();
    assistantMessageIdRef.current = assistantMessageId;
    assistantMessageRef.current = '';

    const assistantMessage: Message = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
    };

    updateSessionMessages(sessionId, msgs => [...msgs, userMessage, assistantMessage]);

    // Update session title from first user message
    setSessions(prev => prev.map(s =>
      s.id === sessionId && s.title === 'New Chat'
        ? { ...s, title: generateSessionTitle(content) }
        : s
    ));

    setIsLoading(true);
    setError(null);

    const targetSessionId = sessionId;

    const handleChunk = (event: SSEEvent) => {
      switch (event.type) {
        case 'text':
          assistantMessageRef.current += event.data;
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? { ...m, content: assistantMessageRef.current, metadata: { type: 'text' } }
                : m
            )
          );
          break;

        case 'progress':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: assistantMessageRef.current || event.data,
                    metadata: {
                      type: 'progress',
                      progress: event.metadata?.progress as { step: string; current: number; total: number } | undefined,
                    },
                  }
                : m
            )
          );
          break;

        case 'voice_mapped':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: assistantMessageRef.current || 'Voice data mapped to form fields:',
                    metadata: {
                      type: 'voice_mapped',
                      fields: (event.metadata?.fields ?? {}) as Record<string, unknown>,
                      confidence: (event.metadata?.confidence ?? {}) as Record<string, number>,
                    },
                  }
                : m
            )
          );
          break;

        case 'image_extracted':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: assistantMessageRef.current || 'Data extracted from image:',
                    metadata: {
                      type: 'image_extracted',
                      records: (event.metadata?.records ?? []) as Record<string, unknown>[],
                      warnings: (event.metadata?.warnings ?? []) as string[],
                    },
                  }
                : m
            )
          );
          break;

        case 'bundle_ready':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: assistantMessageRef.current || 'Bundle generated successfully!',
                    metadata: {
                      type: 'bundle_ready',
                      bundleId: event.metadata?.bundleId as string | undefined,
                      downloadUrl: event.metadata?.downloadUrl as string | undefined,
                      bundleFiles: event.metadata?.files as BundleFile[] | undefined,
                    },
                  }
                : m
            )
          );
          break;

        case 'rule':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: assistantMessageRef.current || 'Generated rule:',
                    metadata: {
                      type: 'rule',
                      code: event.data,
                      ruleType: event.metadata?.ruleType as string | undefined,
                    },
                  }
                : m
            )
          );
          break;

        case 'error':
          updateSessionMessages(targetSessionId, msgs =>
            msgs.map(m =>
              m.id === assistantMessageIdRef.current
                ? {
                    ...m,
                    content: event.data,
                    metadata: { type: 'error' },
                  }
                : m
            )
          );
          break;
      }
    };

    const handleDone = () => {
      setIsLoading(false);
    };

    const handleError = (err: Error) => {
      setIsLoading(false);
      setError(err.message);
      updateSessionMessages(targetSessionId, msgs =>
        msgs.map(m =>
          m.id === assistantMessageIdRef.current
            ? {
                ...m,
                content: `Error: ${err.message}`,
                metadata: { type: 'error' },
              }
            : m
        )
      );
    };

    streamChat(content, targetSessionId, attachments, handleChunk, handleDone, handleError);
  }, [currentSessionId, updateSessionMessages]);

  return {
    messages,
    sessions,
    currentSessionId,
    isLoading,
    error,
    sendMessage,
    startNewSession,
    switchSession,
    clearError,
  };
}
