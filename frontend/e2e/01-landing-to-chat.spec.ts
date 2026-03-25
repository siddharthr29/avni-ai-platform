import { test, expect } from '@playwright/test';
import { registerAndLogin } from './helpers/auth';

test.describe('Landing page to Chat flow', () => {
  test('shows landing page with hero text and feature cards', async ({ page }) => {
    await page.goto('/');

    // Hero section is visible
    await expect(page.getByText('Set up your Avni app')).toBeVisible();
    await expect(page.getByText('in hours, not weeks')).toBeVisible();
    await expect(
      page.getByText('Upload your scoping sheet, chat about requirements'),
    ).toBeVisible();

    // CTA buttons visible
    await expect(page.getByRole('button', { name: 'Get Started' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' }).first()).toBeVisible();

    // Feature cards visible
    await expect(page.getByText('Generate Bundles')).toBeVisible();
    await expect(page.getByText('Chat with AI')).toBeVisible();
    await expect(page.getByText('Write Rules')).toBeVisible();
  });

  test('Sign In navigates to login form', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Sign In' }).first().click();

    // Should see the profile picker / login form
    await expect(page.getByText('Sign in to Avni AI')).toBeVisible();
    await expect(page.getByLabel('Email')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('Get Started navigates to login form', async ({ page }) => {
    await page.goto('/');

    await page.getByRole('button', { name: 'Get Started' }).click();

    // Should see the profile picker / login form
    await expect(page.getByText('Sign in to Avni AI')).toBeVisible();
  });

  test('can switch to registration mode and see extra fields', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Sign In' }).first().click();

    // Switch to register mode
    await page.getByText("Don't have an account? Register").click();

    await expect(page.getByText('Create Account')).toBeVisible();
    await expect(page.getByLabel('Your Name')).toBeVisible();
    await expect(page.getByLabel('Organisation Name')).toBeVisible();
    await expect(page.getByLabel('Sector')).toBeVisible();
  });

  test('full registration flow reaches the chat interface', async ({ page }) => {
    // Mock the registration API so we don't need a real backend
    await page.route('**/api/auth/register', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'test-user-id',
          email: 'priya@example.org',
          name: 'Priya Sharma',
          orgName: 'Test NGO',
          sector: 'Maternal & Child Health (MCH)',
          role: 'ngo_user',
          token: 'mock-token',
        }),
      });
    });

    // Mock health endpoint so chat shows "connected"
    await page.route('**/api/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ok' }),
      });
    });

    await registerAndLogin(page, {
      name: 'Priya Sharma',
      email: 'priya@example.org',
      password: 'testpass123',
      org: 'Test NGO',
      sector: 'Maternal & Child Health (MCH)',
    });

    // Chat interface should load — look for the empty state greeting or input
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')).or(
        page.getByPlaceholder('Type a message'),
      ),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('can type and send a message in chat', async ({ page }) => {
    // Mock APIs
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

    // Mock chat endpoint to return a streamed response
    await page.route('**/api/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'data: {"content":"Avni is an open-source platform for field data collection."}\n\ndata: [DONE]\n\n',
      });
    });

    await registerAndLogin(page);

    // Wait for chat empty state to appear
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')),
    ).toBeVisible({ timeout: 10_000 });

    // Type a message
    const input = page.getByPlaceholder('Type a message');
    await input.fill('What is Avni?');

    // Send message (press Enter)
    await input.press('Enter');

    // Verify the user message appears in the chat
    await expect(page.getByText('What is Avni?')).toBeVisible({ timeout: 5_000 });
  });
});
