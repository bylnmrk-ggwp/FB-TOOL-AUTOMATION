import { expect, test, type Page } from '@playwright/test';

/**
 * Each test names its own account, so a run leaves no state that the next test
 * has to account for, and a failure names the test that produced it.
 */
const uniqueName = (prefix: string): string => `${prefix} ${Date.now().toString(36)}`;

const createAccount = async (page: Page, name: string): Promise<void> => {
  await page.goto('/accounts');
  await page.getByRole('button', { name: 'Add account' }).first().click();

  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Name', { exact: true }).fill(name);
  await dialog.getByRole('button', { name: 'Create account' }).click();

  await expect(dialog).toBeHidden();
  await expect(page.getByRole('cell', { name, exact: true })).toBeVisible();
};

/** Row actions live in a menu; open it and pick one. */
const rowAction = async (page: Page, name: string, item: string): Promise<void> => {
  await page
    .getByRole('row', { name: new RegExp(name) })
    .getByRole('button', { name: /More actions/ })
    .click();
  await page.getByRole('menuitem', { name: item, exact: true }).click();
};

const deleteAccount = async (page: Page, name: string): Promise<void> => {
  await rowAction(page, name, 'Delete');

  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Delete account' }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole('cell', { name, exact: true })).toBeHidden();
};

test.describe('Shell', () => {
  test('loads the dashboard and reports the API as reachable', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Connected')).toBeVisible();
    await expect(page.getByText('Database up')).toBeVisible();
    await expect(page.getByText('Queue up')).toBeVisible();
  });

  test('navigates to every page', async ({ page }) => {
    await page.goto('/');

    for (const [label, heading] of [
      ['Accounts', 'Accounts'],
      ['Groups', 'Groups'],
      ['Compose', 'Compose'],
      ['Queue', 'Queue'],
      ['Monitor', 'Monitor'],
      ['Logs', 'Logs'],
      ['Settings', 'Settings'],
    ] as const) {
      // Scoped to the sidebar: the dashboard figures are links with the same names.
      await page
        .getByRole('navigation', { name: 'Main' })
        .getByRole('link', { name: label })
        .click();
      await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible();
    }
  });

  test('remembers the chosen theme across a reload', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'Switch to light theme' }).click();
    await expect(page.locator('html')).not.toHaveClass(/dark/);

    await page.reload();
    await expect(page.locator('html')).not.toHaveClass(/dark/);

    await page.getByRole('button', { name: 'Switch to dark theme' }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);
  });
});

test.describe('Accounts', () => {
  test('creates, edits, disables and deletes an account', async ({ page }) => {
    const name = uniqueName('E2E Account');
    await createAccount(page, name);

    const row = page.getByRole('row', { name: new RegExp(name) });
    await expect(row.getByText('offline')).toBeVisible();

    await rowAction(page, name, 'Disable');
    await expect(row.getByText('Disabled', { exact: true })).toBeVisible();

    await rowAction(page, name, 'Enable');
    await expect(row.getByText('Disabled', { exact: true })).toBeHidden();

    await rowAction(page, name, 'Edit');
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Display name').fill('Renamed by the test');
    await dialog.getByRole('button', { name: 'Save changes' }).click();
    await expect(dialog).toBeHidden();
    await expect(row.getByText('Renamed by the test')).toBeVisible();

    await deleteAccount(page, name);
  });

  test('refuses a duplicate name with the server message', async ({ page }) => {
    const name = uniqueName('E2E Duplicate');
    await createAccount(page, name);

    await page.getByRole('button', { name: 'Add account' }).first().click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Name', { exact: true }).fill(name);
    await dialog.getByRole('button', { name: 'Create account' }).click();

    await expect(dialog.getByRole('alert')).toContainText('already exists');
    await dialog.getByRole('button', { name: 'Cancel' }).click();

    await deleteAccount(page, name);
  });

  test('filters the list by search', async ({ page }) => {
    const name = uniqueName('E2E Searchable');
    await createAccount(page, name);

    await page.getByLabel('Search', { exact: true }).fill('nothing-matches-this');
    await expect(page.getByText('Nothing matches')).toBeVisible();

    await page.getByLabel('Search', { exact: true }).fill(name);
    await expect(page.getByRole('cell', { name, exact: true })).toBeVisible();

    await page.getByLabel('Search', { exact: true }).fill('');
    await deleteAccount(page, name);
  });
});

test.describe('Compose', () => {
  test('will not queue work without an account chosen', async ({ page }) => {
    await page.goto('/compose');

    await page.getByLabel('Type').selectOption('create_post');
    await page.getByLabel('Text', { exact: true }).fill('A post that should not be queued');
    await page.getByRole('button', { name: 'Queue work' }).click();

    await expect(page.getByRole('alert')).toContainText('Choose at least one account');
  });

  test('queues a job and shows it on the Queue page', async ({ page }) => {
    const name = uniqueName('E2E Compose');
    await createAccount(page, name);

    await page.goto('/compose');
    await page.getByLabel('Type').selectOption('create_post');
    await page.getByLabel('Text', { exact: true }).fill('Queued by an end-to-end test');
    await page.getByRole('checkbox', { name }).click();
    await page.getByRole('button', { name: 'Queue work' }).click();

    // Composing navigates to the queue once the jobs are written.
    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
    await expect(page.getByRole('cell', { name: /Create post/ }).first()).toBeVisible();

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });
});

test.describe('Settings', () => {
  test('saves a changed setting and reads it back', async ({ page }) => {
    await page.goto('/settings');

    await page.getByLabel('Global concurrency').fill('3');
    await page.getByRole('button', { name: 'Save settings' }).click();
    await expect(page.getByText('Settings saved')).toBeVisible();

    await page.reload();
    await expect(page.getByLabel('Global concurrency')).toHaveValue('3');

    await page.getByLabel('Global concurrency').fill('2');
    await page.getByRole('button', { name: 'Save settings' }).click();
    await expect(page.getByText('Settings saved')).toBeVisible();
  });

  test('reports a setting the server refuses', async ({ page }) => {
    await page.goto('/settings');

    await page.getByLabel('Between steps, from (seconds)').fill('9');
    await page.getByLabel('Between steps, to (seconds)').fill('1');
    await page.getByRole('button', { name: 'Save settings' }).click();

    await expect(page.getByRole('alert')).toContainText('minActionDelayMs');
  });
});

test.describe('Logs', () => {
  test('shows what the server wrote and filters by level', async ({ page }) => {
    const name = uniqueName('E2E Logged');
    await createAccount(page, name);

    await page.goto('/logs');
    await expect(page.getByRole('cell', { name: 'account.created' }).first()).toBeVisible();

    await page.getByLabel('Level').selectOption('error');
    await expect(page.getByRole('cell', { name: 'account.created' })).toHaveCount(0);

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });
});
