/** Compile-time proof that a switch or union is exhaustive. */
export const assertNever = (value: never, message = 'Unexpected value'): never => {
  throw new Error(`${message}: ${JSON.stringify(value)}`);
};

export const isDefined = <T>(value: T | null | undefined): value is T =>
  value !== null && value !== undefined;
