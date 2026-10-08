import { describe, expect, it } from 'vitest';
import { loadConfig } from '@fb/server/config';

describe('loadConfig auth', () => {
  it('leaves the login off and generates a secret when nothing is set', () => {
    const config = loadConfig({});
    expect(config.auth.password).toBeNull();
    expect(config.auth.secret).toMatch(/^[0-9a-f]{64}$/);
    expect(config.auth.secretSource).toBe('generated');
  });

  it('turns the login on with the given password and secret', () => {
    const config = loadConfig({ AUTH_PASSWORD: 'hunter22', AUTH_SECRET: 'abc123' });
    expect(config.auth).toEqual({ password: 'hunter22', secret: 'abc123', secretSource: 'env' });
  });

  it('treats a blank password as unset', () => {
    expect(loadConfig({ AUTH_PASSWORD: '   ' }).auth.password).toBeNull();
  });

  it('generates a different secret on every load', () => {
    expect(loadConfig({}).auth.secret).not.toBe(loadConfig({}).auth.secret);
  });
});
