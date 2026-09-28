export interface StoredFile {
  id: string;
  fileName: string;
  mimeType: string;
  sizeBytes: number;
}

/**
 * Every file the automation engine touches is addressed by id. Resolving an id
 * to an absolute path happens here and nowhere else, which is what keeps
 * client-supplied paths out of the filesystem.
 */
export interface FileStore {
  save(fileName: string, mimeType: string, data: Uint8Array): Promise<StoredFile>;
  /** Throws when the id does not resolve inside the configured root. */
  resolvePath(id: string): Promise<string>;
  exists(id: string): Promise<boolean>;
  delete(id: string): Promise<void>;
}
