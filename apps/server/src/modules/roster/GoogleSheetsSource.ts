import { createSign } from 'node:crypto';
import { access, readFile } from 'node:fs/promises';
import { z } from 'zod';
import { WorkbookInvalidError } from '@fb/shared';
import type { RosterSource } from '@fb/application';
import { parseCsv } from './CsvSource.js';

const ServiceAccountSchema = z.object({
  client_email: z.string().email(),
  private_key: z.string().min(1),
  token_uri: z.string().url().default('https://oauth2.googleapis.com/token'),
});

const TokenResponseSchema = z.object({
  access_token: z.string(),
  expires_in: z.number(),
});

const ValuesResponseSchema = z.object({
  values: z.array(z.array(z.string().or(z.number()).or(z.boolean()))).default([]),
});

const SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly';

export interface GoogleSheetsOptions {
  keyFile: string;
  sheetId: string;
  tab: string;
}

/**
 * Reads the roster tab of a Google Sheet.
 *
 * With a service-account key on disk: one signed JWT is exchanged for an
 * hour-long access token; one GET reads the rows. Without one: the sheet is
 * read as CSV through the link-sharing route, which works for any sheet
 * shared with "anyone with the link". No client library: the calls are
 * small, and a dependency that pulls in a hundred more is the wrong trade.
 *
 * Credentials read through here — passwords included — are held in memory
 * for the length of the import and never logged.
 */
export class GoogleSheetsSource implements RosterSource {
  private token: { value: string; expiresAt: number } | null = null;

  constructor(private readonly options: GoogleSheetsOptions) {}

  describe(): string {
    return `Google Sheet ${this.options.sheetId} (${this.options.tab})`;
  }

  async readRows(): Promise<string[][]> {
    // No key on disk: the sheet may still be readable, if it is shared with
    // "anyone with the link". That path needs no credentials at all.
    if (!(await this.hasKeyFile())) return this.readPublicRows();

    const token = await this.accessToken();
    const range = encodeURIComponent(`${this.options.tab}!A1:Z`);
    const url = `https://sheets.googleapis.com/v4/spreadsheets/${this.options.sheetId}/values/${range}`;

    const response = await fetch(url, { headers: { authorization: `Bearer ${token}` } });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new WorkbookInvalidError(
        `Sheets API answered ${response.status}: ${body.slice(0, 200)}`,
      );
    }

    const parsed = ValuesResponseSchema.safeParse(await response.json());
    if (!parsed.success)
      throw new WorkbookInvalidError('the Sheets API response had an unexpected shape');
    return parsed.data.values.map((row) => row.map((cell) => String(cell)));
  }

  /**
   * The link-shared route: Google's visualisation endpoint hands out the tab
   * as CSV to anyone who can view the sheet. `headers=1` keeps the first row
   * as written — without it, a column of phone numbers loses its "NUMBER"
   * label because the label is not a number.
   *
   * A private sheet answers with a sign-in page instead of CSV, which is the
   * signal that a service-account key is needed after all.
   */
  private async readPublicRows(): Promise<string[][]> {
    const query = new URLSearchParams({
      tqx: 'out:csv',
      sheet: this.options.tab,
      headers: '1',
    });
    const url = `https://docs.google.com/spreadsheets/d/${this.options.sheetId}/gviz/tq?${query.toString()}`;

    const response = await fetch(url, { redirect: 'follow' });
    const type = response.headers.get('content-type') ?? '';
    if (!response.ok || !type.includes('text/csv')) {
      throw new WorkbookInvalidError(
        `the sheet is not shared by link and there is no service account key at ${this.options.keyFile}. ` +
          'Either share the sheet with "Anyone with the link can view", or place the key file there ' +
          '(or point SHEETS_SERVICE_ACCOUNT at it) and share the sheet with that account.',
      );
    }

    return parseCsv(await response.text());
  }

  private async hasKeyFile(): Promise<boolean> {
    try {
      await access(this.options.keyFile);
      return true;
    } catch {
      return false;
    }
  }

  private async accessToken(): Promise<string> {
    if (this.token !== null && this.token.expiresAt > Date.now() + 60_000) return this.token.value;

    const account = await this.serviceAccount();
    const now = Math.floor(Date.now() / 1000);
    const header = base64url(JSON.stringify({ alg: 'RS256', typ: 'JWT' }));
    const claims = base64url(
      JSON.stringify({
        iss: account.client_email,
        scope: SCOPE,
        aud: account.token_uri,
        iat: now,
        exp: now + 3600,
      }),
    );
    const signature = createSign('RSA-SHA256')
      .update(`${header}.${claims}`)
      .sign(account.private_key, 'base64url');
    const assertion = `${header}.${claims}.${signature}`;

    const response = await fetch(account.token_uri, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion,
      }),
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new WorkbookInvalidError(
        `Google refused the service account: ${response.status} ${body.slice(0, 200)}`,
      );
    }

    const parsed = TokenResponseSchema.safeParse(await response.json());
    if (!parsed.success)
      throw new WorkbookInvalidError('the token response had an unexpected shape');

    this.token = {
      value: parsed.data.access_token,
      expiresAt: Date.now() + parsed.data.expires_in * 1000,
    };
    return this.token.value;
  }

  private async serviceAccount(): Promise<z.infer<typeof ServiceAccountSchema>> {
    let raw: string;
    try {
      raw = await readFile(this.options.keyFile, 'utf8');
    } catch {
      throw new WorkbookInvalidError(
        `no service account key at ${this.options.keyFile}; set SHEETS_SERVICE_ACCOUNT or place the file there`,
      );
    }
    const parsed = ServiceAccountSchema.safeParse(JSON.parse(raw));
    if (!parsed.success)
      throw new WorkbookInvalidError('the service account file is not a Google key file');
    return parsed.data;
  }
}

const base64url = (value: string): string => Buffer.from(value, 'utf8').toString('base64url');
