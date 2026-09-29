/**
 * The fingerprint patches a headless-or-automated Chromium needs to stop
 * reading as a bot in JavaScript.
 *
 * This is one half of staying unchallenged, and the smaller half. Meta scores
 * the IP address, the account's age and history, and the rhythm of what it
 * does at least as heavily as the browser fingerprint. Nothing here touches
 * those: a fresh account on a datacenter IP acting fast is challenged no
 * matter how clean the `navigator` object looks. What this removes is the
 * cheap, certain tells — the properties Playwright leaves behind that a real
 * Chrome never has — so a warm account on a good IP is not challenged for the
 * browser alone.
 *
 * Runs as an init script: it is injected before any page script on every
 * navigation and every frame, so the page never sees the unpatched values.
 */
export const STEALTH_INIT_SCRIPT = `
(() => {
  const define = (object, name, get) => {
    try {
      Object.defineProperty(object, name, { get, configurable: true });
    } catch {
      // A property that refuses redefinition is left as it is.
    }
  };

  // 1. navigator.webdriver: true on an automated browser, absent on a real one.
  define(Navigator.prototype, 'webdriver', () => false);

  // 2. window.chrome: a real Chrome exposes this object; headless does not.
  if (!window.chrome) {
    window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };
  }

  // 3. Plugins and mimeTypes: empty arrays are a headless signature. A short,
  //    plausible list is what a desktop Chrome reports.
  const pluginData = [
    { name: 'PDF Viewer', filename: 'internal-pdf-viewer' },
    { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer' },
    { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer' },
  ];
  define(Navigator.prototype, 'plugins', () => {
    const list = pluginData.map((p) => ({ ...p, length: 1 }));
    list.item = (i) => list[i] ?? null;
    list.namedItem = (n) => list.find((p) => p.name === n) ?? null;
    return list;
  });

  // 4. languages: headless can report an empty list.
  define(Navigator.prototype, 'languages', () => ['en-US', 'en']);

  // 5. permissions.query for notifications: an automated browser answers
  //    'denied' where a real one answers 'prompt' until the user chooses.
  const query = window.navigator.permissions && window.navigator.permissions.query;
  if (query) {
    window.navigator.permissions.query = (params) =>
      params && params.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission, onchange: null })
        : query.call(window.navigator.permissions, params);
  }

  // 6. WebGL vendor and renderer: headless returns a software renderer; a real
  //    machine names its GPU. A common Intel string is unremarkable.
  const getParameter = WebGLRenderingContext.prototype.getParameter;
  const patchGl = (proto) => {
    proto.getParameter = function (parameter) {
      if (parameter === 37445) return 'Intel Inc.';
      if (parameter === 37446) return 'Intel Iris OpenGL Engine';
      return getParameter.call(this, parameter);
    };
  };
  patchGl(WebGLRenderingContext.prototype);
  if (window.WebGL2RenderingContext) patchGl(WebGL2RenderingContext.prototype);

  // 7. Core counts: 0 or absurd values are a tell; a mid-range desktop is not.
  if (navigator.hardwareConcurrency < 2) define(Navigator.prototype, 'hardwareConcurrency', () => 8);
  define(Navigator.prototype, 'deviceMemory', () => 8);
})();
`;
