import { ClientMessageSchema, ServerEventSchema, type ServerEvent } from '@fb/shared';

/**
 * Nothing goes onto the wire without passing the shared schema first.
 *
 * The frontend parses with the same schema on arrival, so a malformed frame is
 * a server-side bug that shows up here — in one place — rather than as
 * undefined spreading through a React reducer.
 */
export const encodeEvent = (event: ServerEvent): string | null => {
  const parsed = ServerEventSchema.safeParse(event);
  return parsed.success ? JSON.stringify(parsed.data) : null;
};

export const decodeClientMessage = (
  raw: string,
): ReturnType<typeof ClientMessageSchema.safeParse> => {
  try {
    return ClientMessageSchema.safeParse(JSON.parse(raw));
  } catch {
    return ClientMessageSchema.safeParse(undefined);
  }
};
