import { mkdir, rm, stat, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import {
  createId,
  FileNotFoundError,
  PathTraversalError,
  UnsupportedMediaTypeError,
} from '@fb/shared';
import type { FileStore, StoredFile } from '@fb/application';
import { resolveInside } from '../../config/paths.js';

/** Only formats Facebook actually accepts for a post or a message. */
const ALLOWED_TYPES = new Map<string, string>([
  ['image/jpeg', '.jpg'],
  ['image/png', '.png'],
  ['image/gif', '.gif'],
  ['image/webp', '.webp'],
  ['video/mp4', '.mp4'],
  ['video/quicktime', '.mov'],
]);

/**
 * Files are addressed by an id the server issued, never by a path the client
 * chose. The id is a single generated filename, so there is nothing in it that
 * could point outside the upload directory — and `resolveInside` checks that
 * anyway before any path reaches the filesystem.
 */
export class UploadFileStore implements FileStore {
  constructor(private readonly root: string) {}

  async save(fileName: string, mimeType: string, data: Uint8Array): Promise<StoredFile> {
    const extension = ALLOWED_TYPES.get(mimeType);
    if (extension === undefined) throw new UnsupportedMediaTypeError(mimeType);

    await mkdir(this.root, { recursive: true });

    // The extension comes from the declared type, not from the supplied name.
    const id = `${createId('med')}${extension}`;
    const target = this.guard(id);
    await writeFile(target, data);

    return { id, fileName, mimeType, sizeBytes: data.byteLength };
  }

  async resolvePath(id: string): Promise<string> {
    const target = this.guard(id);
    try {
      await stat(target);
    } catch {
      throw new FileNotFoundError(id);
    }
    return target;
  }

  async exists(id: string): Promise<boolean> {
    try {
      await stat(this.guard(id));
      return true;
    } catch {
      return false;
    }
  }

  async delete(id: string): Promise<void> {
    await rm(this.guard(id), { force: true });
  }

  private guard(id: string): string {
    // A generated id has no separators; anything else is a client trying its
    // luck, and is refused before it can be turned into a path.
    if (!/^[A-Za-z0-9_.-]+$/.test(id)) throw new PathTraversalError(id);

    const resolved = resolveInside(this.root, id);
    if (resolved === null) throw new PathTraversalError(id);
    return resolved;
  }

  /** Where uploads live. Reported by the settings endpoint, never accepted from it. */
  get directory(): string {
    return join(this.root);
  }
}
