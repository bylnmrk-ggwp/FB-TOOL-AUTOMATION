import { describe, expect, it } from 'vitest';
// The automation package is not a root dependency; the built module is what the server runs anyway.
import { Gate } from '../../packages/automation/dist/browser/Gate.js';

describe('Gate', () => {
  it('lets the configured number through and holds the rest until a release', async () => {
    const gate = new Gate(2);
    const first = await gate.acquire();
    await gate.acquire();

    let thirdIn = false;
    const third = gate.acquire().then((release) => {
      thirdIn = true;
      return release;
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(thirdIn).toBe(false);

    first();
    await third;
    expect(thirdIn).toBe(true);
  });

  it('ignores a second release of the same place', async () => {
    const gate = new Gate(1);
    const release = await gate.acquire();
    release();
    release();

    const next = await gate.acquire();
    let laterIn = false;
    const later = gate.acquire().then(() => {
      laterIn = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(laterIn).toBe(false);
    next();
    await later;
    expect(laterIn).toBe(true);
  });
});
