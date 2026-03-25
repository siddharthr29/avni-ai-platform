import { test, expect } from '@playwright/test';
import { registerAndLogin } from './helpers/auth';

test.describe('Error handling and edge cases', () => {
  test('navigating to unknown route shows the app (SPA fallback)', async ({ page }) => {
    await page.goto('/this-page-does-not-exist');

    // Since this is a SPA with no router, it should show the landing page
    // or at least not a blank screen
    await expect(
      page.getByText('Set up your Avni app').or(page.getByText('Avni AI')),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('chat handles API errors gracefully', async ({ page }) => {
    // Mock auth to succeed
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-id',
          email: 'test@example.org',
          name: 'Test User',
          orgName: 'Test NGO',
          sector: 'Maternal & Child Health (MCH)',
          role: 'ngo_user',
          token: 'mock-token',
        }),
      });
    });

    await page.route('**/api/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    // Mock chat endpoint to return a server error
    await page.route('**/api/chat', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Internal server error: LLM provider unavailable' }),
      });
    });

    await registerAndLogin(page);

    // Wait for chat to load
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')),
    ).toBeVisible({ timeout: 10_000 });

    // Send a message
    const input = page.getByPlaceholder('Type a message');
    await input.fill('Hello');
    await input.press('Enter');

    // Wait and check that the app doesn't crash — it should show an error message
    // or at least remain interactive (no blank screen)
    await page.waitForTimeout(2_000);
    await expect(input).toBeVisible();

    // Check that the page didn't crash to a blank screen
    const bodyText = await page.locator('body').innerText();
    expect(bodyText.length).toBeGreaterThan(0);
  });

  test('backend offline shows disconnected status', async ({ page }) => {
    // Mock auth
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-id',
          email: 'test@example.org',
          name: 'Test User',
          orgName: 'Test NGO',
          sector: 'Maternal & Child Health (MCH)',
          role: 'ngo_user',
          token: 'mock-token',
        }),
      });
    });

    // Mock health endpoint to fail (backend offline)
    await page.route('**/api/health', async (route) => {
      await route.abort('connectionrefused');
    });

    await registerAndLogin(page);

    // Wait for chat to load
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')),
    ).toBeVisible({ timeout: 10_000 });

    // Should show "Offline" indicator
    await expect(page.getByText('Offline')).toBeVisible({ timeout: 10_000 });
  });

  test('empty chat state shows suggestions', async ({ page }) => {
    // Mock auth
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-id',
          email: 'test@example.org',
          name: 'Test User',
          orgName: 'Test NGO',
          sector: 'Maternal & Child Health (MCH)',
          role: 'ngo_user',
          token: 'mock-token',
        }),
      });
    });

    await page.route('**/api/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await registerAndLogin(page);

    // Wait for chat to load
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')),
    ).toBeVisible({ timeout: 10_000 });

    // Empty state should show suggestion categories
    await expect(page.getByText('Build')).toBeVisible();
    await expect(page.getByText('Learn')).toBeVisible();
    await expect(page.getByText('Support')).toBeVisible();

    // Should show specific suggestion cards
    await expect(page.getByText('Generate an implementation bundle from SRS')).toBeVisible();
    await expect(page.getByText('Explain Avni concepts')).toBeVisible();
  });

  test('login form shows validation — submit disabled without required fields', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Sign In' }).first().click();

    // Without filling fields, the submit button should be disabled
    const submitBtn = page.getByRole('button', { name: 'Sign In' });
    await expect(submitBtn).toBeDisabled();

    // Fill email only — still disabled (password missing)
    await page.getByLabel('Email').fill('test@example.org');
    await expect(submitBtn).toBeDisabled();

    // Fill password too — now enabled
    await page.getByLabel('Password').fill('testpass');
    await expect(submitBtn).toBeEnabled();
  });

  test('registration form requires all fields', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Sign In' }).first().click();
    await page.getByText("Don't have an account? Register").click();

    const submitBtn = page.getByRole('button', { name: 'Create Account' });

    // Initially disabled
    await expect(submitBtn).toBeDisabled();

    // Fill only email and password — still disabled (name, org, sector required)
    await page.getByLabel('Email').fill('test@example.org');
    await page.getByLabel('Password').fill('testpass123');
    await expect(submitBtn).toBeDisabled();

    // Fill name
    await page.getByLabel('Your Name').fill('Test User');
    await expect(submitBtn).toBeDisabled();

    // Fill org
    await page.getByLabel('Organisation Name').fill('Test Org');
    await expect(submitBtn).toBeDisabled();

    // Select sector — now all required fields filled
    await page.getByLabel('Sector').selectOption('Education');
    await expect(submitBtn).toBeEnabled();
  });

  test('auth error displays error message', async ({ page }) => {
    // Mock login to return an error
    await page.route('**/api/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid email or password' }),
      });
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Sign In' }).first().click();

    await page.getByLabel('Email').fill('wrong@example.org');
    await page.getByLabel('Password').fill('wrongpass');
    await page.getByRole('button', { name: 'Sign In' }).click();

    // Error message should appear
    await expect(
      page.getByText(/invalid|error|failed|wrong/i),
    ).toBeVisible({ timeout: 5_000 });
  });
});
