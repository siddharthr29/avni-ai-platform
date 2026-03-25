import type { Page } from '@playwright/test';

interface LoginOptions {
  name?: string;
  email?: string;
  password?: string;
  org?: string;
  sector?: string;
  role?: 'ngo_user' | 'implementor' | 'org_admin' | 'platform_admin';
}

const DEFAULTS: Required<LoginOptions> = {
  name: 'Test User',
  email: 'test@example.org',
  password: 'testpass123',
  org: 'Test Organisation',
  sector: 'Maternal & Child Health (MCH)',
  role: 'ngo_user',
};

/**
 * Navigate to the landing page, click Sign In, fill the registration form,
 * and submit. After this the page should show the chat interface.
 */
export async function registerAndLogin(
  page: Page,
  opts: LoginOptions = {},
): Promise<void> {
  const { name, email, password, org, sector } = { ...DEFAULTS, ...opts };

  // Start from landing page
  await page.goto('/');

  // Click "Sign In" on the landing page header
  await page.getByRole('button', { name: 'Sign In' }).first().click();

  // We are now on the UserProfilePicker — switch to register mode
  await page.getByText("Don't have an account? Register").click();

  // Fill required fields
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByLabel('Your Name').fill(name);
  await page.getByLabel('Organisation Name').fill(org);
  await page.getByLabel('Sector').selectOption(sector);

  // Submit
  await page.getByRole('button', { name: 'Create Account' }).click();
}

/**
 * Sign in with existing credentials (no registration fields).
 */
export async function loginExisting(
  page: Page,
  opts: Pick<LoginOptions, 'email' | 'password'> = {},
): Promise<void> {
  const email = opts.email ?? DEFAULTS.email;
  const password = opts.password ?? DEFAULTS.password;

  await page.goto('/');
  await page.getByRole('button', { name: 'Sign In' }).first().click();

  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign In' }).click();
}

/**
 * Register as a platform_admin user for admin panel tests.
 * Uses a mock API response to set the role since the UI doesn't expose it.
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  // Mock the auth endpoint to return an admin profile
  await page.route('**/api/auth/register', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'admin-test-id',
        email: 'admin@example.org',
        name: 'Admin User',
        orgName: 'Test Organisation',
        sector: 'Education',
        role: 'platform_admin',
        token: 'mock-admin-token',
      }),
    });
  });

  await page.route('**/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'admin-test-id',
        email: 'admin@example.org',
        name: 'Admin User',
        orgName: 'Test Organisation',
        sector: 'Education',
        role: 'platform_admin',
        token: 'mock-admin-token',
      }),
    });
  });

  await registerAndLogin(page, {
    name: 'Admin User',
    email: 'admin@example.org',
    password: 'adminpass123',
    org: 'Test Organisation',
    sector: 'Education',
  });
}
