import type { Attachment, SSEEvent, RuleTestResult, SRSData, UserProfile, AdminUser, PlatformStats, InviteUserRequest, Workflow, ClarityQuestion, RegenerationResult, ProcessDocumentResult } from '../types';

const BASE_URL = '/api';

/** Request timeout in ms — bundle generation can take a while (LLM parsing + file gen). */
const REQUEST_TIMEOUT_MS = 180_000;

/** Create an AbortController with a timeout. Returns [signal, cleanup]. */
function withTimeout(ms: number): [AbortSignal, () => void] {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return [controller.signal, () => clearTimeout(timer)];
}

/** Get auth headers from stored profile token. */
function getAuthHeaders(): Record<string, string> {
  try {
    const raw = localStorage.getItem('avni-ai-user-profile');
    if (raw) {
      const profile = JSON.parse(raw);
      if (profile.accessToken) {
        return { Authorization: `Bearer ${profile.accessToken}` };
      }
    }
  } catch { /* ignore */ }
  return {};
}

/**
 * Try to refresh tokens using the stored refresh token.
 * On success, updates localStorage and returns the new access token.
 * On failure, clears the stored profile (forces re-login) and returns null.
 */
async function tryRefreshToken(): Promise<string | null> {
  try {
    const raw = localStorage.getItem('avni-ai-user-profile');
    if (!raw) return null;
    const profile = JSON.parse(raw);
    if (!profile.refreshToken) return null;

    const response = await fetch(`${BASE_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: profile.refreshToken }),
    });

    if (!response.ok) {
      // Refresh failed — clear profile to force re-login
      localStorage.removeItem('avni-ai-user-profile');
      return null;
    }

    const result = await response.json();
    // Update stored tokens
    profile.accessToken = result.access_token;
    profile.refreshToken = result.refresh_token;
    localStorage.setItem('avni-ai-user-profile', JSON.stringify(profile));
    return result.access_token as string;
  } catch {
    localStorage.removeItem('avni-ai-user-profile');
    return null;
  }
}

/** Authenticated fetch wrapper with automatic token refresh on 401. */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = { ...getAuthHeaders(), ...options.headers as Record<string, string> };
  const response = await fetch(url, { ...options, headers });

  // If 401 and we have a refresh token, try to refresh and retry once
  if (response.status === 401) {
    const newAccessToken = await tryRefreshToken();
    if (newAccessToken) {
      const retryHeaders = {
        ...options.headers as Record<string, string>,
        Authorization: `Bearer ${newAccessToken}`,
      };
      return fetch(url, { ...options, headers: retryHeaders });
    }
  }

  return response;
}

export async function streamChat(
  message: string,
  sessionId: string,
  attachments: Attachment[] | undefined,
  onChunk: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  profile?: UserProfile,
  signal?: AbortSignal,
): Promise<void> {
  const [timeoutSignal, cleanupTimeout] = withTimeout(REQUEST_TIMEOUT_MS);
  // Combine external abort signal with timeout signal
  const combinedController = new AbortController();
  const abort = () => combinedController.abort();
  timeoutSignal.addEventListener('abort', abort);
  signal?.addEventListener('abort', abort);

  try {
    const response = await authFetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: combinedController.signal,
      body: JSON.stringify({
        message,
        session_id: sessionId,
        org_name: profile?.orgName || undefined,
        sector: profile?.sector || undefined,
        org_context: profile?.orgContext || undefined,
        byok_provider: profile?.byokProvider || undefined,
        byok_api_key: profile?.byokApiKey || undefined,
        attachments: attachments?.map(a => ({
          type: a.type,
          filename: a.name,
          data: a.data,
          mime_type: a.mimeType,
        })) ?? [],
      }),
    });

    if (!response.ok) {
      throw new Error(`Chat request failed: ${response.status} ${response.statusText}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body reader available');
    }

    const decoder = new TextDecoder();
    let buffer = '';
    let currentEventType = 'message';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() ?? '';

      for (const line of lines) {
        const trimmed = line.trim();

        // Empty line signals end of an SSE event block
        if (!trimmed) {
          currentEventType = 'message';
          continue;
        }

        // Handle event type line
        if (trimmed.startsWith('event:')) {
          currentEventType = trimmed.slice(6).trim();
          continue;
        }

        // Handle data line
        if (trimmed.startsWith('data:')) {
          const jsonStr = trimmed.slice(5).trim();
          if (jsonStr === '[DONE]') {
            onDone();
            return;
          }

          // Only process data lines from 'message' events (or default)
          if (currentEventType === 'message' || currentEventType === '') {
            try {
              const parsed = JSON.parse(jsonStr) as { type?: string; content?: string; metadata?: Record<string, unknown> };
              const eventType = (parsed.type ?? 'text') as SSEEvent['type'];

              if (eventType === 'done') {
                onDone();
                return;
              }

              const event: SSEEvent = {
                type: eventType,
                data: parsed.content ?? '',
                metadata: parsed.metadata,
              };
              onChunk(event);
            } catch {
              // If it's plain text (not JSON), treat as text event
              onChunk({ type: 'text', data: jsonStr });
            }
          }
          continue;
        }

        // Handle lines without a field name prefix (continuation or plain text)
        // SSE spec says these should be ignored, but we handle gracefully
      }
    }

    // Process any remaining buffer
    if (buffer.trim()) {
      const trimmed = buffer.trim();
      if (trimmed.startsWith('data:')) {
        const jsonStr = trimmed.slice(5).trim();
        if (jsonStr && jsonStr !== '[DONE]') {
          try {
            const parsed = JSON.parse(jsonStr) as { type?: string; content?: string; metadata?: Record<string, unknown> };
            const eventType = (parsed.type ?? 'text') as SSEEvent['type'];
            if (eventType !== 'done') {
              onChunk({
                type: eventType,
                data: parsed.content ?? '',
                metadata: parsed.metadata,
              });
            }
          } catch {
            onChunk({ type: 'text', data: jsonStr });
          }
        }
      }
    }

    onDone();
  } catch (error) {
    if (combinedController.signal.aborted && !signal?.aborted) {
      onError(new Error('Request timed out. The server took too long to respond.'));
    } else if (signal?.aborted) {
      // User-initiated abort (e.g. session switch) — don't show as error
      onDone();
    } else {
      onError(error instanceof Error ? error : new Error(String(error)));
    }
  } finally {
    cleanupTimeout();
    timeoutSignal.removeEventListener('abort', abort);
    signal?.removeEventListener('abort', abort);
  }
}

export async function mapVoice(
  transcript: string,
  formJson: Record<string, unknown>,
  language: string
): Promise<{ fields: Record<string, unknown>; confidence: Record<string, number>; unmapped_text: string }> {
  const response = await authFetch(`${BASE_URL}/voice/map`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript, formJson, language }),
  });

  if (!response.ok) {
    throw new Error(`Voice map request failed: ${response.status}`);
  }

  return response.json();
}

export async function extractImage(
  imageFile: File,
  formJson: Record<string, unknown>
): Promise<{ records: Record<string, unknown>[]; warnings: string[] }> {
  const formData = new FormData();
  formData.append('image', imageFile);
  formData.append('formJson', JSON.stringify(formJson));

  const response = await authFetch(`${BASE_URL}/image/extract`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Image extract request failed: ${response.status}`);
  }

  return response.json();
}

export async function generateBundle(
  srsData: Record<string, unknown>
): Promise<{ bundleId: string; files: unknown[] }> {
  const response = await authFetch(`${BASE_URL}/bundle/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(srsData),
  });

  if (!response.ok) {
    throw new Error(`Bundle generation failed: ${response.status}`);
  }

  return response.json();
}

export async function downloadBundle(bundleId: string): Promise<Blob> {
  const response = await authFetch(`${BASE_URL}/bundle/${bundleId}/download`);

  if (!response.ok) {
    throw new Error(`Bundle download failed: ${response.status}`);
  }

  return response.blob();
}

export async function saveObservations(
  fields: Record<string, unknown>
): Promise<{ success: boolean; message: string }> {
  const response = await authFetch(`${BASE_URL}/avni/save-observations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ observations: fields }),
  });

  if (!response.ok) {
    throw new Error(`Save observations failed: ${response.status}`);
  }

  return response.json();
}

export async function testRule(
  code: string,
  ruleType: string
): Promise<RuleTestResult> {
  const response = await authFetch(`${BASE_URL}/rules/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, ruleType }),
  });

  if (!response.ok) {
    throw new Error(`Rule test failed: ${response.status}`);
  }

  return response.json();
}

export async function searchKnowledge(
  query: string
): Promise<{ results: { content: string; source: string; score: number }[] }> {
  const response = await authFetch(`${BASE_URL}/knowledge/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`Knowledge search failed: ${response.status}`);
  }

  return response.json();
}

// ─── SRS API Functions ───────────────────────────────────────────────────────

export async function generateBundleFromSRS(
  srsData: SRSData
): Promise<{ id: string; status: string; progress: number; message: string }> {
  const response = await authFetch(`${BASE_URL}/bundle/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ srs_data: srsData }),
  });

  if (!response.ok) {
    throw new Error(`SRS bundle generation failed: ${response.status}`);
  }

  return response.json();
}

export async function generateBundleFromExcel(
  files: File[]
): Promise<{ id: string; status: string; progress: number; message: string }> {
  const formData = new FormData();
  files.forEach(f => formData.append('files', f));

  const [signal, cleanup] = withTimeout(REQUEST_TIMEOUT_MS);
  try {
    const response = await authFetch(`${BASE_URL}/bundle/generate-from-excel`, {
      method: 'POST',
      body: formData,
      signal,
    });

    if (!response.ok) {
      throw new Error(`Excel bundle generation failed: ${response.status}`);
    }

    return response.json();
  } finally {
    cleanup();
  }
}

export async function getBundleStatus(
  bundleId: string
): Promise<{ id: string; status: string; progress: number; message: string }> {
  const response = await authFetch(`${BASE_URL}/bundle/${bundleId}/status`);

  if (!response.ok) {
    throw new Error(`Bundle status check failed: ${response.status}`);
  }

  return response.json();
}

export async function aiAutoFill(
  tab: string,
  currentData: Record<string, unknown>,
  context?: string
): Promise<{ tab: string; suggestions: Record<string, unknown> }> {
  const response = await authFetch(`${BASE_URL}/bundle/ai-autofill`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tab, current_data: currentData, context: context ?? '' }),
  });

  if (!response.ok) {
    throw new Error(`AI auto-fill failed: ${response.status}`);
  }

  return response.json();
}

// ─── Admin API Functions ─────────────────────────────────────────────────────

export async function fetchAdminUsers(
  filters?: { search?: string; role?: string; orgName?: string; isActive?: boolean; offset?: number; limit?: number }
): Promise<{ users: AdminUser[]; total: number }> {
  const params = new URLSearchParams();
  if (filters?.search) params.set('search', filters.search);
  if (filters?.role) params.set('role', filters.role);
  if (filters?.orgName) params.set('org_name', filters.orgName);
  if (filters?.isActive !== undefined) params.set('is_active', String(filters.isActive));
  if (filters?.offset !== undefined) params.set('offset', String(filters.offset));
  if (filters?.limit !== undefined) params.set('limit', String(filters.limit));

  const qs = params.toString();
  const response = await authFetch(`${BASE_URL}/admin/users${qs ? `?${qs}` : ''}`);

  if (!response.ok) {
    throw new Error(`Fetch admin users failed: ${response.status}`);
  }

  const data = await response.json();
  // Backend returns snake_case, frontend expects camelCase
  return {
    users: (data.users || []).map((u: Record<string, unknown>) => ({
      id: u.id,
      name: u.name,
      email: u.email || '',
      orgName: u.org_name || '',
      sector: u.sector || '',
      role: u.role,
      isActive: u.is_active ?? false,
      lastLogin: u.last_login || null,
      createdAt: u.created_at || '',
    })),
    total: data.count ?? (data.users || []).length,
  };
}

export async function createAdminUser(
  data: { email: string; name: string; password: string; orgName: string; role: string; sector?: string }
): Promise<AdminUser & { tempPassword?: string }> {
  const response = await authFetch(`${BASE_URL}/admin/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Create admin user failed: ${response.status}`);
  }

  return response.json();
}

export async function updateUserRole(userId: string, role: string): Promise<{ success: boolean }> {
  const response = await authFetch(`${BASE_URL}/admin/users/${userId}/role`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });

  if (!response.ok) {
    throw new Error(`Update user role failed: ${response.status}`);
  }

  return response.json();
}

export async function updateUserStatus(userId: string, isActive: boolean): Promise<{ success: boolean }> {
  const response = await authFetch(`${BASE_URL}/admin/users/${userId}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: isActive }),
  });

  if (!response.ok) {
    throw new Error(`Update user status failed: ${response.status}`);
  }

  return response.json();
}

export async function inviteUser(data: InviteUserRequest): Promise<{ success: boolean; tempPassword?: string }> {
  const response = await authFetch(`${BASE_URL}/admin/users/invite`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Invite user failed: ${response.status}`);
  }

  return response.json();
}

export async function deleteUser(userId: string): Promise<{ success: boolean }> {
  const response = await authFetch(`${BASE_URL}/admin/users/${userId}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    throw new Error(`Delete user failed: ${response.status}`);
  }

  return response.json();
}

export async function fetchPlatformStats(): Promise<PlatformStats> {
  const response = await authFetch(`${BASE_URL}/admin/stats`);

  if (!response.ok) {
    throw new Error(`Fetch platform stats failed: ${response.status}`);
  }

  const data = await response.json();
  // Backend returns snake_case, frontend expects camelCase
  return {
    totalUsers: data.total_users ?? 0,
    activeUsers: data.active_users ?? 0,
    usersByRole: data.users_by_role ?? {},
    usersByOrg: data.users_by_org ?? {},
    totalSessions: data.total_sessions ?? 0,
    recentMessages24h: data.messages_24h ?? 0,
    recentMessages7d: data.messages_7d ?? 0,
    recentMessages30d: data.messages_30d ?? 0,
  };
}

export async function bootstrapAdmin(
  data: { name: string; email: string; password: string; orgName: string }
): Promise<{ success: boolean; user: AdminUser; accessToken: string; refreshToken: string }> {
  const response = await fetch(`${BASE_URL}/admin/bootstrap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`Bootstrap admin failed: ${response.status}`);
  }

  return response.json();
}

// ─── Workflow API Functions ──────────────────────────────────────────────────

export async function startWorkflow(
  type: string,
  data: any
): Promise<Workflow> {
  const response = await authFetch(`${BASE_URL}/workflow/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_type: type, ...data }),
  });

  if (!response.ok) {
    throw new Error(`Start workflow failed: ${response.status}`);
  }

  const result = await response.json();
  return {
    id: result.workflow_id,
    name: result.name,
    steps: result.steps,
    status: result.status as Workflow['status'],
    current_step_index: 0,
    created_at: Date.now() / 1000,
  };
}

export async function getWorkflowStatus(workflowId: string): Promise<Workflow> {
  const response = await authFetch(`${BASE_URL}/workflow/${workflowId}/status`);

  if (!response.ok) {
    throw new Error(`Get workflow status failed: ${response.status}`);
  }

  const result = await response.json();
  return {
    id: result.id,
    name: result.name,
    steps: result.steps,
    status: result.status as Workflow['status'],
    current_step_index: result.current_step_index,
    created_at: result.created_at,
  };
}

export async function approveStep(
  workflowId: string,
  stepId: string,
  feedback?: string
): Promise<void> {
  const response = await authFetch(`${BASE_URL}/workflow/${workflowId}/step/${stepId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: true, feedback: feedback ?? '' }),
  });

  if (!response.ok) {
    throw new Error(`Approve step failed: ${response.status}`);
  }
}

export async function rejectStep(
  workflowId: string,
  stepId: string,
  feedback: string
): Promise<void> {
  const response = await authFetch(`${BASE_URL}/workflow/${workflowId}/step/${stepId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved: false, feedback }),
  });

  if (!response.ok) {
    throw new Error(`Reject step failed: ${response.status}`);
  }
}

export async function provideStepInput(
  workflowId: string,
  stepId: string,
  data: any
): Promise<void> {
  const response = await authFetch(`${BASE_URL}/workflow/${workflowId}/step/${stepId}/input`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ input_data: data }),
  });

  if (!response.ok) {
    throw new Error(`Provide step input failed: ${response.status}`);
  }
}

export async function cancelWorkflow(workflowId: string): Promise<void> {
  const response = await authFetch(`${BASE_URL}/workflow/${workflowId}/cancel`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Cancel workflow failed: ${response.status}`);
  }
}

export function subscribeToWorkflow(
  workflowId: string,
  onEvent: (event: any) => void
): EventSource {
  const token = (() => {
    try {
      const raw = localStorage.getItem('avni-ai-user-profile');
      if (raw) {
        const profile = JSON.parse(raw);
        return profile.accessToken || '';
      }
    } catch { /* ignore */ }
    return '';
  })();

  const url = `${BASE_URL}/workflow/${workflowId}/events${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  const eventSource = new EventSource(url);

  eventSource.onmessage = (event) => {
    try {
      const parsed = JSON.parse(event.data);
      onEvent(parsed);

      // Auto-close on terminal events
      if (parsed.type === 'workflow_completed' || parsed.type === 'workflow_failed') {
        eventSource.close();
      }
    } catch { /* ignore parse errors */ }
  };

  eventSource.onerror = () => {
    // EventSource will auto-reconnect; close on permanent failures
    if (eventSource.readyState === EventSource.CLOSED) {
      onEvent({ type: 'connection_closed' });
    }
  };

  return eventSource;
}

// ─── Clarity API Functions ───────────────────────────────────────────────────

export async function analyzeClarity(
  srsData: any
): Promise<{ questions: ClarityQuestion[]; can_proceed: boolean }> {
  const response = await authFetch(`${BASE_URL}/workflow/clarity/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ srs_data: srsData }),
  });

  if (!response.ok) {
    throw new Error(`Clarity analysis failed: ${response.status}`);
  }

  return response.json();
}

export async function applyClarity(
  srsData: any,
  answers: Record<string, string>
): Promise<any> {
  const response = await authFetch(`${BASE_URL}/workflow/clarity/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ srs_data: srsData, answers }),
  });

  if (!response.ok) {
    throw new Error(`Apply clarity answers failed: ${response.status}`);
  }

  return response.json();
}

// ─── Regeneration API Functions ──────────────────────────────────────────────

export async function regenerateBundle(
  bundleId: string,
  errorInput: string,
  source: string
): Promise<RegenerationResult> {
  const response = await authFetch(`${BASE_URL}/bundle/${bundleId}/regenerate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ error_input: errorInput, source }),
  });

  if (!response.ok) {
    throw new Error(`Bundle regeneration failed: ${response.status}`);
  }

  return response.json();
}

// ─── Document Extractor API Functions ────────────────────────────────────────

export async function extractDocument(file: File): Promise<ProcessDocumentResult> {
  const formData = new FormData();
  formData.append('file', file);
  const [signal, cleanup] = withTimeout(REQUEST_TIMEOUT_MS);
  try {
    const response = await authFetch(`${BASE_URL}/document/extract`, {
      method: 'POST',
      body: formData,
      signal,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Extract failed: ${response.status}` }));
      throw new Error(err.detail || `Extract failed: ${response.status}`);
    }
    return response.json();
  } finally {
    cleanup();
  }
}

export async function processDocument(file: File, orgName?: string): Promise<ProcessDocumentResult> {
  const formData = new FormData();
  formData.append('file', file);
  if (orgName) {
    formData.append('org_name', orgName);
  }
  const [signal, cleanup] = withTimeout(REQUEST_TIMEOUT_MS);
  try {
    const response = await authFetch(`${BASE_URL}/document/process`, {
      method: 'POST',
      body: formData,
      signal,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Process failed: ${response.status}` }));
      throw new Error(err.detail || `Process failed: ${response.status}`);
    }
    return response.json();
  } finally {
    cleanup();
  }
}

export async function processDocumentText(text: string, title?: string, orgName?: string): Promise<ProcessDocumentResult> {
  const formData = new FormData();
  formData.append('text', text);
  if (title) formData.append('title', title);
  if (orgName) formData.append('org_name', orgName);
  const [signal, cleanup] = withTimeout(REQUEST_TIMEOUT_MS);
  try {
    const response = await authFetch(`${BASE_URL}/document/process`, {
      method: 'POST',
      body: formData,
      signal,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: `Process failed: ${response.status}` }));
      throw new Error(err.detail || `Process failed: ${response.status}`);
    }
    return response.json();
  } finally {
    cleanup();
  }
}

export async function validateAndFix(bundleId: string): Promise<any> {
  const response = await authFetch(`${BASE_URL}/bundle/${bundleId}/validate-and-fix`, {
    method: 'POST',
  });

  if (!response.ok) {
    throw new Error(`Validate and fix failed: ${response.status}`);
  }

  return response.json();
}
