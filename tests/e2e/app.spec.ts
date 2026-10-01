import { expect, test, type Page } from '@playwright/test';

/**
 * Each test names its own account, so a run leaves no state that the next test
 * has to account for, and a failure names the test that produced it.
 */
const uniqueName = (prefix: string): string => `${prefix} ${Date.now().toString(36)}`;

/** The API the end-to-end web server talks to; the port is set in playwright.config.ts. */
const API_URL = 'http://127.0.0.1:3101';

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

    await page.getByLabel('Type').click();
    await page.getByRole('option', { name: 'Post text and photos' }).click();
    await page.getByLabel('Text', { exact: true }).fill('A post that should not be queued');
    await page.getByRole('button', { name: 'Queue work' }).click();

    await expect(page.getByRole('alert')).toContainText('Choose at least one account');
  });

  test('queues a job and shows it on the Queue page', async ({ page }) => {
    const name = uniqueName('E2E Compose');
    await createAccount(page, name);

    await page.goto('/compose');
    await page.getByLabel('Type').click();
    await page.getByRole('option', { name: 'Post text and photos' }).click();
    await page.getByLabel('Text', { exact: true }).fill('Queued by an end-to-end test');
    await page.getByRole('checkbox', { name }).click();
    await page.getByRole('button', { name: 'Queue work' }).click();

    // Composing navigates to the queue once the jobs are written.
    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
    await expect(page.getByRole('cell', { name: /Create post/ }).first()).toBeVisible();

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });

  test('comments and shares to the story as one share job', async ({ page }) => {
    const name = uniqueName('E2E Comment Story');
    await createAccount(page, name);

    await page.goto('/compose');
    await page.getByLabel('Type').click();
    await page.getByRole('option', { name: 'Comment on a post' }).click();
    await page.getByLabel('Post URL').fill('https://www.facebook.com/example/posts/1');
    await page.getByLabel('Text', { exact: true }).fill('Commented by an end-to-end test');
    await page.getByRole('radio', { name: 'Share to the story' }).click();
    await page.getByRole('checkbox', { name }).click();
    await page.getByRole('button', { name: 'Queue work' }).click();

    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
    await expect(page.getByRole('cell', { name: /Share post/ }).first()).toBeVisible();

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });

  test('comments then reacts as two jobs', async ({ page }) => {
    const name = uniqueName('E2E Comment React');
    await createAccount(page, name);

    await page.goto('/compose');
    await page.getByLabel('Type').click();
    await page.getByRole('option', { name: 'Comment on a post' }).click();
    await page.getByLabel('Post URL').fill('https://www.facebook.com/example/posts/2');
    await page.getByLabel('Text', { exact: true }).fill('Commented, then reacted');
    await page.getByRole('radio', { name: 'React to the post' }).click();
    await expect(page.getByLabel('Reaction')).toBeVisible();
    await page.getByRole('checkbox', { name }).click();
    await expect(page.getByText('2 jobs (comment + reaction)')).toBeVisible();
    await page.getByRole('button', { name: 'Queue work' }).click();

    await expect(page.getByRole('heading', { name: 'Queue', level: 1 })).toBeVisible();
    await expect(page.getByRole('cell', { name: /^Comment E2E/ }).first()).toBeVisible();
    await expect(page.getByRole('cell', { name: /^React to post E2E/ }).first()).toBeVisible();

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });

  test('filters the account card by login state', async ({ page }) => {
    // The filter row only appears once the roster is longer than a glance, so
    // nine accounts go in through the API rather than nine trips to the dialog.
    const prefix = uniqueName('E2E Filter');
    const names = Array.from({ length: 9 }, (_, index) => `${prefix} ${index + 1}`);
    const ids: string[] = [];
    for (const name of names) {
      const response = await page.request.post(`${API_URL}/api/v1/accounts`, { data: { name } });
      expect(response.ok()).toBeTruthy();
      ids.push(((await response.json()) as { id: string }).id);
    }

    await page.goto('/compose');
    await expect(page.getByRole('checkbox', { name: names[0] })).toBeVisible();

    // Nothing in a test database has ever signed in, so "Logged in" empties the card.
    await page.getByLabel('Login state').click();
    await page.getByRole('option', { name: 'Logged in' }).click();
    await expect(page.getByRole('checkbox', { name: names[0] })).toBeHidden();
    await expect(page.getByText('No account matches that filter.')).toBeVisible();

    await page.getByLabel('Login state').click();
    await page.getByRole('option', { name: 'Not checked' }).click();
    await expect(page.getByRole('checkbox', { name: names[0] })).toBeVisible();

    for (const id of ids) {
      expect((await page.request.delete(`${API_URL}/api/v1/accounts/${id}`)).ok()).toBeTruthy();
    }
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

    await page.getByLabel('Level').click();
    await page.getByRole('option', { name: /^error$/i }).click();
    await expect(page.getByRole('cell', { name: 'account.created' })).toHaveCount(0);

    await page.goto('/accounts');
    await deleteAccount(page, name);
  });
});
