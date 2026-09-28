import { mkdir, rm, stat, readdir } from 'node:fs/promises';
import { isAbsolute, join, normalize, relative, sep } from 'node:path';
import { PathTraversalError, ProfilePathInvalidError, ProfileSlugSchema } from '@fb/shared';
import type { ProfileStorage } from '@fb/application';

/**
 * Owns the profile directories on disk. Every path the rest of the system uses
 * comes from here, which is what makes "the profile must stay inside the
 * profile root" a property of the system rather than a habit.
 */
export class ProfileManager implements ProfileStorage {
  constructor(private readonly root: string) {}

  resolve(slug: string): string {
    const parsed = ProfileSlugSchema.safeParse(slug);
    if (!parsed.success) throw new ProfilePathInvalidError(slug);

    const target = normalize(join(this.root, parsed.data));
    const rel = relative(this.root, target);

    // Belt and braces: the slug pattern already forbids separators, but the
    // check stays so a future change to that pattern cannot open a hole.
    if (rel === '' || rel.startsWith('..') || isAbsolute(rel) || rel.split(sep).includes('..')) {
      throw new PathTraversalError(slug);
    }

    return target;
  }

  async ensure(slug: string): Promise<string> {
    const directory = this.resolve(slug);
    await mkdir(directory, { recursive: true });
    return directory;
  }

  async exists(slug: string): Promise<boolean> {
    try {
      const info = await stat(this.resolve(slug));
      return info.isDirectory();
    } catch {
      return false;
    }
  }

  async remove(slug: string): Promise<void> {
    await rm(this.resolve(slug), { recursive: true, force: true });
  }

  /** Approximate on-disk size, for the settings page and for housekeeping. */
  async sizeBytes(slug: string): Promise<number> {
    const directory = this.resolve(slug);
    return this.measure(directory);
  }

  private async measure(directory: string): Promise<number> {
    let total = 0;
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch {
      return 0;
    }

    for (const entry of entries) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) {
        total += await this.measure(path);
        continue;
      }
      try {
        total += (await stat(path)).size;
      } catch {
        // A file the browser removed mid-walk simply counts as zero.
      }
    }
    return total;
  }
}
