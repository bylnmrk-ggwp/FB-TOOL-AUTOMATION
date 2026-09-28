/** Filesystem side of a browser profile, kept behind a port for testability. */
export interface ProfileStorage {
  /** Creates the directory if needed and returns its absolute path. */
  ensure(slug: string): Promise<string>;
  /** Absolute path for a slug. Throws when the slug escapes the profile root. */
  resolve(slug: string): string;
  remove(slug: string): Promise<void>;
  exists(slug: string): Promise<boolean>;
  sizeBytes(slug: string): Promise<number>;
}
