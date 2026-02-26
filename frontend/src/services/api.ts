import type { Attachment, SSEEvent, RuleTestResult } from '../types';

const BASE_URL = '/api';

export async function streamChat(
  message: string,
  sessionId: string,
  attachments: Attachment[] | undefined,
  onChunk: (event: SSEEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void
): Promise<void> {
  try {
    const response = await fetch(`${BASE_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        sessionId,
        attachments: attachments?.map(a => ({
          type: a.type,
          name: a.name,
          data: a.data,
          mimeType: a.mimeType,
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
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}

export async function mapVoice(
  transcript: string,
  formJson: Record<string, unknown>,
  language: string
): Promise<{ fields: Record<string, unknown>; confidence: Record<string, number>; unmapped_text: string }> {
  const response = await fetch(`${BASE_URL}/voice/map`, {
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

  const response = await fetch(`${BASE_URL}/image/extract`, {
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
  const response = await fetch(`${BASE_URL}/bundle/generate`, {
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
  const response = await fetch(`${BASE_URL}/bundle/${bundleId}/download`);

  if (!response.ok) {
    throw new Error(`Bundle download failed: ${response.status}`);
  }

  return response.blob();
}

export async function saveObservations(
  fields: Record<string, unknown>
): Promise<{ success: boolean; message: string }> {
  const response = await fetch(`${BASE_URL}/avni/save-observations`, {
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
  const response = await fetch(`${BASE_URL}/rules/test`, {
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
  const response = await fetch(`${BASE_URL}/knowledge/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  if (!response.ok) {
    throw new Error(`Knowledge search failed: ${response.status}`);
  }

  return response.json();
}
