import { useState, useCallback, useRef, useEffect } from 'react';
import type { Message, Session, Attachment, SSEEvent, BundleFile, UserProfile, WorkflowStep, ClarityQuestion, SRSData } from '../types';
import { streamChat, authFetch } from '../services/api';
import { mergeSrsUpdate } from '../components/srs/SRSPreviewPanel';
import { createDefaultSRSData } from '../data/srs-templates';

function generateId(): string {
  return crypto.randomUUID();
}

function generateSessionTitle(firstMessage: string): string {
  const trimmed = firstMessage.trim();
  if (trimmed.length <= 40) return trimmed;
  return trimmed.slice(0, 37) + '...';
}

// ── Backend sync helpers ─────────────────────────────────────────────────────

async function syncCreateSession(sessionId: string, userId: string, title: string) {
  try {
    await authFetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: sessionId, user_id: userId, title }),
    });
  } catch { /* best-effort */ }
}

async function syncUpdateSessionTitle(sessionId: string, title: string) {
  try {
    await authFetch(`/api/sessions/${sessionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
  } catch { /* best-effort */ }
}

async function syncDeleteSession(sessionId: string) {
  try {
    await authFetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
  } catch { /* best-effort */ }
}

async function fetchBackendSessions(userId: string): Promise<Session[]> {
  try {
    const res = await authFetch(`/api/users/${userId}/sessions`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.sessions || []).map((s: { id: string; title: string; created_at: string; message_count: number }) => ({
      id: s.id,
      title: s.title,
      createdAt: new Date(s.created_at),
      messages: [], // Messages are loaded on demand
      _messageCount: s.message_count,
    }));
  } catch {
    return [];
  }
}

async function fetchSessionMessages(sessionId: string): Promise<Message[]> {
  try {
    const res = await authFetch(`/api/sessions/${sessionId}/messages`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.messages || []).map((m: { id: string; role: string; content: string; created_at: string; metadata?: Record<string, unknown> }) => ({
      id: m.id,
      role: m.role as 'user' | 'assistant',
      content: m.content,
      timestamp: new Date(m.created_at),
      metadata: m.metadata ?? undefined,
    }));
  } catch {
    return [];
  }
}

// ── localStorage cache helpers ───────────────────────────────────────────────

function loadCurrentSessionId(userId: string): string | null {
  try {
    return localStorage.getItem(`avni-ai-current-session-${userId}`);
  } catch {
    return null;
  }
}

function saveCurrentSessionId(userId: string, sessionId: string | null) {
  try {
    if (sessionId) {
      localStorage.setItem(`avni-ai-current-session-${userId}`, sessionId);
    } else {
      localStorage.removeItem(`avni-ai-current-session-${userId}`);
    }
  } catch { /* silently fail */ }
}

// ── Hook ─────────────────────────────────────────────────────────────────────

interface UseChatReturn {
  messages: Message[];
  sessions: Session[];
  currentSessionId: string | null;
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string, attachments?: Attachment[]) => void;
  startNewSession: () => void;
  switchSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  clearError: () => void;
  // SRS mode
  srsMode: boolean;
  srsData: SRSData;
  srsPhase: string;
  srsBundleStatus: 'idle' | 'generating' | 'done' | 'error';
  srsBundleId: string | null;
  setSrsData: (data: SRSData) => void;
  startSrsMode: () => void;
  stopSrsMode: () => void;
  generateSrsBundle: () => void;
}

export function useChat(userId: string | null, profile?: UserProfile | null): UseChatReturn {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // SRS mode state
  const [srsMode, setSrsMode] = useState(false);
  const [srsData, setSrsDataState] = useState<SRSData>(createDefaultSRSData());
  const [srsPhase, setSrsPhase] = useState('start');
  const [srsBundleStatus, setSrsBundleStatus] = useState<'idle' | 'generating' | 'done' | 'error'>('idle');
  const [srsBundleId, setSrsBundleId] = useState<string | null>(null);

  const assistantMessageRef = useRef<string>('');
  const assistantMessageIdRef = useRef<string>('');
  const abortControllerRef = useRef<AbortController | null>(null);
  const bundlePollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cleanup bundle poll on unmount
  useEffect(() => {
    return () => {
      if (bundlePollRef.current) clearInterval(bundlePollRef.current);
    };
  }, []);

  // Load sessions from backend on user change
  useEffect(() => {
    if (!userId) {
      setSessions([]);
      setCurrentSessionId(null);
      return;
    }
    const savedSessionId = loadCurrentSessionId(userId);
    fetchBackendSessions(userId).then(backendSessions => {
      if (backendSessions.length > 0) {
        setSessions(backendSessions);
        // Restore last active session
        const validId = backendSessions.find(s => s.id === savedSessionId)?.id;
        setCurrentSessionId(validId ?? null);
        // Load messages for the active session
        if (validId) {
          fetchSessionMessages(validId).then(msgs => {
            setSessions(prev => prev.map(s =>
              s.id === validId ? { ...s, messages: msgs } : s
            ));
          });
        }
      }
    });
  }, [userId]);

  // Persist current session id
  useEffect(() => {
    if (userId) {
      saveCurrentSessionId(userId, currentSessionId);
    }
  }, [userId, currentSessionId]);

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
    // Sync to backend
    if (userId) {
      syncCreateSession(newSession.id, userId, newSession.title);
    }
    return newSession.id;
  }, [userId]);

  // ── SRS Mode ───────────────────────────────────────────────────────────────

  const setSrsData = useCallback((data: SRSData) => {
    setSrsDataState(data);
  }, []);

  const checkSrsMode = useCallback(async (sessionId: string) => {
    try {
      const res = await authFetch(`/api/srs/state/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setSrsMode(data.srs_mode ?? false);
        if (data.srs_data && Object.keys(data.srs_data).length > 0) {
          setSrsDataState(data.srs_data as SRSData);
        }
        if (data.phase) setSrsPhase(data.phase);
      } else {
        setSrsMode(false);
      }
    } catch {
      setSrsMode(false);
    }
  }, []);

  const startSrsMode = useCallback(async () => {
    let sessionId = currentSessionId;

    // Create a new session if none exists
    if (!sessionId) {
      const newSession: Session = {
        id: generateId(),
        title: 'SRS Builder',
        createdAt: new Date(),
        messages: [],
      };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      sessionId = newSession.id;
      if (userId) {
        syncCreateSession(newSession.id, userId, 'SRS Builder');
      }
    }

    // Activate SRS mode on the backend
    try {
      await authFetch('/api/srs/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, enabled: true }),
      });
    } catch {
      // Best-effort - still activate locally
    }

    setSrsMode(true);
    setSrsDataState(createDefaultSRSData());
    setSrsPhase('start');
    setSrsBundleStatus('idle');
    setSrsBundleId(null);

    // Send the initial greeting message to kick off the conversation
    // We need to use a slight delay to ensure session state is set
    setTimeout(() => {
      sendMessageInternal(
        "I want to build an Avni implementation. Help me create the SRS.",
        undefined,
        sessionId!,
      );
    }, 100);
  }, [currentSessionId, userId]);

  const stopSrsMode = useCallback(async () => {
    if (currentSessionId) {
      try {
        await authFetch('/api/srs/mode', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSessionId, enabled: false }),
        });
      } catch { /* best-effort */ }
    }
    setSrsMode(false);
    setSrsDataState(createDefaultSRSData());
    setSrsPhase('start');
    setSrsBundleStatus('idle');
    setSrsBundleId(null);
  }, [currentSessionId]);

  // Generate bundle from SRS data
  const generateSrsBundle = useCallback(async () => {
    setSrsBundleStatus('generating');

    try {
      const backendSrs: any = {
        orgName: srsData.summary?.organizationName || (srsData as any).orgName || 'Organisation',
        subjectTypes: (srsData as any).subjectTypes || [{ name: 'Individual', type: 'Person' }],
        programs: (srsData.programs || []).map((p: any) =>
          typeof p === 'string' ? { name: p } : { name: p.name, colour: p.colour || p.color }
        ),
        encounterTypes: (srsData as any).encounterTypes || srsData.w3h?.map((w: any) => w.what) || [],
        forms: (srsData.forms || []).map((f: any) => ({
          name: f.name,
          formType: f.formType || 'Encounter',
          programName: f.programName || null,
          encounterTypeName: f.encounterTypeName || null,
          subjectTypeName: f.subjectTypeName || null,
          groups: f.groups || (f.fields
            ? Object.entries(
                (f.fields as any[]).reduce<Record<string, any[]>>((acc, field) => {
                  const page = field.pageName || 'Default';
                  if (!acc[page]) acc[page] = [];
                  acc[page].push(field);
                  return acc;
                }, {})
              ).map(([groupName, fields]) => ({
                name: groupName,
                fields: fields.map((field: any) => ({
                  name: field.fieldName || field.name,
                  dataType: field.dataType,
                  mandatory: field.mandatory,
                  options: field.options
                    ? (typeof field.options === 'string'
                        ? field.options.split(',').map((o: string) => o.trim()).filter(Boolean)
                        : field.options)
                    : [],
                  type: field.selectionType === 'Multi' ? 'MultiSelect' : 'SingleSelect',
                  unit: field.unit || undefined,
                  lowAbsolute: field.min ? Number(field.min) : undefined,
                  highAbsolute: field.max ? Number(field.max) : undefined,
                })),
              }))
            : []),
        })),
        groups: (srsData as any).groups || srsData.users?.map((u: any) => u.type).filter(Boolean) || ['Everyone'],
        addressLevelTypes: (srsData as any).addressLevelTypes || null,
        programEncounterMappings: (srsData as any).programEncounterMappings || null,
        generalEncounterTypes: (srsData as any).generalEncounterTypes || null,
        visitSchedules: (srsData as any).visitSchedules || null,
        eligibilityRules: (srsData as any).eligibilityRules || null,
      };

      const response = await authFetch('/api/bundle/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ srs_data: backendSrs }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Generation failed' }));
        throw new Error(err.detail || 'Bundle generation failed');
      }

      const data = await response.json();
      const newBundleId = data.bundle_id || data.id;

      if (!newBundleId) {
        setSrsBundleStatus('done');
        setSrsBundleId(data.bundle_id || 'generated');
        return;
      }

      setSrsBundleId(newBundleId);

      // Poll for status
      bundlePollRef.current = setInterval(async () => {
        try {
          const statusRes = await authFetch(`/api/bundle/${newBundleId}/status`);
          if (!statusRes.ok) return;
          const statusData = await statusRes.json();
          const status = statusData.status?.toLowerCase();
          if (status === 'completed' || status === 'done') {
            if (bundlePollRef.current) clearInterval(bundlePollRef.current);
            setSrsBundleStatus('done');
          } else if (status === 'failed' || status === 'error') {
            if (bundlePollRef.current) clearInterval(bundlePollRef.current);
            setSrsBundleStatus('error');
          }
        } catch { /* polling error, continue */ }
      }, 2000);
    } catch {
      setSrsBundleStatus('error');
    }
  }, [srsData]);

  const switchSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
    setError(null);
    // Load messages from backend if not already loaded
    setSessions(prev => {
      const session = prev.find(s => s.id === sessionId);
      if (session && session.messages.length === 0) {
        fetchSessionMessages(sessionId).then(msgs => {
          setSessions(p => p.map(s =>
            s.id === sessionId ? { ...s, messages: msgs } : s
          ));
        });
      }
      return prev;
    });
    // Check if this session has SRS mode enabled
    checkSrsMode(sessionId);
  }, [checkSrsMode]);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    setCurrentSessionId(prev => prev === sessionId ? null : prev);
    syncDeleteSession(sessionId);
    // If deleting the current SRS session, exit SRS mode
    if (sessionId === currentSessionId && srsMode) {
      setSrsMode(false);
      setSrsDataState(createDefaultSRSData());
      setSrsPhase('start');
    }
  }, [currentSessionId, srsMode]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Internal send message with explicit sessionId (used by startSrsMode)
  const sendMessageInternal = useCallback((content: string, attachments?: Attachment[], explicitSessionId?: string) => {
    let sessionId = explicitSessionId || currentSessionId;

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
      if (userId) {
        syncCreateSession(newSession.id, userId, newSession.title);
      }
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
    const targetSessionId = sessionId;
    setSessions(prev => prev.map(s => {
      if (s.id === targetSessionId && s.title === 'New Chat') {
        const title = generateSessionTitle(content);
        syncUpdateSessionTitle(targetSessionId, title);
        return { ...s, title };
      }
      return s;
    }));

    setIsLoading(true);
    setError(null);

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

        case 'workflow_progress':
          updateSessionMessages(targetSessionId, msgs => {
            const progressMsg: Message = {
              id: generateId(),
              role: 'assistant',
              content: event.data || 'Workflow step update',
              timestamp: new Date(),
              metadata: {
                type: 'workflow_progress',
                workflowId: event.metadata?.workflow_id as string | undefined,
                step: event.metadata?.step as any,
              },
            };
            return [...msgs, progressMsg];
          });
          break;

        case 'checkpoint':
          updateSessionMessages(targetSessionId, msgs => {
            const checkpointMsg: Message = {
              id: generateId(),
              role: 'assistant',
              content: (event.metadata?.message as string) || 'Action required: checkpoint reached',
              timestamp: new Date(),
              metadata: {
                type: 'checkpoint',
                workflowId: event.metadata?.workflow_id as string | undefined,
                step: event.metadata?.step as any,
                needs: event.metadata?.needs as 'approval' | 'review' | 'input' | undefined,
                resultSummary: event.metadata?.result_summary,
              },
            };
            return [...msgs, checkpointMsg];
          });
          break;

        case 'clarification':
          updateSessionMessages(targetSessionId, msgs => {
            const clarityMsg: Message = {
              id: generateId(),
              role: 'assistant',
              content: event.data || 'Clarification needed before proceeding',
              timestamp: new Date(),
              metadata: {
                type: 'clarification',
                workflowId: event.metadata?.workflow_id as string | undefined,
                questions: (event.metadata?.questions ?? []) as any[],
              },
            };
            return [...msgs, clarityMsg];
          });
          break;

        case 'action':
          // Dispatch a custom DOM event so App.tsx can handle view changes
          if (event.metadata?.action === 'open_srs_builder') {
            window.dispatchEvent(new CustomEvent('avni-action', { detail: { action: 'open_srs_builder' } }));
          }
          break;

        // ── SRS mode SSE events ──────────────────────────────────────────
        case 'srs_update': {
          const update = (event.metadata?.data || event.data) as Partial<Record<string, unknown>> | undefined;
          if (update && typeof update === 'object') {
            setSrsDataState(prev => {
              const updated = mergeSrsUpdate(prev, update);
              // Highlight sections that changed
              for (const key of Object.keys(update)) {
                const sectionMap: Record<string, string> = {
                  summary: 'organization',
                  programs: 'programs',
                  users: 'subjects',
                  forms: 'forms',
                  visitScheduling: 'scheduling',
                  dashboardCards: 'dashboard',
                  permissions: 'permissions',
                  w3h: 'programs',
                };
                if (sectionMap[key]) {
                  window.dispatchEvent(new CustomEvent('srs-highlight-section', { detail: { section: sectionMap[key] } }));
                }
              }
              return updated;
            });
          }
          break;
        }

        case 'phase': {
          const newPhase = (event.metadata?.phase || event.data) as string | undefined;
          if (newPhase) setSrsPhase(newPhase);
          break;
        }

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

    // Abort any in-flight request before starting new one (prevents race conditions)
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    streamChat(content, targetSessionId, attachments, handleChunk, handleDone, handleError, profile ?? undefined, controller.signal);
  }, [currentSessionId, userId, updateSessionMessages, profile]);

  // Public sendMessage wraps internal
  const sendMessage = useCallback((content: string, attachments?: Attachment[]) => {
    sendMessageInternal(content, attachments);
  }, [sendMessageInternal]);

  return {
    messages,
    sessions,
    currentSessionId,
    isLoading,
    error,
    sendMessage,
    startNewSession,
    switchSession,
    deleteSession,
    clearError,
    // SRS mode
    srsMode,
    srsData,
    srsPhase,
    srsBundleStatus,
    srsBundleId,
    setSrsData,
    startSrsMode,
    stopSrsMode,
    generateSrsBundle,
  };
}
