/** Structural helpers used across packages. Domain types live with their schema. */

export type Brand<T, B extends string> = T & { readonly __brand: B };

export type DeepReadonly<T> = T extends (infer R)[]
  ? readonly DeepReadonly<R>[]
  : T extends object
    ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
    : T;

export type Nullable<T> = T | null;

export type Awaitable<T> = T | Promise<T>;

/** Every field optional except the listed keys. */
export type RequireOnly<T, K extends keyof T> = Partial<Omit<T, K>> & Pick<T, K>;
