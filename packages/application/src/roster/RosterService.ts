import {
  cleanUsername,
  WorkbookInvalidError,
  type ImportAccountsResult,
  type RosterRow,
} from '@fb/shared';
import type { Logger } from '../ports/Logger.js';
import type { RosterSource } from '../ports/Sessions.js';
import type { AccountService } from '../accounts/AccountService.js';

/**
 * Header labels as they appear on the roster, mapped to the fields they fill.
 * Matched by label, never by position, so the sheet can be reordered.
 */
const HEADERS = {
  facebookName: ['FACEBOOK NAME', 'NAME'],
  username: ['USERNAME', 'EMAIL', 'USER'],
  password: ['PASSWORD', 'PASS'],
  gmail: ['GMAIL', 'GMAIL ACCOUNT'],
  gmailPassword: ['PASS FOR GMAIL', 'GMAIL PASSWORD', 'GMAIL PASS'],
  phone: ['NUMBER', 'PHONE', 'MOBILE'],
  proxy: ['PROXY', 'PROXIES', 'IP'],
  // A blank or numeric label counts only in the first column; see mapHeaders.
  sheetNo: ['NO', 'NO.', '#'],
} as const;

type Field = keyof typeof HEADERS;

/** Column index for each field, or absent when the header is not on the sheet. */
export const mapHeaders = (header: readonly string[]): Partial<Record<Field, number>> => {
  const out: Partial<Record<Field, number>> = {};
  header.forEach((cell, index) => {
    const label = cell.trim().toUpperCase();
    for (const [field, labels] of Object.entries(HEADERS) as [Field, readonly string[]][]) {
      if (out[field] === undefined && labels.includes(label)) out[field] = index;
    }
  });
  // A blank or numeric first header is the row-number column on the sheet
  // this was written for (Google's CSV export turns its label into "0");
  // only the very first column may claim it that way.
  if (out.sheetNo === undefined && /^\d*$/.test(header[0]?.trim() ?? '')) out.sheetNo = 0;
  return out;
};

const cell = (row: readonly string[], index: number | undefined): string =>
  index === undefined ? '' : (row[index] ?? '').trim();

const orNull = (value: string): string | null => (value === '' ? null : value);

/**
 * Sheet rows -> roster rows. Column A (the row number) is the key an import
 * matches on. Only rows with both a username and a password count; the rest
 * are headings, notes, empty lines or slots not filled in yet.
 */
export const parseRoster = (rows: readonly (readonly string[])[]): RosterRow[] => {
  const header = rows[0];
  if (header === undefined) throw new WorkbookInvalidError('the sheet is empty');

  const columns = mapHeaders(header);
  if (columns.username === undefined) {
    throw new WorkbookInvalidError(
      `no USERNAME column; the header row is ${JSON.stringify(header)}`,
    );
  }

  const parsed: RosterRow[] = [];
  rows.slice(1).forEach((row) => {
    const username = cleanUsername(cell(row, columns.username));
    const password = cell(row, columns.password);
    // A row counts only when it can sign in: username and password both
    // present. Anything else is a heading, a note, or a slot not filled yet.
    if (username === '' || password === '') return;

    const numbered = Number.parseInt(cell(row, columns.sheetNo), 10);
    // A name that is only digits is a placeholder on the sheet, not a name.
    const facebookName = cell(row, columns.facebookName);
    parsed.push({
      sheetNo: Number.isFinite(numbered) ? numbered : null,
      facebookName: /^\d*$/.test(facebookName) ? null : facebookName,
      username,
      password,
      gmail: orNull(cell(row, columns.gmail)),
      gmailPassword: orNull(cell(row, columns.gmailPassword)),
      phone: orNull(cell(row, columns.phone)),
      proxyUrl: orNull(cell(row, columns.proxy)),
    });
  });

  return parsed;
};

/**
 * Pulls the roster in and reconciles it with the accounts table. The row
 * number is the key; a row already known updates its roster fields and
 * leaves everything this machine owns — status, profile, login verdict —
 * untouched.
 */
export class RosterService {
  constructor(
    private readonly accounts: AccountService,
    private readonly logger: Logger,
  ) {}

  async importFrom(source: RosterSource): Promise<ImportAccountsResult & { rows: number }> {
    const rows = await source.readRows();
    const roster = parseRoster(rows);

    this.logger.info(`Read ${roster.length} roster row(s) from ${source.describe()}`, {
      event: 'roster.read',
      rows: roster.length,
    });

    const result = await this.accounts.importRoster(roster);
    this.logger.info(
      `Roster import: ${result.created} created, ${result.updated} updated, ${result.removed} removed, ${result.skipped.length} skipped`,
      { event: 'roster.imported' },
    );
    return { ...result, rows: roster.length };
  }
}
