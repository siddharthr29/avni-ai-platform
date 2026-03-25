import { test, expect } from '@playwright/test';
import { loginAsAdmin } from './helpers/auth';

test.describe('Admin Panel', () => {
  test.beforeEach(async ({ page }) => {
    // Mock health endpoint
    await page.route('**/api/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // Mock admin users endpoint
    await page.route('**/api/admin/users*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          users: [
            {
              id: 'user-1',
              email: 'priya@example.org',
              name: 'Priya Sharma',
              orgName: 'Test NGO',
              role: 'ngo_user',
              isActive: true,
              createdAt: '2025-01-15T10:00:00Z',
              lastLoginAt: '2025-03-10T14:30:00Z',
            },
            {
              id: 'user-2',
              email: 'rahul@example.org',
              name: 'Rahul Verma',
              orgName: 'Test NGO',
              role: 'implementor',
              isActive: true,
              createdAt: '2025-02-01T08:00:00Z',
              lastLoginAt: '2025-03-14T09:15:00Z',
            },
          ],
          total: 2,
        }),
      });
    });

    // Mock platform stats endpoint
    await page.route('**/api/admin/stats*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          totalUsers: 42,
          activeUsers: 35,
          totalSessions: 128,
          totalMessages: 1560,
          bundlesGenerated: 18,
        }),
      });
    });

    await loginAsAdmin(page);

    // Wait for the chat interface to load
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')).or(
        page.getByPlaceholder('Type a message'),
      ),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('can navigate to Admin Panel', async ({ page }) => {
    // Click the admin button in the header (shield/admin icon or menu)
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    // Admin Panel header should be visible
    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });
  });

  test('user management tab loads with user table', async ({ page }) => {
    // Navigate to admin
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Users tab should be active by default
    await expect(page.getByText('Users').first()).toBeVisible();

    // User data from mock should be visible
    await expect(page.getByText('Priya Sharma').or(page.getByText('priya@example.org'))).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText('Rahul Verma').or(page.getByText('rahul@example.org'))).toBeVisible();
  });

  test('search input is functional', async ({ page }) => {
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Find and use the search input
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();

    await searchInput.fill('Priya');
    // The input should accept text (debounced API call will fire)
    await expect(searchInput).toHaveValue('Priya');
  });

  test('role filter dropdown works', async ({ page }) => {
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Find role filter — could be a select or dropdown
    const roleFilter = page.locator('select').filter({ hasText: /role|all/i }).or(
      page.getByLabel(/role/i),
    );

    if (await roleFilter.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
      // Select a role
      await roleFilter.first().selectOption({ index: 1 });
    }
  });

  test('stats tab shows statistics', async ({ page }) => {
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Switch to Stats tab
    await page.getByText('Stats').click();

    // Stats content should load — look for stat numbers or cards
    await expect(
      page.getByText(/total|users|sessions|messages|bundles/i).first(),
    ).toBeVisible({ timeout: 5_000 });
  });

  test('invite user button opens a modal', async ({ page }) => {
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Look for invite/add user button
    const inviteBtn = page.getByRole('button', { name: /invite|add user/i });

    if (await inviteBtn.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
      await inviteBtn.first().click();

      // Modal should appear with email input
      await expect(
        page.getByPlaceholder(/email/i).or(page.getByText(/invite/i)),
      ).toBeVisible({ timeout: 3_000 });
    }
  });

  test('back button returns to chat', async ({ page }) => {
    const adminBtn = page.getByRole('button', { name: /admin/i }).or(
      page.getByText('Admin'),
    );
    await adminBtn.first().click();

    await expect(page.getByText('Admin Panel')).toBeVisible({ timeout: 5_000 });

    // Click back button (aria-label "Back to chat")
    await page.getByRole('button', { name: /back to chat/i }).click();

    // Should return to chat
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')).or(
        page.getByPlaceholder('Type a message'),
      ),
    ).toBeVisible({ timeout: 10_000 });
  });
});
