import { describe, expect, it } from 'vitest';
import { normaliseApiBase } from '../../apps/web/src/lib/api-base';

describe('normaliseApiBase', () => {
  it('is empty, meaning same-origin, when nothing is configured', () => {
    expect(normaliseApiBase(undefined)).toBe('');
    expect(normaliseApiBase('')).toBe('');
    expect(normaliseApiBase('   ')).toBe('');
  });

  it('drops a trailing slash so paths never double it', () => {
    expect(normaliseApiBase('https://pc.tail1234.ts.net/')).toBe('https://pc.tail1234.ts.net');
    expect(normaliseApiBase('https://pc.tail1234.ts.net')).toBe('https://pc.tail1234.ts.net');
  });
});
