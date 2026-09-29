import { describe, expect, it } from 'vitest';
import { parseProxy, proxyDisplay } from '@fb/shared';

describe('parseProxy', () => {
  it('treats a bare host:port as http with no credentials', () => {
    expect(parseProxy('1.2.3.4:8080')).toEqual({ server: 'http://1.2.3.4:8080' });
  });

  it('reads the colon form host:port:user:pass', () => {
    expect(parseProxy('1.2.3.4:8080:alice:secret')).toEqual({
      server: 'http://1.2.3.4:8080',
      username: 'alice',
      password: 'secret',
    });
  });

  it('splits credentials out of a scheme URL', () => {
    expect(parseProxy('http://alice:secret@1.2.3.4:8080')).toEqual({
      server: 'http://1.2.3.4:8080',
      username: 'alice',
      password: 'secret',
    });
  });

  it('keeps a socks5 scheme', () => {
    expect(parseProxy('socks5://1.2.3.4:1080')).toEqual({ server: 'socks5://1.2.3.4:1080' });
  });

  it('decodes percent-encoded credentials', () => {
    expect(parseProxy('http://user:p%40ss@1.2.3.4:8080')).toEqual({
      server: 'http://1.2.3.4:8080',
      username: 'user',
      password: 'p@ss',
    });
  });

  it('returns null for empty or unparseable input', () => {
    expect(parseProxy('')).toBeNull();
    expect(parseProxy(null)).toBeNull();
    expect(parseProxy('   ')).toBeNull();
    expect(parseProxy('not a proxy')).toBeNull();
  });
});

describe('proxyDisplay', () => {
  it('shows the server and never the credentials', () => {
    expect(proxyDisplay('1.2.3.4:8080:alice:secret')).toBe('http://1.2.3.4:8080');
    expect(proxyDisplay('http://alice:secret@host:3128')).toBe('http://host:3128');
    expect(proxyDisplay('')).toBeNull();
  });
});
