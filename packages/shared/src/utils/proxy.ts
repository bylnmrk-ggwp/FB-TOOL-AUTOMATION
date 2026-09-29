/**
 * A proxy as Playwright's launch option wants it: a credential-free server
 * URL, with the username and password carried alongside rather than inside
 * the URL (Chromium ignores inline credentials on the proxy server).
 */
export interface ProxyConfig {
  server: string;
  username?: string;
  password?: string;
}

/**
 * Parses the one string an operator pastes from a proxy provider into that
 * shape. Accepts, in order of how providers hand it out:
 *
 *   host:port                         → http://host:port
 *   host:port:user:pass               → http://host:port + credentials
 *   scheme://host:port                → as given
 *   scheme://user:pass@host:port      → server split from credentials
 *
 * The scheme defaults to http; socks5:// and https:// pass through. Returns
 * null for empty or unparseable input, so a blank field simply means "no
 * proxy" rather than a launch failure.
 */
export const parseProxy = (raw: string | null | undefined): ProxyConfig | null => {
  const value = (raw ?? '').trim();
  if (value === '') return null;

  // host:port:user:pass — the colon-separated form, no scheme, four parts.
  if (!value.includes('://') && !value.includes('@')) {
    const parts = value.split(':');
    if (parts.length === 4) {
      const [host, port, username, password] = parts;
      return { server: `http://${host}:${port}`, username, password };
    }
    if (parts.length === 2) return { server: `http://${value}` };
    return null;
  }

  const withScheme = value.includes('://') ? value : `http://${value}`;
  let url: URL;
  try {
    url = new URL(withScheme);
  } catch {
    return null;
  }

  const server = `${url.protocol}//${url.host}`;
  const config: ProxyConfig = { server };
  if (url.username !== '') config.username = decodeURIComponent(url.username);
  if (url.password !== '') config.password = decodeURIComponent(url.password);
  return config;
};

/** The host:port of a proxy, safe to show — never its credentials. */
export const proxyDisplay = (raw: string | null | undefined): string | null =>
  parseProxy(raw)?.server ?? null;
