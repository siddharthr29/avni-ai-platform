import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// We need to mock fetch before importing the module
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock });

// Import after mocks are set up
import {
  authFetch,
  fetchAdminUsers,
  fetchPlatformStats,
  streamChat,
  generateBundle,
  downloadBundle,
  searchKnowledge,
  testRule,
  deleteUser,
  updateUserRole,
} from '../api';

describe('api service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.clear();
  });

  describe('getAuthHeaders (via authFetch)', () => {
    it('adds Authorization header when token is in localStorage', async () => {
      localStorageMock.setItem(
        'avni-ai-user-profile',
        JSON.stringify({ accessToken: 'test-token-123' }),
      );
      mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }));

      await authFetch('/api/test');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/test',
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token-123',
          }),
        }),
      );
    });

    it('does not add Authorization header when no token in localStorage', async () => {
      mockFetch.mockResolvedValueOnce(new Response('{}', { status: 200 }));

      await authFetch('/api/test');

      const calledHeaders = mockFetch.mock.calls[0][1]?.headers ?? {};
      expect(calledHeaders).not.toHaveProperty('Authorization');
    });
  });

  describe('authFetch retry on 401', () => {
    it('retries with new token on 401 when refresh succeeds', async () => {
      localStorageMock.setItem(
        'avni-ai-user-profile',
        JSON.stringify({ accessToken: 'old-token', refreshToken: 'refresh-tok' }),
      );

      // First call returns 401
      mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }));
      // Refresh call succeeds
      mockFetch.mockResolvedValueOnce(
        new Response(
          JSON.stringify({ access_token: 'new-token', refresh_token: 'new-refresh' }),
          { status: 200 },
        ),
      );
      // Retry call succeeds
      mockFetch.mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));

      const response = await authFetch('/api/protected');

      expect(response.status).toBe(200);
      // Should have made 3 fetch calls: original, refresh, retry
      expect(mockFetch).toHaveBeenCalledTimes(3);
    });

    it('returns 401 response when refresh fails', async () => {
      localStorageMock.setItem(
        'avni-ai-user-profile',
        JSON.stringify({ accessToken: 'old-token', refreshToken: 'bad-refresh' }),
      );

      mockFetch.mockResolvedValueOnce(new Response('', { status: 401 }));
      mockFetch.mockResolvedValueOnce(new Response('', { status: 401 })); // refresh fails

      const response = await authFetch('/api/protected');
      expect(response.status).toBe(401);
    });
  });

  describe('fetchAdminUsers', () => {
    it('maps snake_case response to camelCase', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            users: [
              {
                id: 'u1',
                name: 'Test User',
                email: 'test@org.com',
                org_name: 'TestOrg',
                sector: 'Health',
                role: 'implementor',
                is_active: true,
                last_login: '2024-01-01',
                created_at: '2024-01-01',
              },
            ],
            count: 1,
          }),
          { status: 200 },
        ),
      );

      const result = await fetchAdminUsers();

      expect(result.users[0]).toEqual(
        expect.objectContaining({
          id: 'u1',
          name: 'Test User',
          orgName: 'TestOrg',
          isActive: true,
          lastLogin: '2024-01-01',
          createdAt: '2024-01-01',
        }),
      );
      expect(result.total).toBe(1);
    });

    it('builds query string from filters', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ users: [], count: 0 }), { status: 200 }),
      );

      await fetchAdminUsers({ search: 'alice', role: 'implementor', isActive: true });

      const url = mockFetch.mock.calls[0][0] as string;
      expect(url).toContain('search=alice');
      expect(url).toContain('role=implementor');
      expect(url).toContain('is_active=true');
    });
  });

  describe('fetchPlatformStats', () => {
    it('maps snake_case response to camelCase', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            total_users: 100,
            active_users: 80,
            users_by_role: { implementor: 50 },
            users_by_org: { OrgA: 30 },
            total_sessions: 200,
            messages_24h: 10,
            messages_7d: 50,
            messages_30d: 200,
          }),
          { status: 200 },
        ),
      );

      const result = await fetchPlatformStats();

      expect(result.totalUsers).toBe(100);
      expect(result.activeUsers).toBe(80);
      expect(result.totalSessions).toBe(200);
      expect(result.recentMessages24h).toBe(10);
      expect(result.recentMessages7d).toBe(50);
      expect(result.recentMessages30d).toBe(200);
      expect(result.usersByRole).toEqual({ implementor: 50 });
      expect(result.usersByOrg).toEqual({ OrgA: 30 });
    });
  });

  describe('error handling', () => {
    it('generateBundle throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce(new Response('', { status: 500 }));

      await expect(generateBundle({})).rejects.toThrow(/Bundle generation failed: 500/);
    });

    it('downloadBundle throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce(new Response('', { status: 404 }));

      await expect(downloadBundle('bad-id')).rejects.toThrow(
        /Bundle download failed: 404/,
      );
    });

    it('searchKnowledge throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce(new Response('', { status: 503 }));

      await expect(searchKnowledge('test query')).rejects.toThrow(
        /Knowledge search failed: 503/,
      );
    });

    it('testRule throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce(new Response('', { status: 400 }));

      await expect(testRule('code', 'ViewFilter')).rejects.toThrow(
        /Rule test failed: 400/,
      );
    });

    it('deleteUser throws on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce(new Response('', { status: 403 }));

      await expect(deleteUser('user-1')).rejects.toThrow(/Delete user failed: 403/);
    });

    it('updateUserRole sends PATCH with correct body', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ success: true }), { status: 200 }),
      );

      await updateUserRole('user-1', 'org_admin');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/admin/users/user-1/role',
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ role: 'org_admin' }),
        }),
      );
    });
  });

  describe('streamChat', () => {
    it('calls onDone when stream ends with [DONE]', async () => {
      const encoder = new TextEncoder();
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode('data: {"type":"text","content":"Hello"}\n\n'),
          );
          controller.enqueue(encoder.encode('data: [DONE]\n\n'));
          controller.close();
        },
      });

      mockFetch.mockResolvedValueOnce(
        new Response(stream, { status: 200 }),
      );

      const onChunk = vi.fn();
      const onDone = vi.fn();
      const onError = vi.fn();

      await streamChat('test', 'session-1', undefined, onChunk, onDone, onError);

      expect(onChunk).toHaveBeenCalledWith(
        expect.objectContaining({ type: 'text', data: 'Hello' }),
      );
      expect(onDone).toHaveBeenCalled();
      expect(onError).not.toHaveBeenCalled();
    });

    it('calls onError when fetch fails', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response('', { status: 500, statusText: 'Internal Server Error' }),
      );

      const onChunk = vi.fn();
      const onDone = vi.fn();
      const onError = vi.fn();

      await streamChat('test', 'session-1', undefined, onChunk, onDone, onError);

      expect(onError).toHaveBeenCalledWith(
        expect.objectContaining({
          message: expect.stringContaining('500'),
        }),
      );
    });
  });

  describe('request body formatting', () => {
    it('searchKnowledge sends correct body', async () => {
      mockFetch.mockResolvedValueOnce(
        new Response(JSON.stringify({ results: [] }), { status: 200 }),
      );

      await searchKnowledge('how to create forms');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/knowledge/search',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ query: 'how to create forms' }),
        }),
      );
    });
  });
});
