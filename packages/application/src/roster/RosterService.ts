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
  sheetNo: ['NO', 'NO.', '#', ''],
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
  // A blank first header is the row-number column on the sheet this was
  // written for; only the very first column may claim it that way.
  if (out.sheetNo === undefined && header[0]?.trim() === '') out.sheetNo = 0;
  return out;
};

const cell = (row: readonly string[], index: number | undefined): string =>
  index === undefined ? '' : (row[index] ?? '').trim();

const orNull = (value: string): string | null => (value === '' ? null : value);

/**
 * Sheet rows -> roster rows. Rows without a username are skipped: the
 * username is the key an import matches on, and a row without one is a
 * heading, a note or an empty line.
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
  rows.slice(1).forEach((row, offset) => {
    const username = cleanUsername(cell(row, columns.username));
    if (username === '') return;

    const rawNo = cell(row, columns.sheetNo);
    const numbered = Number.parseInt(rawNo, 10);
    parsed.push({
      sheetNo: Number.isFinite(numbered) ? numbered : offset + 1,
      facebookName: orNull(cell(row, columns.facebookName)),
      username,
      password: orNull(cell(row, columns.password)),
      gmail: orNull(cell(row, columns.gmail)),
      gmailPassword: orNull(cell(row, columns.gmailPassword)),
      phone: orNull(cell(row, columns.phone)),
    });
  });

  return parsed;
};

/**
 * Pulls the roster in and reconciles it with the accounts table. The
 * username is the key; a row already known updates its roster fields and
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
      `Roster import: ${result.created} created, ${result.updated} updated, ${result.skipped.length} skipped`,
      { event: 'roster.imported' },
    );
    return { ...result, rows: roster.length };
  }
}
