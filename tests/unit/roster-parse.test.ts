import { describe, expect, it } from 'vitest';
import { mapHeaders, parseRoster } from '@fb/application';

/**
 * The header row as Google's CSV export hands it out: the row-number label
 * comes back as "0", the phone column keeps its label, and the sheet's empty
 * columns trail as blank headers.
 */
const EXPORTED_HEADER = [
  '0',
  'FACEBOOK NAME',
  'USERNAME',
  'PASSWORD',
  ' GMAIL',
  'PASS FOR GMAIL',
  'NUMBER',
  'STATUS',
  '',
  '',
];

describe('mapHeaders', () => {
  it('reads the row number from a numeric first header, never from a blank one later', () => {
    const columns = mapHeaders(EXPORTED_HEADER);
    expect(columns.sheetNo).toBe(0);
    expect(columns.facebookName).toBe(1);
    expect(columns.username).toBe(2);
    expect(columns.gmail).toBe(4);
    expect(columns.phone).toBe(6);
  });

  it('accepts a blank first header as the row number', () => {
    expect(mapHeaders(['', 'NAME', 'USERNAME']).sheetNo).toBe(0);
  });

  it('does not take a blank header elsewhere as the row number', () => {
    expect(mapHeaders(['NAME', 'USERNAME', '']).sheetNo).toBeUndefined();
  });
});

describe('parseRoster', () => {
  it('counts only rows with both a username and a password, keyed on column A', () => {
    const rows = parseRoster([
      EXPORTED_HEADER,
      ['1', 'Rene Batler', 'rene@example.com', 'secret', '', '', '', ''],
      ['2', '', 'second@example.com', 'secret', '', '', '', ''],
      ['3', 'No password yet', 'third@example.com', '', '', '', '', ''],
      ['4', 'No username', '', 'secret', '', '', '', ''],
      ['5', '', '', '', '', '', '', ''],
      ['', '', '', '', '', '', '', ''],
    ]);

    expect(rows.map((row) => row.sheetNo)).toEqual([1, 2]);
    expect(rows[0]?.facebookName).toBe('Rene Batler');
    expect(rows[1]?.facebookName).toBeNull();
  });

  it('treats a digits-only Facebook name as no name', () => {
    const rows = parseRoster([
      EXPORTED_HEADER,
      ['7', '7', 'seven@example.com', 'secret', '', '', '', ''],
    ]);
    expect(rows[0]?.facebookName).toBeNull();
  });

  it('keeps a row that has credentials but no number', () => {
    const rows = parseRoster([
      ['NAME', 'USERNAME', 'PASSWORD'],
      ['Someone', 'someone@example.com', 'secret'],
    ]);
    expect(rows).toEqual([
      expect.objectContaining({ sheetNo: null, username: 'someone@example.com' }),
    ]);
  });
});
