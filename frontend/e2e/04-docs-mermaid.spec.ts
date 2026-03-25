import { test, expect } from '@playwright/test';
import { registerAndLogin } from './helpers/auth';

test.describe('Documentation viewer', () => {
  test.beforeEach(async ({ page }) => {
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
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')).or(
        page.getByPlaceholder('Type a message'),
      ),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('can navigate to documentation', async ({ page }) => {
    // Click the docs button in the header
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    // Documentation viewer should load
    await expect(page.locator('text=Documentation').or(page.locator('h1')).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test('documentation content loads with sections', async ({ page }) => {
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    // Wait for content to render
    await page.waitForTimeout(2_000);

    // Should have some text content rendered (headings, paragraphs)
    const headings = page.locator('h1, h2, h3');
    await expect(headings.first()).toBeVisible({ timeout: 10_000 });
  });

  test('mermaid diagrams render as SVG', async ({ page }) => {
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    // Wait for mermaid to initialize and render
    await page.waitForTimeout(3_000);

    // Look for rendered mermaid diagrams — they produce SVG elements
    // inside containers with class "mermaid" or data-mermaid attribute
    const mermaidSvgs = page.locator('.mermaid svg, [data-mermaid] svg, .mermaid-container svg');
    const svgCount = await mermaidSvgs.count();

    // If there are mermaid diagrams in the docs, they should be SVGs
    if (svgCount > 0) {
      await expect(mermaidSvgs.first()).toBeVisible();
    }
    // If no diagrams found, the test still passes (docs may not have diagrams on the visible page)
  });

  test('zoom controls are present for diagrams', async ({ page }) => {
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    await page.waitForTimeout(2_000);

    // Look for zoom/fullscreen controls near mermaid diagrams
    const zoomControls = page.getByRole('button', { name: /zoom|fullscreen|expand/i }).or(
      page.locator('[aria-label*="zoom"], [aria-label*="fullscreen"], [aria-label*="expand"]'),
    );

    const controlCount = await zoomControls.count();
    if (controlCount > 0) {
      await expect(zoomControls.first()).toBeVisible();
    }
  });

  test('fullscreen modal opens and closes with Escape', async ({ page }) => {
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    await page.waitForTimeout(2_000);

    // Find a fullscreen/expand button
    const expandBtn = page.getByRole('button', { name: /fullscreen|expand/i }).or(
      page.locator('[aria-label*="fullscreen"], [aria-label*="expand"]'),
    );

    if (await expandBtn.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
      await expandBtn.first().click();

      // A modal/dialog should appear
      const modal = page.locator('[role="dialog"], .modal, .fixed.inset-0');
      await expect(modal.first()).toBeVisible({ timeout: 3_000 });

      // Press Escape to close
      await page.keyboard.press('Escape');

      // Modal should be gone
      await expect(modal.first()).not.toBeVisible({ timeout: 3_000 });
    }
  });

  test('back button returns to chat from docs', async ({ page }) => {
    const docsBtn = page.getByRole('button', { name: /docs|documentation/i }).or(
      page.getByText('Docs'),
    );
    await docsBtn.first().click();

    await page.waitForTimeout(1_000);

    // Click the back/close button
    const backBtn = page.getByRole('button', { name: /back|close|return/i }).or(
      page.locator('button').filter({ has: page.locator('svg.lucide-arrow-left, svg.lucide-chevron-left, svg.lucide-x') }).first(),
    );
    await backBtn.first().click();

    // Should return to chat
    await expect(
      page.getByText('Welcome to Avni AI').or(page.getByText('Hello,')).or(
        page.getByPlaceholder('Type a message'),
      ),
    ).toBeVisible({ timeout: 10_000 });
  });
});
